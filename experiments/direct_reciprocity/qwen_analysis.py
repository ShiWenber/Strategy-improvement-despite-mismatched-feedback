"""Audit and summarize complete paired Qwen3.8-Flash experiment batches."""
import argparse
import json
from pathlib import Path

import numpy as np

WORKSPACE = Path(__file__).resolve().parents[2]
ROOT = WORKSPACE / 'results/qwen3_8'

from .condition_generation import specification
from .records import read_json, write_json
from .specificity_analysis import contrast, holm
from .thinking_control_analysis import aggregate

SOURCE = Path('results/feedback_specificity_v2')


def audit(root, manifest, source=SOURCE):
    root = Path(root)
    read_json(root / 'COMPLETE.json')
    selections = read_json(root / 'SELECTIONS_SEALED.json')
    issues = []
    if len(selections['rows']) != len(manifest['jobs']) // manifest['draws'] * 3:
        issues.append('Sealed selection count differs from manifest')
    rows = []
    for job in manifest['jobs']:
        identity = job['id']
        context = read_json(root / 'contexts' / (job['context'] + '.json'))
        request = read_json(root / 'requests_candidates' / (identity + '.json'))
        candidate = read_json(root / 'candidates' / (identity + '.json'))
        holdout = read_json(root / 'holdout' / (identity + '.json'))
        parent = read_json(root / 'holdout' / (job['context'] + '.json'))
        expected = specification(context['prompts'][job['arm']], 'qwen', manifest['mode'])
        if any(request.get(key) != value for key, value in expected.items()):
            issues.append(identity + ': request specification differs')
        if request['started_at'] < manifest['frozen_at']:
            issues.append(identity + ': request predates manifest')
        if request.get('returned_model') != manifest['api']['model']:
            issues.append(identity + ': unexpected returned model')
        if manifest['mode'] == 'on' and not request.get('reasoning_content'):
            issues.append(identity + ': no native reasoning content')
        if manifest['mode'] == 'off' and request.get('reasoning_content'):
            issues.append(identity + ': unexpected reasoning content')
        if candidate['valid'] != (request['status'] == 'valid'):
            issues.append(identity + ': validity mismatch')
        for setting in ('default', 'noise01', 'long'):
            for metric in ('score', 'cooperation', 'worst_score'):
                delta = holdout['deployed'][setting][metric] - parent['measured'][setting][metric]
                if abs(delta - holdout['delta'][setting][metric]) > 1e-10:
                    issues.append(identity + ': H delta arithmetic')
                if holdout['fallback'][setting] and abs(delta) > 1e-10:
                    issues.append(identity + ': fallback arithmetic')
        rows.append(request)
    usage = {key: sum((row.get('usage') or {}).get(key, 0) or 0 for row in rows)
             for key in ('prompt_tokens', 'completion_tokens', 'total_tokens')}
    return {'issues': issues, 'requests': len(rows), 'valid': sum(row['status'] == 'valid' for row in rows),
            'truncated': sum(row.get('finish_reason') == 'length' for row in rows),
            'usage_missing': sum(row.get('usage') is None for row in rows), 'usage': usage,
            'reasoning_characters': sum(len(row.get('reasoning_content') or '') for row in rows),
            'reported_cost_cny_uncached_beijing':
                .8 * usage['prompt_tokens'] / 1e6 + 2.7 * usage['completion_tokens'] / 1e6}


def analyze(input_root=ROOT, source=SOURCE, output_suffix=""):
    input_root = Path(input_root)
    reports = {}
    for mode in ('off', 'on'):
        root = input_root / mode
        manifest = read_json(root / 'manifest.json')
        aud = audit(root, manifest, source)
        write_json(root / f'AUDIT{output_suffix}.json', aud)
        if aud['issues']:
            raise RuntimeError(f'{mode}: {len(aud["issues"])} audit issues')
        reports[mode] = {'audit': aud, 'result': aggregate(root, manifest)}
        write_json(root / f'ANALYSIS{output_suffix}.json', reports[mode])
    def vector(mode, arm):
        return np.asarray(reports[mode]['result']['raw'][arm]['metrics']['default/score']['seed_values'])
    focus = {mode: contrast(vector(mode, 'accurate') - vector(mode, 'mismatched'))
             for mode in ('off', 'on')}
    focus['on_minus_off'] = contrast((vector('on', 'accurate') - vector('on', 'mismatched'))
                                     - (vector('off', 'accurate') - vector('off', 'mismatched')))
    adjusted = holm({key: value['sign_swap_p'] for key, value in focus.items()})
    for key, value in focus.items():
        value['holm_p'] = adjusted[key]
    summary = {'model': 'qwen3.8-flash', 'modes': reports, 'focus': focus,
               'limitation': 'Thinking and max_tokens differ between modes; H was already used historically.'}
    write_json(input_root / f'ANALYSIS{output_suffix}.json', summary)
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--source', type=Path, default=SOURCE)
    parser.add_argument('--output-suffix', default='')
    args = parser.parse_args()
    analyze(args.root, args.source, args.output_suffix)
