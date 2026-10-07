"""Native model request settings, streaming and candidate validation."""
from dataclasses import asdict
from pathlib import Path
import time
from .thinking_control import transport_diagnostics, validate, receive_stream

from .core import Policy
from .specificity import cfg_for
from .records import read_json, write_json, cached_request, begin_request

SOURCE = Path('results/feedback_specificity_v2')
DEFAULT_ROOT = Path('results/qwen3_8')
MODEL = 'qwen3.8-flash'
LIMITS = {'off': 6000, 'on': 131072}


def mode_for(root):
    mode = Path(root).name
    if mode not in LIMITS or Path(root).parent.name != 'qwen3_8':
        raise ValueError('Use results/qwen3_8/off or results/qwen3_8/on')
    return mode


def specification(prompt, mode):
    spec = dict(provider='qwen', model=MODEL, prompt=prompt,
                temperature=1, max_tokens=LIMITS[mode],
                extra_body={'enable_thinking': mode == 'on'},
                stream=True, stream_options={'include_usage': True})
    if mode == 'on':
        spec['reasoning_effort'] = 'high'
    return spec


def generate_one(arg):
    root, job = arg
    root = Path(root)
    mode = mode_for(root)
    out = root / 'candidates' / (job['id'] + '.json')
    if out.exists():
        return {'id': job['id'], 'cached': True}
    c = read_json(root / 'contexts' / (job['context'] + '.json'))
    spec = specification(c['prompts'][job['arm']], mode)
    path = root / 'requests_candidates' / (job['id'] + '.json')
    record = cached_request(path, spec)
    if record is None:
        from openai import OpenAI
        import httpx
        from ..config.load_env import get_api_key, get_base_url
        key = get_api_key('qwen')
        if not key:
            raise RuntimeError('Provider not configured')
        record = begin_request(path, spec)
        events = root / 'streams' / (job['id'] + '.jsonl')
        events.parent.mkdir(exist_ok=True)
        progress_path = root / 'request_progress' / (job['id'] + '.json')
        def progress(chars):
            write_json(progress_path, {'id': job['id'], 'characters_received': chars, 'updated_at': time.time()})
        try:
            with OpenAI(api_key=key, base_url=get_base_url('qwen'), max_retries=0,
                        timeout=httpx.Timeout(3600, connect=30)) as client:
                with events.open('x', encoding='utf-8') as sink:
                    request = dict(model=spec['model'], messages=[{'role':'user', 'content':spec['prompt']}],
                                   temperature=spec['temperature'], max_tokens=spec['max_tokens'],
                                   extra_body=spec['extra_body'], stream=True,
                                   stream_options=spec['stream_options'])
                    if mode == 'on':
                        request['reasoning_effort'] = spec['reasoning_effort']
                    with client.chat.completions.create(**request) as stream:
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
    if mode == 'on' and not record.get('reasoning_content'):
        raise RuntimeError('No native reasoning evidence; stop dispatch and inspect ' + job['id'])
    if record.get('returned_model') != MODEL:
        raise RuntimeError('Unexpected returned model; inspect before continuing')
    policy = validate(record, job['id'], cfg_for(job['seed']))
    write_json(path, record)
    write_json(out, {**job, 'child': asdict(policy) if policy else None,
                    'parent_key': Policy(**c['parent']).key, 'valid': policy is not None})
    return {'id':job['id'], 'valid':policy is not None, 'reasoning_chars':len(record['reasoning_content']),
            'finish_reason':record['finish_reason'], 'usage':record['usage']}
