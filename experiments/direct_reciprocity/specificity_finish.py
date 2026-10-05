"""Local continuation of the already-running frozen batch; never invokes an API."""
import argparse
import json
import os
from pathlib import Path
import time

from .run import read_json, write_json
from .specificity import check_manifest
from .specificity_parallel_tail import run as parallel_tail
from .specificity_analysis import analyze
from .specificity_supplement import supplement
from .plot_specificity import plot


def snapshot(path):
    """Read atomically replaced status files without blocking Windows rename."""
    try:
        if os.name != 'nt':
            return read_json(path)
        import ctypes
        from ctypes import wintypes
        import msvcrt
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        create = kernel.CreateFileW
        create.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                           wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        create.restype = wintypes.HANDLE
        handle = create(str(Path(path).resolve()), 0x80000000, 0x1 | 0x2 | 0x4, None, 3, 0x80, None)
        if handle == ctypes.c_void_p(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        fd = msvcrt.open_osfhandle(handle, os.O_RDONLY)
        with os.fdopen(fd, 'rb') as stream:
            return json.loads(stream.read().decode('utf-8-sig'))
    except (PermissionError, FileNotFoundError):
        return None


def finish(root):
    root = Path(root)
    manifest = check_manifest(root)
    contexts = {j['context'] for j in manifest['jobs']}
    status_path = root / 'POSTPROCESS_STATUS.json'
    write_json(status_path, {'stage': 'waiting_for_holdout_parent_completion', 'updated_at': time.time(), 'api_calls': 0})
    while True:
        state = snapshot(root / 'EXECUTION_STATUS.json')
        if state is None:
            time.sleep(2)
            continue
        if state.get('errors'):
            raise RuntimeError('Primary runner has errors; do not bypass its stop')
        parallel = root / 'parallel_select' / 'PUBLISH_LOG.json'
        tail = snapshot(parallel)
        tail_ready = tail is not None and tail['completed'] == tail['scheduled']
        parents_ready = (root / 'H_RELEASED.json').exists() and all((root / 'holdout' / (cid + '.json')).exists() for cid in contexts)
        if (root / 'COMPLETE.json').exists():
            break
        if tail_ready and parents_ready:
            write_json(status_path, {'stage': 'parallel_holdout_tail', 'updated_at': time.time(), 'api_calls': 0})
            parallel_tail(root, 'holdout', count=300, workers=24)
            break
        time.sleep(15)
    while not (root / 'COMPLETE.json').exists():
        state = snapshot(root / 'EXECUTION_STATUS.json')
        if state is None:
            time.sleep(2)
            continue
        if state.get('errors'):
            raise RuntimeError('Primary runner has errors; analysis remains gated')
        time.sleep(15)
    write_json(status_path, {'stage': 'audit_and_analysis', 'updated_at': time.time(), 'api_calls': 0})
    result = analyze(root)
    write_json(status_path, {'stage': 'supplement_and_replay', 'updated_at': time.time(), 'api_calls': 0})
    supplement(root)
    write_json(status_path, {'stage': 'figures', 'updated_at': time.time(), 'api_calls': 0})
    plot(root)
    write_json(status_path, {'stage': 'complete', 'updated_at': time.time(), 'api_calls': 0,
                             'primary': result['primary'], 'gate': result['gate']})
    print({'postprocessing': 'complete', 'primary': result['primary'], 'gate': result['gate']}, flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', nargs='?', default='results/feedback_specificity_v2')
    args = parser.parse_args()
    try:
        finish(args.root)
    except Exception as exc:
        write_json(Path(args.root) / 'POSTPROCESS_ERROR.json', {'type': type(exc).__name__, 'message': str(exc), 'at': time.time()})
        raise
