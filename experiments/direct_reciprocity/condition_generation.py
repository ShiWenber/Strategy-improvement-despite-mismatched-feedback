"""Shared candidate requests, sequential condition batches and per-condition data logs."""
import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import shutil
import threading
import time
import traceback

from .core import Config, Policy
from .records import read_json, write_json, cached_request, begin_request
from .run import Generator, validate
from .specificity_assets import SCORE_ARMS, generation_arms
from ..config.load_env import require_model

_LOG_LOCK = threading.Lock()
TOKEN_LIMITS = {('deepseek', 'off'): 6000, ('deepseek', 'on'): 384000,
                ('qwen', 'off'): 6000, ('qwen', 'on'): 131072}


def specification(prompt, provider, mode, *, model=None):
    """Resolve request parameters, optionally using an explicitly selected model."""
    model = require_model(provider) if model is None else model.strip()
    if not model:
        raise ValueError('Explicit model must not be empty')
    spec = dict(provider=provider, model=model,
                prompt=prompt, temperature=1, max_tokens=TOKEN_LIMITS[provider, mode])
    spec['extra_body'] = ({'thinking': {'type': 'enabled' if mode == 'on' else 'disabled'}}
                          if provider == 'deepseek' else {'enable_thinking': mode == 'on'})
    if mode == 'on':
        spec['reasoning_effort'] = 'high'
    if provider != 'deepseek' or mode != 'off':
        spec.update(stream=True, stream_options={'include_usage': True})
    return spec


def transport_diagnostics(exc, secret):
    """Keep transport exception chains without credentials, headers or frame locals."""
    import httpx
    chain, seen = [], set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        message = (str(exc) if isinstance(exc, httpx.TransportError)
                   or type(exc).__module__.startswith(('httpcore', 'h11'))
                   else 'Non-transport exception; inspect type and frames')
        if secret:
            message = message.replace(secret, '[REDACTED]')
        chain.append({'type': type(exc).__name__, 'module': type(exc).__module__, 'message': message[:2000],
                      'frames': [{'file': Path(f.filename).name, 'line': f.lineno, 'function': f.name}
                                 for f in traceback.extract_tb(exc.__traceback__)]})
        exc = exc.__cause__ if exc.__cause__ is not None else (None if exc.__suppress_context__ else exc.__context__)
    return chain


def receive_stream(stream, sink, progress):
    content, reasoning = [], []
    usage, finish, response_id, model = None, None, None, None
    last, chars = time.monotonic(), 0
    for chunk in stream:
        sink.write(json.dumps(chunk.model_dump(), ensure_ascii=False) + '\n')
        sink.flush()
        response_id, model = chunk.id or response_id, chunk.model or model
        if chunk.usage is not None:
            usage = chunk.usage.model_dump()
        for choice in chunk.choices:
            if choice.index != 0:
                raise RuntimeError('Unexpected multiple choices')
            r, c = getattr(choice.delta, 'reasoning_content', None) or '', choice.delta.content or ''
            reasoning.append(r)
            content.append(c)
            chars += len(r) + len(c)
            if choice.finish_reason is not None:
                finish = choice.finish_reason
        if time.monotonic() - last > 10:
            progress(chars)
            last = time.monotonic()
    if finish is None:
        raise RuntimeError('Stream ended without finish_reason; uncertain request, never retry silently')
    return dict(content=''.join(content), reasoning_content=''.join(reasoning), usage=usage,
                finish_reason=finish, response_id=response_id, returned_model=model)


def _archive_failed_request(root, path, record):
    """Preserve the failed response and its partial stream before another attempt."""
    root, path = Path(root), Path(path)
    archive = root / 'attempt_history' / f'retry_{time.time_ns()}'
    sources = [('requests_candidates', path),
               ('streams', root / 'streams' / (path.stem + '.jsonl')),
               ('request_progress', root / 'request_progress' / path.name)]
    for folder, source in sources:
        if source.exists():
            destination = archive / folder / source.name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
    path.unlink()


def retry_after_seconds(value, now=None):
    """Accept bounded Retry-After seconds or an HTTP date; ignore invalid values."""
    if value is None:
        return None
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        from datetime import timezone
        from email.utils import parsedate_to_datetime
        try:
            date = parsedate_to_datetime(str(value))
            if date.tzinfo is None:
                date = date.replace(tzinfo=timezone.utc)
            seconds = date.timestamp() - (time.time() if now is None else now)
        except (TypeError, ValueError, OverflowError):
            return None
    return seconds if 0 <= seconds <= 3600 else None


def provider_failure_metadata(exc, secret):
    """Whitelist provider diagnostics and Retry-After, redacting the API key."""
    def redact(value):
        if isinstance(value, str):
            return (value.replace(secret, '[REDACTED]') if secret else value)[:2000]
        return value if value is None or isinstance(value, (bool, int, float)) else None

    result = {}
    body = getattr(exc, 'body', None)
    if isinstance(body, dict):
        error = body['error'] if isinstance(body.get('error'), dict) else body
        result['provider_error'] = {name: redact(error.get(name)) for name in ('type', 'code', 'message')}
    headers = getattr(getattr(exc, 'response', None), 'headers', {}) or {}
    retry_after = headers.get('retry-after') or headers.get('Retry-After')
    if retry_after is not None:
        result['retry_after'] = redact(str(retry_after))
        result['retry_after_seconds'] = retry_after_seconds(retry_after)
    return result


def streamed_program(root, job, spec, cfg, api_retries=3):
    import httpx
    import random

    def retryable_status(status):
        return status in (408, 409, 429) or isinstance(status, int) and status >= 500

    def transport_failure(exc):
        seen = set()
        while exc is not None and id(exc) not in seen:
            seen.add(id(exc))
            if isinstance(exc, httpx.TransportError):
                return True
            exc = exc.__cause__ if exc.__cause__ is not None else (None if exc.__suppress_context__ else exc.__context__)
        return False

    path = root / 'requests_candidates' / (job['id'] + '.json')
    record = cached_request(path, spec, retry_failed=True)
    if record is not None and record.get('status') == 'api_error':
        saved_transport = any(isinstance(error_class := getattr(httpx, item.get('type', ''), None), type)
                              and issubclass(error_class, httpx.TransportError)
                              for item in record.get('exception_chain', []))
        if not (retryable_status(record.get('http_status')) or saved_transport):
            raise RuntimeError('Saved request is not a confirmed retryable failure; inspect ' + job['id'])
        if record.get('http_status') == 429:
            finished = record.get('finished_at')
            elapsed = max(0., time.time() - finished) if isinstance(finished, (int, float)) else 0.
            wait = max(60., retry_after_seconds(record.get('retry_after_seconds')) or 0.) - elapsed
            if wait > 0:
                time.sleep(wait + random.uniform(0., 1.))
        _archive_failed_request(root, path, record)
        record = None
    if record is None:
        from openai import OpenAI
        from ..config.load_env import get_api_key, get_base_url
        key = get_api_key(spec['provider'])
        if not key:
            raise RuntimeError('Provider not configured')
        events = root / 'streams' / (job['id'] + '.jsonl')
        events.parent.mkdir(exist_ok=True)
        if events.exists():
            events.unlink()
        progress_path = root / 'request_progress' / (job['id'] + '.json')
        if progress_path.exists():
            progress_path.unlink()

        def progress(chars):
            write_json(root / 'request_progress' / (job['id'] + '.json'),
                       {'id': job['id'], 'characters_received': chars, 'updated_at': time.time()})

        direct = os.environ.get('DIRECT_RECIPROCITY_API_DIRECT') == '1'
        timeout = httpx.Timeout(3600, connect=30)
        client_options = {'timeout': timeout}
        if direct:
            client_options['http_client'] = httpx.Client(trust_env=False, timeout=timeout)
        with OpenAI(api_key=key, base_url=get_base_url(spec['provider']), max_retries=0,
                    **client_options) as client:
            request = {k: v for k, v in spec.items() if k not in ('provider', 'prompt')}
            request['messages'] = [{'role': 'user', 'content': spec['prompt']}]
            for attempt in range(api_retries + 1):
                record = begin_request(path, spec)
                record['transport'] = {'direct': direct, 'trust_env': not direct}
                write_json(path, record)
                if events.exists():
                    events.unlink()
                with events.open('x', encoding='utf-8') as sink:
                    try:
                        with client.chat.completions.create(**request) as stream:
                            response = stream.response
                            record['response_metadata'] = {
                                'http_status': response.status_code, 'http_version': response.http_version,
                                'opened_at': time.time(), 'headers': {k: response.headers[k] for k in
                                    ('x-request-id', 'request-id', 'content-type', 'transfer-encoding') if k in response.headers}}
                            write_json(path, record)
                            result = receive_stream(stream, sink, progress)
                        record.update(result, status='received', finished_at=time.time())
                        write_json(path, record)
                        break
                    except Exception as exc:
                        error = {'error_type': type(exc).__name__, 'http_status': getattr(exc, 'status_code', None),
                                 'exception_chain': transport_diagnostics(exc, key)}
                        error.update(provider_failure_metadata(exc, key))
                        record.update(error, status='api_error', finished_at=time.time())
                        write_json(path, record)
                        http_status = getattr(exc, 'status_code', None)
                        retryable = transport_failure(exc) or retryable_status(http_status)
                        if not retryable or attempt >= api_retries:
                            raise RuntimeError('Request failed; saved metadata for ' + job['id']) from None
                        delay = min(60., 2. * 2 ** min(attempt, 5))
                        if http_status == 429:
                            delay = max(60., record.get('retry_after_seconds') or 0.)
                        delay += random.uniform(0., 1.)
                        record.update(retry_delay_seconds=delay, retry_number=attempt + 1)
                        write_json(path, record)
                        sink.close()
                        _archive_failed_request(root, path, record)
                        if events.exists():
                            events.unlink()
                        if progress_path.exists():
                            progress_path.unlink()
                        time.sleep(delay)
    policy = validate(record, job['id'], cfg)
    write_json(path, record)
    return policy


def log_path(root, arm):
    if arm not in SCORE_ARMS:
        raise ValueError('Unknown information condition: ' + arm)
    return Path(root) / 'arm_logs' / (arm + '.jsonl')


def data_log_row(root, job):
    root = Path(root)
    row = {'id': job['id'], 'arm': job['arm'], 'job': job}
    for folder, key in [('requests_candidates', 'request'), ('candidates', 'candidate'),
                        ('selection_scores', 'selection_scores'), ('holdout', 'holdout')]:
        relative = f"{folder}/{job['id']}.json"
        path = root / relative
        row[key] = None
        if path.exists():
            row[key] = read_json(path)
    row['status'] = row['request']['status'] if row['request'] else 'pending'
    return row


def append_data_log(root, job):
    """Append a durable completion snapshot; batch export removes resume duplicates."""
    path = log_path(root, job['arm'])
    row = data_log_row(root, job)
    with _LOG_LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(row, ensure_ascii=False) + '\n')


def write_arm_logs(root, manifest, arm=None):
    """Atomically export one condition or all conditions using the same log schema."""
    paths = []
    for condition in ((arm,) if arm is not None else generation_arms(manifest['arms'])):
        if condition not in manifest['arms']:
            raise ValueError('Condition absent from frozen batch: ' + condition)
        path = log_path(root, condition)
        with _LOG_LOCK:
            path.parent.mkdir(parents=True, exist_ok=True)
            temp = path.with_suffix('.jsonl.tmp')
            with temp.open('w', encoding='utf-8') as stream:
                for job in manifest['jobs']:
                    if job['arm'] == condition:
                        stream.write(json.dumps(data_log_row(root, job), ensure_ascii=False) + '\n')
            temp.replace(path)
        paths.append(path)
    return paths


def generate_candidate(root, job, arm, *, provider='deepseek', mode='off', model=None, api_retries=3):
    """All models share the same condition parameter, candidate record and log path."""
    if arm not in SCORE_ARMS or job['arm'] != arm:
        raise ValueError('Candidate information condition differs from task')
    root = Path(root)
    out = root / 'candidates' / (job['id'] + '.json')
    try:
        context = read_json(root / 'contexts' / (job['context'] + '.json'))
        cfg = Config(seed=job['seed'])
        spec = specification(context['prompts'][arm], provider, mode, model=model)
        if out.exists():
            saved = read_json(out)
            request = cached_request(root / 'requests_candidates' / (job['id'] + '.json'), spec)
            if (request is None or any(saved.get(key) != value for key, value in job.items())
                    or saved['valid'] != (request['status'] == 'valid')):
                raise RuntimeError('Cached candidate differs from frozen task or request: ' + job['id'])
            return {'id': job['id'], 'arm': arm, 'cached': True}
        if provider == 'deepseek' and mode == 'off':
            generator = Generator(root / 'requests_candidates', provider, spec['model'], cfg.temperature)
            policy = generator.generate(job['id'], spec['prompt'], cfg)
        else:
            policy = streamed_program(root, job, spec, cfg, api_retries=api_retries)
        write_json(out, {**job, 'child': asdict(policy) if policy else None,
                        'parent_key': Policy(**context['parent']).key, 'valid': policy is not None})
        record = read_json(root / 'requests_candidates' / (job['id'] + '.json'))
        return {'id': job['id'], 'arm': arm, 'valid': policy is not None,
                'reasoning_chars': len(record.get('reasoning_content') or ''),
                'finish_reason': record.get('finish_reason'), 'usage': record.get('usage')}
    finally:
        append_data_log(root, job)


def candidate_job(arg, *, provider='deepseek', mode='off', model=None, api_retries=3):
    root, job = arg
    return generate_candidate(root, job, job['arm'], provider=provider, mode=mode, model=model,
                              api_retries=api_retries)


def jobs_for_arm(root, manifest, arm):
    order = generation_arms(manifest['arms'])
    if arm not in order:
        raise ValueError('Condition absent from frozen batch: ' + arm)
    for previous in order[:order.index(arm)]:
        for job in (j for j in manifest['jobs'] if j['arm'] == previous):
            candidate = Path(root) / 'candidates' / (job['id'] + '.json')
            request = Path(root) / 'requests_candidates' / (job['id'] + '.json')
            if not candidate.exists() or not request.exists():
                raise RuntimeError('Complete ' + previous + ' before generating ' + arm)
            saved, response = read_json(candidate), read_json(request)
            if response['status'] not in ('valid', 'invalid') or saved['valid'] != (response['status'] == 'valid'):
                raise RuntimeError('Complete ' + previous + ' before generating ' + arm)
    return [j for j in manifest['jobs'] if j['arm'] == arm]


def generate_conditions(root, manifest, workers, generate_one, arm=None):
    from .specificity import pool_run
    for condition in ((arm,) if arm is not None else generation_arms(manifest['arms'])):
        jobs = jobs_for_arm(root, manifest, condition)
        try:
            pool_run(generate_one, [(str(root), job) for job in jobs], workers, root, 'generate_' + condition)
        finally:
            write_arm_logs(root, manifest, condition)


def main():
    parser = argparse.ArgumentParser(description='Export one data log per information condition; no API calls.')
    parser.add_argument('--roots', type=Path, nargs='+', required=True)
    args = parser.parse_args()
    for root in args.roots:
        paths = write_arm_logs(root, read_json(root / 'manifest.json'))
        print(json.dumps({'root': str(root), 'logs': [str(p) for p in paths]}))


if __name__ == '__main__':
    main()
