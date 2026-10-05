"""Export the current manuscript's compact numeric tables from full-precision JSON."""
import argparse
import csv
import json
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    a = parser.parse_args()
    a.output.mkdir(parents=True, exist_ok=True)

    def read(rel):
        return json.loads((a.work / rel).read_text(encoding='utf-8-sig'))

    def emit(stem, headers, rows):
        with (a.output / (stem + '.csv')).open('w', newline='', encoding='utf-8') as f:
            csv.writer(f).writerows([headers, *rows])
        lines = ['% Generated from archived full-precision records; current paper numbering.',
                 r'\begin{tabular}{' + 'l' + 'r' * (len(headers) - 1) + '}',
                 r'\toprule', ' & '.join(headers) + r' \\', r'\midrule']
        lines += [' & '.join(map(str, row)) + r' \\' for row in rows]
        lines += [r'\bottomrule', r'\end{tabular}', '']
        (a.output / (stem + '.tex')).write_text('\n'.join(lines), encoding='utf-8')

    def ci(row):
        return f"{row['mean']:+.5f} [{row['ci95'][0]:+.5f}, {row['ci95'][1]:+.5f}]"

    off = read('results/feedback_specificity_v2/ANALYSIS.json')
    rows = [['Raw Accurate - Mismatched (primary)', f"{off['primary']['sign_swap_p']:.6f}", '---']]
    for key, label in [('raw_accurate-score', 'Raw Accurate - Score'),
                       ('raw_accurate-background', 'Raw Accurate - Background'),
                       ('raw_accurate-cooperation', 'Raw Accurate - Cooperation'),
                       ('S3_accurate-score', 'S3 Accurate - Score'),
                       ('S3_accurate-parent', 'S3 Accurate - Parent'),
                       ('selection_interaction', 'Selection interaction S3 - S2')]:
        r = off['secondary'][key]
        rows.append([label, f"{r['sign_swap_p']:.6f}", f"{r['holm_p']:.6f}"])
    emit('tableS2_primary', ['Contrast', 'Raw p', 'Holm p'], rows)
    emit('tableS3_sensitivity', ['Condition', 'Noise 0.01', '200 rounds'],
         [[arm.title(), *[ci(off['raw'][arm]['metrics'][setting + '/score']) for setting in ['noise01', 'long']]] for arm in ['accurate', 'mismatched']])
    post = read('results/interface_focus_revision_20260925/ANALYSIS.json')['thinking_on_accurate_minus_score_posthoc']
    sys.path.insert(0, str(a.work.resolve()))
    import numpy as np
    from experiments.direct_reciprocity.specificity_analysis import contrast, holm
    thinking = read('results/feedback_specificity_thinking_384k_20260923/ANALYSIS.json')['thinking']
    checks = {}
    for key in post:
        stage = key.split('/')[0]
        if stage == 'Raw':
            accurate = thinking['raw']['accurate']['metrics']['default/score']['seed_values']
            score = thinking['raw']['score']['metrics']['default/score']['seed_values']
        else:
            accurate = thinking['selected']['S3/accurate']['metrics']['default']['seed_values']
            score = thinking['selected']['S3/score']['metrics']['default']['seed_values']
        checks[key] = contrast(np.asarray(accurate) - np.asarray(score))
        for field in ['mean', 'seed_values', 'ci95', 'sign_swap_p']:
            assert checks[key][field] == post[key][field], (key, field)
    adjusted = holm({key: row['sign_swap_p'] for key, row in checks.items()})
    assert all(adjusted[key] == post[key]['holm_p'] for key in checks)
    (a.output / 'posthoc_recomputed.json').write_text(json.dumps({'status': 'passed', 'exact_match': True,
        'comparisons': checks, 'holm_p': adjusted, 'new_model_calls': 0}, indent=2) + '\n', encoding='utf-8')
    rows = []
    for key, row in post.items():
        label = 'Raw Accurate - Score' if key.startswith('Raw') else 'S3 Accurate - Score'
        rows.append([label, ci(row), f"{row['positive_seeds']}/{row['negative_seeds']}",
                     f"{row['sign_swap_p']:.6f}", f"{row['holm_p']:.6f}"])
    emit('tableS4_posthoc', ['Contrast', 'Mean [95 percent interval]', 'Positive/negative', 'Raw p', 'Holm p'], rows)
    role = read('results/feedback_specificity_v2/role_analysis/ANALYSIS.json')['summaries']
    emit('tableS5_selection', ['Test setting', 'S3 minus random selection [95 percent interval]'],
         [[label, ci(role['pooled/S3/' + setting]['total'])] for setting, label in [('noise01', 'Noise 0.01'), ('long', '200 rounds')]])
    rows = []
    for mode in ['off', 'on']:
        distance = read('docs/direct_reciprocity/mismatch_distance/mismatch_distance_thinking_' + mode + '.json')
        r = distance['weak_mismatch_sensitivity']['tau_raw_further_two_thirds']
        rows.append([mode.upper(), r['n'], ci(r)])
    emit('tableS6_distance', ['Mode', 'Parents retained', 'Raw Accurate - Mismatched'], rows)
    emit('tableS1_probe_parameters', ['Probe', 'Start t', 'Defection rounds', 'Following rule'],
         [['two D TFT', 3, 2, 'Copy previous action'], ['five D GTFT', 9, 5, 'Copy with forgiveness 0.15'],
          ['three D ALLC', 6, 3, 'Always C'], ['sustained D', 5, 35, 'D to horizon'],
          ['periodic D', 4, '---', 'First 2 of every 7 steps D']])
    print('Exported current supplementary tables S1-S6 as CSV and TeX')


if __name__ == '__main__':
    main()
