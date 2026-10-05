"""Re-execute identity-selected policies with the project simulator, without APIs."""
import argparse
from concurrent.futures import ProcessPoolExecutor
import json
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--full', action='store_true', help='Replay all default-H parent/candidate records; may take many hours')
    a = parser.parse_args()
    sys.path.insert(0, str(a.work))
    from experiments.direct_reciprocity.specificity_supplement import replay_job
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
    print(json.dumps({'records': len(records), 'games_replayed': result['games_replayed'], 'max_abs_error': result['max_abs_error']}))


if __name__ == '__main__':
    main()
