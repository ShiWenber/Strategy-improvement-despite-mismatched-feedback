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
    parser.add_argument('--analysis-suffix', default='')
    parser.add_argument('--output-suffix', default='')
    a = parser.parse_args()
    a.output.mkdir(parents=True, exist_ok=True)

    def read(rel):
        path = a.work / rel
        return json.loads(path.with_name(path.stem + a.analysis_suffix + path.suffix).read_text(encoding='utf-8-sig'))

    def emit(stem, headers, rows):
        stem += a.output_suffix
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
    emit('tableS2_primary', ['Contrast', 'Raw p'], [row[:2] for row in rows])
    emit('tableS3_sensitivity', ['Condition', 'Noise 0.01', '200 rounds'],
         [[arm.title(), *[ci(off['raw'][arm]['metrics'][setting + '/score']) for setting in ['noise01', 'long']]] for arm in ['accurate', 'mismatched']])
    role = read('results/feedback_specificity_v2/role_analysis/ANALYSIS.json')['summaries']
    emit('tableS4_selection', ['Test setting', 'S3 minus random selection [95 percent interval]'],
         [[label, ci(role['pooled/S3/' + setting]['total'])] for setting, label in [('noise01', 'Noise 0.01'), ('long', '200 rounds')]])
    rows = []
    for mode in ['off', 'on']:
        distance = read('docs/direct_reciprocity/mismatch_distance/mismatch_distance_thinking_' + mode + '.json')
        r = distance['weak_mismatch_sensitivity']['tau_raw_further_two_thirds']
        rows.append([mode.upper(), r['n'], ci(r)])
    emit('tableS5_distance', ['Mode', 'Parents retained', 'Raw Accurate - Mismatched'], rows)
    emit('tableS1_probe_parameters', ['Probe', 'Start t', 'Defection rounds', 'Following rule'],
         [['two D TFT', 3, 2, 'Copy previous action'], ['five D GTFT', 9, 5, 'Copy with forgiveness 0.15'],
          ['three D ALLC', 6, 3, 'Always C'], ['sustained D', 5, 35, 'D to horizon'],
          ['periodic D', 4, '---', 'First 2 of every 7 steps D']])
    print('Exported current supplementary tables S1-S5 as CSV and TeX')


if __name__ == '__main__':
    main()
