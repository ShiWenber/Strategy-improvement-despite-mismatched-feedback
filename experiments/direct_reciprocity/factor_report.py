"""Paired prompt/selection comparisons across every held-out endpoint metric."""
import argparse
from pathlib import Path
from statistics import mean

from .analyze import interval
from .run import read_json, write_json


def report(root):
    root = Path(root)
    analysis = read_json(root / 'analysis.json')
    groups = {}
    for row in analysis['endpoints']:
        groups.setdefault((row['prompt'], row['selection']), {})[row['seed']] = row
    comparisons = []
    for selection in ('paper_truncation',):
        for prompt in ('score', 'full'):
            comparisons.append(((prompt, selection), ('minimal', selection)))
    metrics = [f'{setting}_{metric}' for setting in ('default', 'noise01', 'long')
               for metric in ('score', 'cooperation', 'worst_score')]
    records = []
    for left_key, right_key in comparisons:
        left, right = groups.get(left_key, {}), groups.get(right_key, {})
        shared = sorted(set(left) & set(right))
        for metric in metrics:
            successful = [s for s in shared
                          if left[s][metric] is not None and right[s][metric] is not None]
            differences = [left[s][metric] - right[s][metric] for s in successful]
            records.append({
                'left': list(left_key), 'right': list(right_key), 'metric': metric,
                'available_paired_seeds': shared, 'successful_paired_seeds': successful,
                'left_missing_test_seeds': [s for s in shared if left[s][metric] is None],
                'right_missing_test_seeds': [s for s in shared if right[s][metric] is None],
                'differences': differences, 'mean': mean(differences) if differences else None,
                'bootstrap95': interval(differences),
            })
    result = {'all_main_cells_complete': analysis['all_main_cells_complete'],
              'endpoint_count': len(analysis['endpoints']), 'contrasts': records,
              'note': 'Left minus right; seed is the unit. Exploratory unadjusted 95% bootstrap intervals with at most five seeds. Missing tests are excluded pairwise, never zero-filled. Equal generations do not match calls/tokens; this estimates workflow effects, not an isolated mechanism effect.'}
    write_json(root / 'FACTOR_COMPARISONS.json', result)
    print(f"Endpoints: {result['endpoint_count']}; contrasts: {len(records)}")
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('root', type=Path)
    report(parser.parse_args().root)
