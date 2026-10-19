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
    parser.add_argument('--numbering', choices=('legacy', 'manuscript'), default='legacy',
                        help='Continuous I-V numbering for the compiled 2026-10-13 manuscript.')
    a = parser.parse_args()
    a.output.mkdir(parents=True, exist_ok=True)

    def read(rel):
        path = a.work / rel
        return json.loads(path.with_name(path.stem + a.analysis_suffix + path.suffix).read_text(encoding='utf-8-sig'))

    names = {'tableS1_probe_parameters': 'tableII_probe_parameters',
             'tableS3_sensitivity': 'tableIV_sensitivity',
             'tableS4_selection': 'tableIII_selection',
             'tableS5_distance': 'tableV_distance',
             'tableS2_primary': 'extra_primary_test',
             'tableS6_score_baseline': 'extra_score_baseline',
             'tableS7_score_failures': 'extra_score_failures'}

    def emit(stem, headers, rows):
        if a.numbering == 'manuscript':
            stem = names.get(stem, stem)
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
        if row.get('mean') is None or row.get('ci95') is None:
            return 'Not estimable'
        return f"{row['mean']:+.5f} [{row['ci95'][0]:+.5f}, {row['ci95'][1]:+.5f}]"

    def context_count(row):
        return f"{row.get('n_contexts', '?')}/{row.get('n_expected_contexts', '?')}"

    if a.numbering == 'manuscript':
        emit('tableI_selectors', ['Property', 'S1', 'S2', 'S3'],
             [['Scoring source', 'Training', 'Training', 'Validation V'],
              ['Opponents', '11 peers + 13 reference', '11 peers + 13 reference', '4 families x 6'],
              ['Repeats per opponent', 5, 20, 20], ['Games', 120, 480, 480],
              ['Weights', 'Peers 0.6 / reference 0.4', 'Peers 0.6 / reference 0.4', 'Equal by family']])
    off = read('results/feedback_specificity_v2/ANALYSIS.json')
    rows = [['Raw Accurate - Mismatched (primary)', f"{off['primary']['sign_swap_p']:.6f}", '---']]
    emit('tableS2_primary', ['Contrast', 'Raw p'], [row[:2] for row in rows])
    sensitivity = {arm: [off['raw'][arm]['metrics'][setting + '/score'] for setting in ['noise01', 'long']]
                   for arm in ['accurate', 'mismatched']}
    missing = any(row.get('missing_contexts') or row.get('estimable') is False
                  for rows in sensitivity.values() for row in rows)
    emit('tableS3_sensitivity', ['Condition', 'Noise 0.01', '200 rounds']
         + (['Noise parent contexts', '200-round parent contexts'] if missing else []),
         [[arm.title(), *map(ci, rows), *([context_count(row) for row in rows] if missing else [])]
          for arm, rows in sensitivity.items()])
    role = read('results/feedback_specificity_v2/role_analysis/ANALYSIS.json')['summaries']
    emit('tableS4_selection', ['Test setting', 'S3 minus random selection [95 percent interval]']
         + (['Parent contexts evaluated'] if missing else []),
         [[label, ci(role['pooled/S3/' + setting]['total']),
           *([context_count(role['pooled/S3/' + setting]['total'])] if missing else [])]
          for setting, label in [('noise01', 'Noise 0.01'), ('long', '200 rounds')]])
    if missing:
        (a.output / ('SAMPLE_AVAILABILITY' + a.output_suffix + '.json')).write_text(
            json.dumps({'note': 'Unavailable parent measurements are excluded only for their setting; '
                               'undefined gains are never replaced by zero.',
                        'sensitivity': {arm: {setting: row for setting, row in zip(('noise01', 'long'), rows)}
                                        for arm, rows in sensitivity.items()}}, indent=2), encoding='utf-8')
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
    manifest = json.loads((a.work / 'results/feedback_specificity_v2/manifest.json').read_text(encoding='utf-8-sig'))
    if 'score' in manifest['arms']:
        score = read('results/model_comparison_20260928/score_baseline_data.json')['configurations']
        emit('tableS6_score_baseline', ['Configuration', 'Raw contrast', 'Mean [95 percent interval]'],
             [[config, arm.title() + ' - Score', ci(data['comparisons']['raw'][arm + '_minus_score'])]
              for config, data in score.items() for arm in ('accurate', 'mismatched')])
        score_missing = any(any(data.get('unavailable', {}).values()) for data in score.values())
        emit('tableS7_score_failures', ['Configuration', 'Candidates', 'Invalid', 'H default', 'H noise', 'H long', 'Behaviour']
             + (['Unavailable default', 'Unavailable noise', 'Unavailable long', 'Unavailable behaviour'] if score_missing else []),
             [[config, data['candidates'], data['invalid'],
               *[data['fallbacks'][setting] for setting in ('default', 'noise01', 'long', 'behavior')],
               *([data.get('unavailable', {}).get(setting, 0) for setting in ('default', 'noise01', 'long', 'behavior')]
                 if score_missing else [])]
              for config, data in score.items()])
    last = 'S7' if 'score' in manifest['arms'] else 'S5'
    print('Exported manuscript tables I-V and additional evidence as CSV and TeX'
          if a.numbering == 'manuscript' else f'Exported legacy supplementary tables S1-{last} as CSV and TeX')


if __name__ == '__main__':
    main()
