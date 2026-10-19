"""Audit and summarize complete paired Qwen experiment batches."""
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
from .holdout_metrics import audit_deltas

def audit(root, manifest):
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
        expected = specification(context['prompts'][job['arm']], 'qwen', manifest['mode'],
                                 model=manifest['api']['model'])
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
        issues.extend(audit_deltas(holdout, parent, identity))
        rows.append(request)
    return {'issues': issues, 'requests': len(rows), 'valid': sum(row['status'] == 'valid' for row in rows),
            'truncated': sum(row.get('finish_reason') == 'length' for row in rows),
            'reasoning_characters': sum(len(row.get('reasoning_content') or '') for row in rows)}


def analyze(input_root=ROOT, output_suffix=""):
    input_root = Path(input_root)
    manifests = {mode: read_json(input_root / mode / 'manifest.json') for mode in ('off', 'on')}
    model = manifests['off']['api']['model']
    if manifests['on']['api']['model'] != model:
        raise ValueError('Qwen OFF and ON manifests must use the same model')
    reports = {}
    for mode in ('off', 'on'):
        root = input_root / mode
        manifest = manifests[mode]
        reports[mode] = {'result': aggregate(root, manifest)}
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
    summary = {'model': model, 'modes': reports, 'focus': focus,
               'limitation': 'Thinking and max_tokens differ between modes; H was already used historically.'}
    write_json(input_root / f'ANALYSIS{output_suffix}.json', summary)
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--output-suffix', default='')
    parser.add_argument('--audit-only', action='store_true', help='Run optional record audits instead of analysis.')
    parser.add_argument('--audit-output', type=Path, help='Explicit destination for the optional audit JSON.')
    args = parser.parse_args()
    if args.audit_only:
        if args.audit_output is None:
            parser.error('--audit-only requires --audit-output')
        reports = {mode: audit(args.root / mode,
                              read_json(args.root / mode / 'manifest.json'))
                   for mode in ('off', 'on')}
        write_json(args.audit_output, reports)
        print(json.dumps(reports))
    else:
        if args.audit_output is not None:
            parser.error('--audit-output requires --audit-only')
        analyze(args.root, args.output_suffix)
