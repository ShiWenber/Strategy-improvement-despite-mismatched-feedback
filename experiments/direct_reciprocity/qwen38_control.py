"""Paired Qwen3.8-Flash replication over the frozen direct-reciprocity inputs."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, wait, FIRST_COMPLETED
from dataclasses import asdict, replace
import hashlib
import json
import os
from pathlib import Path
import shutil
import time
import traceback

from .core import Policy, digest, match
from .baselines import TRAIN
from .run import read_json, write_json
from .specificity import (check_manifest, source_hash, cfg_for, evaluation_job,
                          seal_selections, holdout_job)

SOURCE = Path('results/feedback_specificity_v2')
DEFAULT_ROOT = Path('results/qwen3_8')
MODEL = 'qwen3.8-flash'
LIMITS = {'off': 6000, 'on': 131072}


def mode_for(root):
    mode = Path(root).name
    if mode not in LIMITS or Path(root).parent.name != 'qwen3_8':
        raise ValueError('Use results/qwen3_8/off or results/qwen3_8/on')
    return mode


def filehash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


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


def specification(prompt, mode):
    spec = dict(provider='qwen', model=MODEL, prompt=prompt,
                temperature=1, max_tokens=LIMITS[mode],
                extra_body={'enable_thinking': mode == 'on'},
                stream=True, stream_options={'include_usage': True})
    if mode == 'on':
        spec['reasoning_effort'] = 'high'
    return spec


def prepare(root):
    root = Path(root)
    mode = mode_for(root)
    old = check_manifest(SOURCE)
    read_json(SOURCE / 'COMPLETE.json')
    if (root / 'manifest.json').exists():
        return verify(root)
    if root.exists() and any(root.iterdir()):
        raise RuntimeError('Nonempty unsealed destination; inspect before preparing')
    root.mkdir(parents=True, exist_ok=True)
    copied = {}
    for folder in ('contexts', 'populations'):
        for src in sorted((SOURCE / folder).glob('*.json')):
            dst = root / folder / src.name
            dst.parent.mkdir(exist_ok=True)
            shutil.copyfile(src, dst)
            copied[str(dst.relative_to(root))] = filehash(src)
    for cid in sorted({j['context'] for j in old['jobs']}):
        src = SOURCE / 'selection_scores' / (cid + '.json')
        dst = root / 'selection_scores' / src.name
        dst.parent.mkdir(exist_ok=True)
        shutil.copyfile(src, dst)
        copied[str(dst.relative_to(root))] = filehash(src)
    protocol = (DEFAULT_ROOT / 'PROTOCOL.md').read_text(encoding='utf-8')
    (root / 'PROTOCOL.md').write_text(protocol, encoding='utf-8')
    manifest = dict(version='qwen3.8-flash-v1', mode=mode, source=str(SOURCE.resolve()),
                    source_manifest_hash=filehash(SOURCE / 'manifest.json'),
                    implementation_hash=source_hash(), runner_hash=filehash(__file__),
                    protocol_hash=filehash(root / 'PROTOCOL.md'), reused_file_hashes=copied,
                    jobs=old['jobs'], seeds=old['seeds'], arms=old['arms'],
                    ranks=old['ranks'], draws=old['draws'], config=old['config'],
                    frozen_at=time.time(), new_calls=600, reused_initial_calls=240,
                    api={k:v for k,v in specification('', mode).items() if k != 'prompt'},
                    comparison='same frozen populations and prompts; Qwen modes differ in thinking and supported output limits')
    prompts = {}
    for job in manifest['jobs']:
        c = read_json(root / 'contexts' / (job['context'] + '.json'))
        prompts[job['id']] = digest(c['prompts'][job['arm']])
    manifest['prompt_hashes'] = prompts
    write_json(root / 'manifest.json', manifest)
    return manifest


def verify(root):
    root = Path(root)
    mode = mode_for(root)
    m = read_json(root / 'manifest.json')
    if m['mode'] != mode:
        raise RuntimeError('Mode identity changed')
    if m['implementation_hash'] != source_hash() or m['runner_hash'] != filehash(__file__):
        raise RuntimeError('Frozen implementation changed')
    if filehash(SOURCE / 'manifest.json') != m['source_manifest_hash']:
        raise RuntimeError('Historical manifest changed')
    if filehash(root / 'PROTOCOL.md') != m['protocol_hash']:
        raise RuntimeError('Frozen protocol changed')
    for rel, expected in m['reused_file_hashes'].items():
        if filehash(root / rel) != expected:
            raise RuntimeError('Reused input changed: ' + rel)
    if m['api'] != {k:v for k,v in specification('', mode).items() if k != 'prompt'}:
        raise RuntimeError('Request configuration changed')
    return m


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
    mode = mode_for(root)
    out = root / 'candidates' / (job['id'] + '.json')
    if out.exists():
        return {'id': job['id'], 'cached': True}
    c = read_json(root / 'contexts' / (job['context'] + '.json'))
    spec = specification(c['prompts'][job['arm']], mode)
    fingerprint = digest(json.dumps(spec, sort_keys=True))
    path = root / 'requests_candidates' / (job['id'] + '.json')
    path.parent.mkdir(exist_ok=True)
    if path.exists():
        record = read_json(path)
        if record['fingerprint'] != fingerprint:
            raise RuntimeError('Request identity collision')
        if record['status'] in ('requested', 'api_error'):
            raise RuntimeError('Uncertain or failed saved request; manual investigation required: ' + job['id'])
    else:
        from openai import OpenAI
        import httpx
        from ..config.load_env import get_api_key, get_base_url
        key = get_api_key('qwen')
        if not key:
            raise RuntimeError('Provider not configured')
        record = dict(spec, fingerprint=fingerprint, status='requested', started_at=time.time())
        # Exclusive creation makes two accidentally concurrent runners fail before duplicate billing.
        with path.open('x', encoding='utf-8') as f:
            json.dump(record, f, ensure_ascii=False, indent=2)
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


def pool(fn, args, workers, root, stage, process=False):
    """Bounded submissions, durable heartbeat, drain in-flight work on first error."""
    started = time.time()
    iterator = iter(args)
    active, errors, done = {}, [], 0
    cls = ProcessPoolExecutor if process else ThreadPoolExecutor
    with cls(max_workers=workers) as executor:
        def submit():
            try:
                item = next(iterator)
            except StopIteration:
                return False
            active[executor.submit(fn, item)] = item
            return True
        for _ in range(workers):
            if not submit(): break
        while active:
            ready, _ = wait(active, timeout=20, return_when=FIRST_COMPLETED)
            for future in ready:
                item = active.pop(future)
                try:
                    result = future.result()
                    done += 1
                    print(json.dumps({'stage':stage, 'done':done, 'total':len(args), 'result':result}), flush=True)
                except Exception as exc:
                    errors.append({'task':str(item)[:500], 'type':type(exc).__name__, 'message':str(exc)[:500]})
            write_json(Path(root) / 'EXECUTION_STATUS.json', dict(stage=stage, completed=done,
                       total=len(args), active=len(active), errors=errors, started_at=started, updated_at=time.time()))
            if not errors:
                while len(active) < workers and submit(): pass
    if errors:
        raise RuntimeError(stage + ' stopped after errors; inspect EXECUTION_STATUS.json')


def release_parents(root, m):
    root = Path(root)
    seal_selections(root, m)
    write_json(root / 'H_RELEASED.json', {'selection_digest':digest((root / 'SELECTIONS_SEALED.json').read_text(encoding='utf-8')),
                                         'released_at':time.time(), 'historical_test_panel':True})
    copied = {}
    for cid in sorted({j['context'] for j in m['jobs']}):
        src = SOURCE / 'holdout' / (cid + '.json')
        dst = root / 'holdout' / src.name
        dst.parent.mkdir(exist_ok=True)
        if dst.exists() and filehash(dst) != filehash(src):
            raise RuntimeError('Parent test record changed')
        shutil.copyfile(src, dst)
        copied[cid] = filehash(src)
    write_json(root / 'REUSED_PARENT_H.json', copied)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('stage', choices=['prepare','first','all','select','holdout'])
    p.add_argument('--output', required=True)
    p.add_argument('--api-workers', type=int, default=12)
    p.add_argument('--workers', type=int, default=24)
    p.add_argument('--env-file', default='../../.env')
    a = p.parse_args()
    from dotenv import load_dotenv
    load_dotenv(a.env_file, override=False)
    root = Path(a.output)
    if a.stage == 'prepare':
        m = prepare(root)
        print(json.dumps({'prepared':str(root), 'requests':len(m['jobs']), 'api':m['api']}))
        return
    m = verify(root)
    # A held file lock disallows concurrent mutation of a batch, and auto-releases on process exit.
    lockpath = root / 'RUNNER.lock'
    lock = lockpath.open('a+b')
    lock.seek(0)
    if os.name == 'nt':
        import msvcrt
        if lockpath.stat().st_size == 0:
            lock.write(b'0'); lock.flush(); lock.seek(0)
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    write_json(root / 'PROCESS.json', {'pid':os.getpid(), 'stage':a.stage, 'started_at':time.time()})
    try:
        if a.stage == 'first':
            result = generate_one((str(root), m['jobs'][0]))
            write_json(root / 'FIRST_REQUEST_CHECK.json', {'completed':True, 'result':result})
            print(json.dumps(result), flush=True)
            return
        if a.stage == 'all':
            read_json(root / 'FIRST_REQUEST_CHECK.json')
            pool(generate_one, [(str(root),j) for j in m['jobs']], a.api_workers, root, 'generate')
        if a.stage in ('all','select'):
            verify(root)
            for j in m['jobs']: read_json(root / 'candidates' / (j['id']+'.json'))
            pool(evaluation_job, [(str(root),'child',j['id']) for j in m['jobs']], a.workers, root, 'select', True)
            seal_selections(root, m)
        if a.stage in ('all','holdout'):
            verify(root)
            release_parents(root, m)
            pool(holdout_job, [(str(root),'child',j['id']) for j in m['jobs']], a.workers, root, 'holdout', True)
            write_json(root / 'COMPLETE.json', {'completed_at':time.time(), 'candidates':600,
                       'contexts':60, 'new_initial_calls':0, 'implementation_hash':source_hash()})
    finally:
        lock.close()


if __name__ == '__main__':
    main()
