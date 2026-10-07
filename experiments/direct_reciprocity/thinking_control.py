"""Native model request settings, streaming and candidate validation."""
from dataclasses import asdict, replace
import json
from pathlib import Path
import time
import traceback

from .core import Policy, match
from .baselines import TRAIN
from .specificity import cfg_for
from .records import read_json, write_json, cached_request, begin_request

SOURCE = Path('results/feedback_specificity_v2')
DEFAULT_ROOT = Path('results/feedback_specificity_thinking_384k_20260923')
PROTOCOL = Path('docs/direct_reciprocity/THINKING_384K_PROTOCOL.md')
MAX_TOKENS = 384000


def transport_diagnostics(exc, secret):
    """Keep transport exception chains without credentials, headers or frame locals."""
    import httpx
    chain, seen = [], set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        message = str(exc) if isinstance(exc, httpx.TransportError) or type(exc).__module__.startswith(('httpcore', 'h11')) else 'Non-transport exception; inspect type and frames'
        if secret:
            message = message.replace(secret, '[REDACTED]')
        chain.append({'type':type(exc).__name__, 'module':type(exc).__module__,
                      'message':message[:2000],
                      'frames':[{'file':Path(f.filename).name, 'line':f.lineno, 'function':f.name}
                                for f in traceback.extract_tb(exc.__traceback__)]})
        exc = exc.__cause__ if exc.__cause__ is not None else (None if exc.__suppress_context__ else exc.__context__)
    return chain


def specification(prompt):
    return dict(provider='deepseek', model='deepseek-flash', prompt=prompt,
                temperature=1, max_tokens=MAX_TOKENS, reasoning_effort='high',
                extra_body={'thinking': {'type': 'enabled'}},
                stream=True, stream_options={'include_usage': True})


def validate(record, identity, cfg):
    if not record.get('content') or record.get('finish_reason') == 'length':
        record.update(status='invalid', validation_error='Missing or truncated program output')
        return None
    code = record['content']
    if code.strip().startswith('```'):
        lines = code.strip().splitlines()
        if lines[-1].strip() == '```':
            code = '\n'.join(lines[1:-1])
    policy = Policy(identity, code)
    try:
        policy.compile()
        for opponent in TRAIN:
            match(policy, opponent, replace(cfg, repeats=1), 12345)
    except Exception as exc:
        record.update(status='invalid', validation_error=f'{type(exc).__name__}: {exc}')
        return None
    record.update(status='valid', code_hash=policy.key)
    return policy


def receive_stream(stream, sink, progress):
    content, reasoning = [], []
    usage, finish, response_id, model = None, None, None, None
    last = time.monotonic()
    chars = 0
    for chunk in stream:
        data = chunk.model_dump()
        sink.write(json.dumps(data, ensure_ascii=False) + '\n')
        sink.flush()
        response_id = chunk.id or response_id
        model = chunk.model or model
        if chunk.usage is not None:
            usage = chunk.usage.model_dump()
        for choice in chunk.choices:
            if choice.index != 0:
                raise RuntimeError('Unexpected multiple choices')
            delta = choice.delta
            r = getattr(delta, 'reasoning_content', None) or ''
            c = delta.content or ''
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
    return dict(content=''.join(content), reasoning_content=''.join(reasoning),
                usage=usage, finish_reason=finish, response_id=response_id, returned_model=model)


def generate_one(arg):
    root, job = arg
    root = Path(root)
    out = root / 'candidates' / (job['id'] + '.json')
    if out.exists():
        return {'id': job['id'], 'cached': True}
    c = read_json(root / 'contexts' / (job['context'] + '.json'))
    spec = specification(c['prompts'][job['arm']])
    path = root / 'requests_candidates' / (job['id'] + '.json')
    record = cached_request(path, spec)
    if record is None:
        from openai import OpenAI
        import httpx
        from ..config.load_env import get_api_key, get_base_url
        key = get_api_key('deepseek')
        if not key:
            raise RuntimeError('Provider not configured')
        record = begin_request(path, spec)
        events = root / 'streams' / (job['id'] + '.jsonl')
        events.parent.mkdir(exist_ok=True)
        progress_path = root / 'request_progress' / (job['id'] + '.json')
        def progress(chars):
            write_json(progress_path, {'id': job['id'], 'characters_received': chars, 'updated_at': time.time()})
        try:
            with OpenAI(api_key=key, base_url=get_base_url('deepseek'), max_retries=0,
                        timeout=httpx.Timeout(3600, connect=30)) as client:
                with events.open('x', encoding='utf-8') as sink:
                    with client.chat.completions.create(
                        model=spec['model'], messages=[{'role':'user', 'content':spec['prompt']}],
                        temperature=spec['temperature'], max_tokens=spec['max_tokens'],
                        reasoning_effort=spec['reasoning_effort'], extra_body=spec['extra_body'],
                        stream=True, stream_options=spec['stream_options']) as stream:
                        response = stream.response
                        record['response_metadata'] = {
                            'http_status':response.status_code, 'http_version':response.http_version,
                            'opened_at':time.time(),
                            'headers':{k:response.headers[k] for k in
                                       ('x-request-id', 'request-id', 'content-type', 'transfer-encoding')
                                       if k in response.headers}}
                        write_json(path, record)
                        result = receive_stream(stream, sink, progress)
            record.update(result, status='received', finished_at=time.time())
            write_json(path, record)
        except Exception as exc:
            # Store only safe error metadata, never request headers or credentials.
            error = {'error_type': type(exc).__name__, 'http_status': getattr(exc, 'status_code', None)}
            error['exception_chain'] = transport_diagnostics(exc, key)
            body = getattr(exc, 'body', None)
            if isinstance(body, dict) and isinstance(body.get('error'), dict):
                error['provider_error'] = {k:body['error'].get(k) for k in ('type', 'code', 'message')}
            record.update(error, status='api_error', finished_at=time.time())
            write_json(path, record)
            raise RuntimeError('Request failed; saved metadata for ' + job['id']) from None
    if not record.get('reasoning_content'):
        raise RuntimeError('No native reasoning evidence; stop dispatch and inspect ' + job['id'])
    if record.get('returned_model') != 'deepseek-flash':
        raise RuntimeError('Unexpected returned model; inspect before continuing')
    policy = validate(record, job['id'], cfg_for(job['seed']))
    write_json(path, record)
    write_json(out, {**job, 'child': asdict(policy) if policy else None,
                    'parent_key': Policy(**c['parent']).key, 'valid': policy is not None})
    return {'id':job['id'], 'valid':policy is not None, 'reasoning_chars':len(record['reasoning_content']),
            'finish_reason':record['finish_reason'], 'usage':record['usage']}
