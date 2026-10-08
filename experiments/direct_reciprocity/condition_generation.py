"""Shared candidate requests, sequential condition batches and per-condition data logs."""
import argparse
from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
import threading
import time
import traceback

from .core import Config, Policy
from .records import read_json, write_json, cached_request, begin_request
from .run import Generator, validate
from .specificity_assets import SCORE_ARMS, generation_arms

_LOG_LOCK = threading.Lock()
TOKEN_LIMITS = {('deepseek', 'off'): 6000, ('deepseek', 'on'): 384000,
                ('qwen', 'off'): 6000, ('qwen', 'on'): 131072}


def specification(prompt, provider, mode):
    spec = dict(provider=provider, model={'deepseek': 'deepseek-flash', 'qwen': 'qwen3.8-flash'}[provider],
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


def streamed_program(root, job, spec, cfg, require_reasoning):
    path = root / 'requests_candidates' / (job['id'] + '.json')
    record = cached_request(path, spec)
    if record is None:
        from openai import OpenAI
        import httpx
        from ..config.load_env import get_api_key, get_base_url
        key = get_api_key(spec['provider'])
        if not key:
            raise RuntimeError('Provider not configured')
        record = begin_request(path, spec)
        events = root / 'streams' / (job['id'] + '.jsonl')
        events.parent.mkdir(exist_ok=True)

        def progress(chars):
            write_json(root / 'request_progress' / (job['id'] + '.json'),
                       {'id': job['id'], 'characters_received': chars, 'updated_at': time.time()})

        try:
            with OpenAI(api_key=key, base_url=get_base_url(spec['provider']), max_retries=0,
                        timeout=httpx.Timeout(3600, connect=30)) as client:
                request = {k: v for k, v in spec.items() if k not in ('provider', 'prompt')}
                request['messages'] = [{'role': 'user', 'content': spec['prompt']}]
                with events.open('x', encoding='utf-8') as sink:
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
        except Exception as exc:
            error = {'error_type': type(exc).__name__, 'http_status': getattr(exc, 'status_code', None),
                     'exception_chain': transport_diagnostics(exc, key)}
            body = getattr(exc, 'body', None)
            if isinstance(body, dict) and isinstance(body.get('error'), dict):
                error['provider_error'] = {k: body['error'].get(k) for k in ('type', 'code', 'message')}
            record.update(error, status='api_error', finished_at=time.time())
            write_json(path, record)
            raise RuntimeError('Request failed; saved metadata for ' + job['id']) from None
    if require_reasoning and not record.get('reasoning_content'):
        raise RuntimeError('No native reasoning evidence; stop dispatch and inspect ' + job['id'])
    if record.get('returned_model') != spec['model']:
        raise RuntimeError('Unexpected returned model; inspect before continuing')
    policy = validate(record, job['id'], cfg)
    write_json(path, record)
    return policy


def log_path(root, arm):
    if arm not in SCORE_ARMS:
        raise ValueError('Unknown information condition: ' + arm)
    return Path(root) / 'arm_logs' / (arm + '.jsonl')


def data_log_row(root, job):
    root = Path(root)
    row = {'id': job['id'], 'arm': job['arm'], 'job': job, 'record_sha256': {}}
    for folder, key in [('requests_candidates', 'request'), ('candidates', 'candidate'),
                        ('selection_scores', 'selection_scores'), ('holdout', 'holdout')]:
        relative = f"{folder}/{job['id']}.json"
        path = root / relative
        row[key] = None
        if path.exists():
            content = path.read_bytes()
            row[key] = json.loads(content)
            row['record_sha256'][relative] = sha256(content).hexdigest()
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


def generate_candidate(root, job, arm, *, provider='deepseek', mode='off'):
    """All models share the same condition parameter, candidate record and log path."""
    if arm not in SCORE_ARMS or job['arm'] != arm:
        raise ValueError('Candidate information condition differs from task')
    root = Path(root)
    out = root / 'candidates' / (job['id'] + '.json')
    try:
        context = read_json(root / 'contexts' / (job['context'] + '.json'))
        cfg = Config(seed=job['seed'])
        spec = specification(context['prompts'][arm], provider, mode)
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
            policy = streamed_program(root, job, spec, cfg, require_reasoning=mode == 'on')
        write_json(out, {**job, 'child': asdict(policy) if policy else None,
                        'parent_key': Policy(**context['parent']).key, 'valid': policy is not None})
        record = read_json(root / 'requests_candidates' / (job['id'] + '.json'))
        return {'id': job['id'], 'arm': arm, 'valid': policy is not None,
                'reasoning_chars': len(record.get('reasoning_content') or ''),
                'finish_reason': record.get('finish_reason'), 'usage': record.get('usage')}
    finally:
        append_data_log(root, job)


def candidate_job(arg, *, provider='deepseek', mode='off'):
    root, job = arg
    return generate_candidate(root, job, job['arm'], provider=provider, mode=mode)


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
        from .restore_score import verify_restoration
        verify_restoration(root)
        paths = write_arm_logs(root, read_json(root / 'manifest.json'))
        print(json.dumps({'root': str(root), 'logs': [str(p) for p in paths]}))


if __name__ == '__main__':
    main()
