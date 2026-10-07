"""Replay archived policies through the experiment simulator, without APIs."""
import argparse
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
import json
from pathlib import Path

from .core import Policy, versus
from .records import read_json
from .specificity import cfg_for
from .specificity_assets import panel



def replay_job(arg):
    root, kind, identity = arg
    root = Path(root)
    row = read_json(root / ('contexts' if kind == 'parent' else 'candidates') / (identity + '.json'))
    c = row if kind == 'parent' else read_json(root / 'contexts' / (row['context'] + '.json'))
    item = c['parent'] if kind == 'parent' else row['child']
    saved = read_json(root / 'holdout' / (identity + '.json'))
    if item is None:
        return {'id': identity, 'kind': kind, 'status': 'invalid_candidate_no_game_replay'}
    try:
        actual = versus(Policy(**item), [p for _, p in panel('H')], replace(cfg_for(c['seed']), repeats=20), 'specificity-H-default')
    except Exception as exc:
        expected = saved['measured']['default']
        return {'id': identity, 'kind': kind, 'status': 'failure_reproduced' if expected['status'] == 'failed' and expected['error_type'] == type(exc).__name__ else 'mismatch',
                'error_type': type(exc).__name__}
    expected = saved['measured']['default']
    errors = {'score': abs(actual['score'] / 100 - expected['score']),
              'cooperation': abs(actual['cooperation'] - expected['cooperation']),
              'worst_score': abs(actual['worst_score'] / 100 - expected['worst_score'])}
    return {'id': identity, 'kind': kind, 'status': 'ok' if max(errors.values()) <= 1e-12 else 'mismatch',
            'errors': errors, 'games_replayed': 240}



def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--full', action='store_true', help='Replay all default-H parent/candidate records; may take many hours')
    a = parser.parse_args()
    roots = ['feedback_specificity_v2', 'feedback_specificity_thinking_384k_20260923', 'qwen3_8/off', 'qwen3_8/on']
    tasks = []
    for relative in roots:
        root = a.work / 'results' / relative
        manifest = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
        parents = sorted({j['context'] for j in manifest['jobs']})
        tasks += [(str(root), 'parent', cid) for cid in (parents if a.full else parents[:1])]
        for arm in manifest['arms']:
            children = sorted(j['id'] for j in manifest['jobs'] if j['arm'] == arm)
            tasks += [(str(root), 'child', identity) for identity in (children if a.full else children[:1])]
    with ProcessPoolExecutor(max_workers=a.workers) as pool:
        values = list(pool.map(replay_job, tasks))
    records = [{'configuration': Path(task[0]).relative_to(a.work / 'results').as_posix(), **value} for task, value in zip(tasks, values)]
    result = {'scope': 'All default-H records' if a.full else 'First lexicographic parent and first candidate in each arm, in each of four configurations',
              'simulator': 'project simulator; not an independent implementation',
              'records': records, 'games_replayed': sum(r.get('games_replayed', 0) for r in records),
              'live_api_calls': 0, 'max_abs_error': max((max(r['errors'].values()) for r in records if 'errors' in r), default=0)}
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    if result['max_abs_error'] > 1e-12 or any(r['status'] not in ('ok', 'invalid_candidate_no_game_replay') for r in records):
        raise RuntimeError('Game replay differs from recorded results; inspect ' + str(a.output))
    print(json.dumps({'records': len(records), 'games_replayed': result['games_replayed'], 'max_abs_error': result['max_abs_error']}))



if __name__ == '__main__':
    main()
