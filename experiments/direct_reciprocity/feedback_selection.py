"""Exploratory frozen-parent selection using training fitness only.

This is a post hoc selection diagnostic, not the primary one-step estimand,
nor an actual multi-generation population experiment. No API calls.
"""
from collections import defaultdict
from pathlib import Path
from statistics import mean
import argparse

from .core import Policy
from .feedback import ARMS
from .feedback_analysis import interval, sign_flip_p
from .run import read_json, write_json


def analyze(root):
    root = Path(root)
    groups = defaultdict(list)
    for path in (root / 'outcomes').glob('*.json'):
        row = read_json(path)
        groups[(row['context'], row['arm'])].append(row)
    selected = []
    for (context, arm), rows in sorted(groups.items()):
        if len(rows) != 2:
            continue
        baseline = read_json(root / 'parents' / (context + '.json'))
        valid = [r for r in rows if r['valid'] and not r['fallback']['training']]
        winner = min(valid, key=lambda r: (-r['deployed']['training']['score'], Policy(**r['child']).key, r['id'])) if valid else None
        accept = winner is not None and winner['deployed']['training']['score'] > baseline['training']['score']
        selected.append({'context': context, 'seed': rows[0]['seed'], 'arm': arm,
                         'accepted': accept, 'winner': winner['id'] if accept else 'parent',
                         'delta': {s: winner['delta'][s]['score'] if accept else 0.0
                                   for s in ('training', 'default', 'noise01', 'long')}})
    summaries = {}
    for arm in ARMS:
        cells = [r for r in selected if r['arm'] == arm]
        raw = [r for (cid, a), rows in groups.items() if a == arm for r in rows]
        summaries[arm] = {'contexts': len(cells), 'accepted': sum(r['accepted'] for r in cells),
                          'raw_training_improvements': sum(r['delta']['training']['score'] > 0 for r in raw),
                          'raw_default_improvements': sum(r['delta']['default']['score'] > 0 for r in raw),
                          'training_up_default_down': sum(r['delta']['training']['score'] > 0 and r['delta']['default']['score'] < 0 for r in raw),
                          'metrics': {}}
        for setting in ('training', 'default', 'noise01', 'long'):
            seeds = {str(seed): mean(r['delta'][setting] for r in cells if r['seed'] == seed)
                     for seed in range(5) if sum(r['seed'] == seed for r in cells) == 3}
            summaries[arm]['metrics'][setting] = {'seed_means': seeds, 'mean': mean(seeds.values()) if seeds else None}
    comparisons = []
    for a, b in [('true', 'shuffled'), ('true', 'hidden'), ('diagnostic', 'true')]:
        left, right = summaries[a]['metrics']['default']['seed_means'], summaries[b]['metrics']['default']['seed_means']
        deltas = [left[s] - right[s] for s in sorted(left.keys() & right.keys())]
        comparisons.append({'comparison': a + '-' + b, 'seed_differences': deltas,
                            'mean': mean(deltas) if deltas else None,
                            'ci95': interval(deltas), 'exact_sign_flip_p': sign_flip_p(deltas)})
    result = {'complete': len(selected) == 60, 'selected': selected, 'arms': summaries,
              'comparisons': comparisons,
              'note': 'Post hoc; keep parent unless best of two proposals has strictly higher training fitness; holdout never selects. Not multi-generation evolution.'}
    write_json(root / 'SELECTION_ANALYSIS.json', result)
    print({'selection_contexts': len(selected), 'complete': result['complete']})
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', nargs='?', default='results/feedback_attribution_v1')
    analyze(parser.parse_args().root)
