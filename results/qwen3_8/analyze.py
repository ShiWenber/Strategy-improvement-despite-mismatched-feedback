"""Audit and summarize complete paired Qwen3.8-Flash experiment batches."""
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parent
WORKSPACE = ROOT.parents[1]
sys.path.insert(0, str(WORKSPACE))

from experiments.direct_reciprocity.core import Policy, digest
from experiments.direct_reciprocity.qwen38_control import SOURCE, filehash, specification, verify
from experiments.direct_reciprocity.run import read_json, write_json
from experiments.direct_reciprocity.specificity_analysis import contrast, holm
from thinking_control_analysis import aggregate


def audit(root, manifest):
    root = Path(root)
    read_json(root / 'COMPLETE.json')
    selections = read_json(root / 'SELECTIONS_SEALED.json')
    release = read_json(root / 'H_RELEASED.json')
    issues = []
    if len(selections['rows']) != len(manifest['jobs']) // manifest['draws'] * 3:
        issues.append('Sealed selection count differs from manifest')
    if release['selection_digest'] != digest((root / 'SELECTIONS_SEALED.json').read_text(encoding='utf-8')):
        issues.append('H released against wrong selection seal')
    rows = []
    for job in manifest['jobs']:
        identity = job['id']
        context = read_json(root / 'contexts' / (job['context'] + '.json'))
        request = read_json(root / 'requests_candidates' / (identity + '.json'))
        candidate = read_json(root / 'candidates' / (identity + '.json'))
        holdout = read_json(root / 'holdout' / (identity + '.json'))
        parent = read_json(root / 'holdout' / (job['context'] + '.json'))
        expected = specification(context['prompts'][job['arm']], manifest['mode'])
        if any(request.get(key) != value for key, value in expected.items()):
            issues.append(identity + ': request specification differs')
        if request.get('fingerprint') != digest(json.dumps(expected, sort_keys=True)):
            issues.append(identity + ': request fingerprint differs')
        if digest(request['prompt']) != manifest['prompt_hashes'][identity]:
            issues.append(identity + ': frozen prompt differs')
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
        if candidate['child'] and Policy(**candidate['child']).key != request.get('code_hash'):
            issues.append(identity + ': candidate differs from response')
        if selections['candidate_hashes'][identity] != digest((root / 'candidates' / (identity + '.json')).read_text(encoding='utf-8')):
            issues.append(identity + ': candidate changed after selection')
        if filehash(root / 'holdout' / (job['context'] + '.json')) != filehash(SOURCE / 'holdout' / (job['context'] + '.json')):
            issues.append(identity + ': parent H changed')
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


def analyze():
    reports = {}
    for mode in ('off', 'on'):
        root = ROOT / mode
        manifest = read_json(root / 'manifest.json')
        aud = audit(root, manifest)
        write_json(root / 'AUDIT.json', aud)
        if aud['issues']:
            raise RuntimeError(f'{mode}: {len(aud["issues"])} audit issues')
        reports[mode] = {'audit': aud, 'result': aggregate(root, manifest)}
        write_json(root / 'ANALYSIS.json', reports[mode])
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
    write_json(ROOT / 'ANALYSIS.json', summary)
    lines = ['# Qwen3.8-Flash paired replication', '',
             'Same frozen 20 populations, 60 parents and 240 prompts per mode. H was previously used.', '',
             '| Mode | Valid / 240 | Raw Accurate | Raw Mismatched | S3 Accurate | S3 Mismatched | Input tokens | Output tokens | Uncached list cost (CNY) |',
             '| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    for mode in ('off', 'on'):
        report = reports[mode]
        aud, result = report['audit'], report['result']
        raw = [result['raw'][arm]['metrics']['default/score']['mean'] for arm in ('accurate', 'mismatched')]
        s3 = [result['selected']['S3/' + arm]['metrics']['default']['mean'] for arm in ('accurate', 'mismatched')]
        lines.append(f"| {mode} | {aud['valid']} | {raw[0]:+.5f} | {raw[1]:+.5f} | {s3[0]:+.5f} | {s3[1]:+.5f} | {aud['usage']['prompt_tokens']:,} | {aud['usage']['completion_tokens']:,} | {aud['reported_cost_cny_uncached_beijing']:.2f} |")
    lines.extend(['', 'Primary descriptive contrasts (population is the independent unit):', ''])
    for key, value in focus.items():
        lines.append(f"- {key}: raw Accurate − Mismatched {value['mean']:+.5f} payoff per round; Holm p={value['holm_p']:.5f}.")
    lines.extend(['', 'Thinking and output limit differ between modes (6,000 vs 131,072); the mode contrast does not isolate thinking alone. The cost assumes uncached Beijing list prices and can differ from the actual bill.', ''])
    (ROOT / 'REPORT.md').write_text('\n'.join(lines), encoding='utf-8')
    return summary


if __name__ == '__main__':
    analyze()
