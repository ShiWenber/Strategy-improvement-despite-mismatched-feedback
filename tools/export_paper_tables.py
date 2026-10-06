"""Export the current manuscript's compact numeric tables from full-precision JSON."""
import argparse
import csv
import json
import textwrap
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--analysis-suffix', default='')
    parser.add_argument('--output-suffix', default='')
    parser.add_argument('--run-root', type=Path, help='Export one OFF experiment instead of the paper datasets.')
    parser.add_argument('--distance-input', type=Path, help='Distance summary for --run-root.')
    parser.add_argument('--figure-dir', type=Path, help='Also render readable table PNG and PDF files.')
    a = parser.parse_args()
    a.work = a.work.resolve()
    if a.run_root:
        a.run_root = a.run_root.resolve()
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
        if a.figure_dir:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            widths = [max(len(str(row[i])) for row in [headers, *rows]) for i in range(len(headers))]
            wrap_width = max(16, 80 // len(headers))
            cells = [[textwrap.fill(str(cell), wrap_width) for cell in row] for row in [headers, *rows]]
            heights = [max(cell.count('\n') + 1 for cell in row) for row in cells]
            fig, ax = plt.subplots(figsize=(175 / 25.4, .30 * sum(heights) + .55))
            ax.axis('off')
            table = ax.table(cellText=cells[1:], colLabels=cells[0], cellLoc='left', loc='center',
                             colWidths=[max(12, min(width, wrap_width)) / sum(max(12, min(w, wrap_width)) for w in widths) for width in widths])
            table.auto_set_font_size(False)
            table.set_fontsize(8.5)
            for (i, j), cell in table.get_celld().items():
                cell.set_height(.26 * heights[i] / fig.get_figheight())
                cell.set_edgecolor('#D4D9DE')
                cell.set_linewidth(.5)
                if i == 0:
                    cell.set_facecolor('#E9EEF3')
                    cell.get_text().set_weight('bold')
            fig.tight_layout(pad=.7)
            a.figure_dir.mkdir(parents=True, exist_ok=True)
            for extension in ('png', 'pdf'):
                fig.savefig(a.figure_dir / (stem.split('_')[0] + '.' + extension), dpi=300, facecolor='white')
            plt.close(fig)

    def ci(row):
        return f"{row['mean']:+.5f} [{row['ci95'][0]:+.5f}, {row['ci95'][1]:+.5f}]"

    source = a.run_root if a.run_root else a.work / 'results/feedback_specificity_v2'
    off = read(source / 'ANALYSIS.json')
    rows = [['Raw Accurate - Mismatched (primary)', f"{off['primary']['sign_swap_p']:.6f}", '---']]
    emit('tableS2_primary', ['Contrast', 'Raw p'], [row[:2] for row in rows])
    emit('tableS3_sensitivity', ['Condition', 'Noise 0.01', '200 rounds'],
         [[arm.title(), *[ci(off['raw'][arm]['metrics'][setting + '/score']) for setting in ['noise01', 'long']]] for arm in ['accurate', 'mismatched']])
    role = read(source / 'role_analysis/ANALYSIS.json')['summaries']
    emit('tableS4_selection', ['Test setting', 'S3 minus random selection [95 percent interval]'],
         [[label, ci(role['pooled/S3/' + setting]['total'])] for setting, label in [('noise01', 'Noise 0.01'), ('long', '200 rounds')]])
    rows = []
    for mode in (['off'] if a.run_root else ['off', 'on']):
        distance = json.loads(a.distance_input.read_text(encoding='utf-8')) if a.distance_input else read('docs/direct_reciprocity/mismatch_distance/mismatch_distance_thinking_' + mode + '.json')
        r = distance['weak_mismatch_sensitivity']['tau_raw_further_two_thirds']
        rows.append([mode.upper(), r['n'], ci(r)] if r else [mode.upper(), distance['weak_mismatch_sensitivity']['n_strong'], 'Insufficient parents'])
    emit('tableS5_distance', ['Mode', 'Parents retained', 'Raw Accurate - Mismatched'], rows)
    emit('tableS1_probe_parameters', ['Probe', 'Start t', 'Defection rounds', 'Following rule'],
         [['two D TFT', 3, 2, 'Copy previous action'], ['five D GTFT', 9, 5, 'Copy with forgiveness 0.15'],
          ['three D ALLC', 6, 3, 'Always C'], ['sustained D', 5, 35, 'D to horizon'],
          ['periodic D', 4, '---', 'First 2 of every 7 steps D']])
    if a.run_root:
        emit('tableI_conditions', ['Condition', 'Numerical report'],
             [['Accurate', 'The parent strategy\'s own report'], ['Mismatched', 'Another strategy\'s report in the same population']])
        emit('tableII_scoring', ['Selector', 'Evaluation panel', 'Repetitions'],
             [['S1', 'Training', 5], ['S2', 'Training', 20], ['S3', 'Validation', 20]])
    print('Exported tables as CSV and TeX' + (' and readable PNG/PDF' if a.figure_dir else ''))


if __name__ == '__main__':
    main()
