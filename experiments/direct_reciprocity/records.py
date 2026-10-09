"""Durable records for experiment workflows."""
from contextlib import contextmanager
from dataclasses import asdict
import json
import hashlib
import os
from pathlib import Path
import time


def digest(text):
    """Stable internal identity for deterministic policy and seed generation."""
    return hashlib.sha256(text.encode('utf-8')).hexdigest()

def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    temp = path.with_suffix(path.suffix+'.tmp')
    temp.write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding='utf-8')
    temp.replace(path)


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def request_budget(paths, generation=None):
    import json
    records=[]
    for directory in paths:
        for path in Path(directory).glob('*.json'):
            if generation is not None and path.name.startswith('g') and path.name[1:4].isdigit() and int(path.name[1:4]) > generation:
                continue
            record=json.loads(path.read_text(encoding='utf-8-sig'))
            records.append(record)
    return {'requests':len(records),'valid':sum(r['status']=='valid' for r in records),
            'invalid':sum(r['status']=='invalid' for r in records),
            'api_errors':sum(r['status']=='api_error' for r in records),
            'unknown_usage':sum(r.get('usage') is None for r in records),
            'total_tokens':sum((r.get('usage') or {}).get('total_tokens',0) for r in records),
            'prompt_tokens':sum((r.get('usage') or {}).get('prompt_tokens',0) for r in records),
            'completion_tokens':sum((r.get('usage') or {}).get('completion_tokens',0) for r in records)}


def population_root(root, manifest=None):
    """Read reused initialization in place without issuing a new request."""
    root = Path(root)
    manifest = manifest or read_json(root / 'manifest.json')
    if 'initial_source' not in manifest:
        return root
    source = (root / manifest['initial_source']).resolve()
    return source


def check_manifest(root):
    manifest = read_json(Path(root) / 'manifest.json')
    if 'archive_projection' in manifest:
        raise RuntimeError('Historical archive is read-only; freeze a new output directory and reuse its initialization with --source')
    population_root(root, manifest)
    return manifest


def initial_identity(cfg, provider, model):
    return f'{provider}-{model}-{cfg.seed}'


def configure_run(directory, cfg, provider, model, initial_source, train, test):
    path = Path(directory) / 'config.json'
    metadata = {'initial_source': str(Path(initial_source).resolve()) if initial_source else None,
                'config': asdict(cfg),
                'provider': provider, 'model': model,
                'baseline_train': [asdict(p) for p in train], 'baseline_test': [asdict(p) for p in test]}
    if path.exists() and read_json(path) != metadata:
        raise RuntimeError('Existing run configuration differs')
    write_json(path, metadata)
    return metadata


def cached_request(path, specification):
    path = Path(path)
    if not path.exists():
        return None
    record = read_json(path)
    if record['status'] in ('requested', 'api_error'):
        raise RuntimeError('Uncertain or failed saved request; inspect ' + str(path))
    return record


def begin_request(path, specification):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    record = dict(specification, status='requested', started_at=time.time())
    with path.open('x', encoding='utf-8') as stream:
        json.dump(record, stream, ensure_ascii=False, indent=2)
    return record


def release_holdout(root, **metadata):
    root = Path(root)
    write_json(root / 'H_RELEASED.json', {'released_at': time.time(), **metadata})


def require_holdout(root):
    root = Path(root)
    if not (root / 'H_RELEASED.json').exists():
        raise RuntimeError('Holdout not released')


def complete(root, **counts):
    write_json(Path(root) / 'COMPLETE.json', dict(completed_at=time.time(), **counts))


@contextmanager
def runner_lock(root, stage):
    path = Path(root) / 'RUNNER.lock'
    with path.open('a+b') as handle:
        if path.stat().st_size == 0:
            handle.write(b'0')
            handle.flush()
        handle.seek(0)
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        write_json(Path(root) / 'PROCESS.json', dict(pid=os.getpid(), stage=stage, started_at=time.time()))
        try:
            yield
        finally:
            if os.name == 'nt':
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)
