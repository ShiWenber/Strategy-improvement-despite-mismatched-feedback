"""Exploratory child behavior on the same controlled probes used for feedback.

These are training-probe responses, not an independent measure of generalization.
This post-processing was added while the fixed 120-request batch was running.
"""
from collections import defaultdict
from pathlib import Path
from statistics import mean
import argparse

from .core import Config, Policy
from .feedback import behavior_diagnostics, ARMS
from .run import read_json, write_json


def analyze(root):
    root = Path(root)
    rows = []
    for path in sorted((root / 'outcomes').glob('*.json')):
        row = read_json(path)
        target = root / 'behavior' / path.name
        if target.exists():
            rows.append(read_json(target))
            continue
        context = read_json(root / 'contexts' / (row['context'] + '.json'))
        result = {'id': row['id'], 'seed': row['seed'], 'arm': row['arm'],
                  'valid': row['valid'], 'delta': {}, 'status': 'ok'}
        try:
            child = behavior_diagnostics(Policy(**row['child']), Config(**context['cfg'])) if row['valid'] else context['diagnostic']
            result['child'] = child
            for scenario, fields in child.items():
                result['delta'][scenario] = {k: v - context['diagnostic'][scenario][k] for k, v in fields.items()}
        except Exception as exc:
            result.update(status='failed', error_type=type(exc).__name__)
        write_json(target, result)
        rows.append(result)
    summary = {}
    for arm in ARMS:
        data = [r for r in rows if r['arm'] == arm]
        metrics = defaultdict(lambda: defaultdict(list))
        for row in data:
            if row['status'] == 'ok':
                for scenario, fields in row['delta'].items():
                    for key, value in fields.items():
                        metrics[scenario + '/' + key][str(row['seed'])].append(value)
        summary[arm] = {'n': len(data), 'failures': sum(r['status'] != 'ok' for r in data), 'metrics': {}}
        for key, seeds in metrics.items():
            cluster_means = {s: mean(v) for s, v in seeds.items() if len(v) == 6}
            summary[arm]['metrics'][key] = {'seed_means': cluster_means,
                                          'mean': mean(cluster_means.values()) if cluster_means else None}
    result = {'outcomes': len(rows), 'arms': summary,
              'note': 'Exploratory post-processing on feedback probes; not held-out behavior. Invalid proposals retain parent.'}
    write_json(root / 'BEHAVIOR_ANALYSIS.json', result)
    print({'behavior_outcomes': len(rows), 'failures': sum(r['status'] != 'ok' for r in rows)})
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', nargs='?', default='results/feedback_attribution_v1')
    analyze(parser.parse_args().root)
