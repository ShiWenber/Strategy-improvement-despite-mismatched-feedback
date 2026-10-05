"""Reproducible publication figures from the complete frozen v2 analysis only."""
import argparse
import json
from pathlib import Path
import os

import numpy as np

from .core import digest
from .run import read_json, write_json

ARMS = ('score', 'accurate', 'mismatched', 'background', 'cooperation')
LABELS = ('Score only', 'Accurate diagnosis', 'Mismatched diagnosis', 'Background text', 'Cooperation advice')
COLORS = ('#555555', '#0072B2', '#D55E00', '#009E73', '#CC79A7')
MARKERS = ('o', 's', '^', 'D', 'v')


def plot(root):
    root = Path(root)
    read_json(root / 'COMPLETE.json')
    data = read_json(root / 'ANALYSIS.json')
    if data['audit']['issues']:
        raise RuntimeError('Do not plot unaudited results')
    output = root / 'figures'
    output.mkdir(exist_ok=True)
    os.environ.setdefault('MPLCONFIGDIR', str(output / '.mplconfig'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.ticker import MaxNLocator
    plt.rcParams.update({'font.size': 10, 'axes.labelsize': 10, 'axes.titlesize': 11,
                         'xtick.labelsize': 9, 'ytick.labelsize': 9, 'legend.fontsize': 9,
                         'font.family': 'DejaVu Sans', 'pdf.fonttype': 42,
                         'svg.fonttype': 'none', 'axes.spines.top': False, 'axes.spines.right': False})
    files = []

    def save(fig, name):
        for ext in ('png', 'svg', 'pdf'):
            path = output / (name + '.' + ext)
            fig.savefig(path, dpi=180, bbox_inches='tight')
            files.append(str(path))
        plt.close(fig)

    def dot(ax, row, y, color, marker, show_seeds=False):
        if show_seeds:
            offsets = np.linspace(-.15, .15, len(row['seed_values']))
            ax.scatter(row['seed_values'], y + offsets, s=12, color=color, alpha=.22, linewidths=0, zorder=1)
        lo, hi = row['ci95']
        ax.plot([lo, hi], [y, y], color=color, lw=2, zorder=2)
        ax.plot([lo, lo], [y - .07, y + .07], color=color, lw=1)
        ax.plot([hi, hi], [y - .07, y + .07], color=color, lw=1)
        ax.scatter([row['mean']], [y], marker=marker, s=44, color=color, edgecolors='white', linewidth=.5, zorder=3)

    def setup(ax, labels):
        ax.axvline(0, color='#333333', lw=.8, linestyle='--')
        ax.set_yticks(range(len(labels)), labels)
        ax.set_ylim(len(labels) - .5, -.5)
        ax.grid(axis='x', color='#e5e5e5', linewidth=.6)
        ax.set_axisbelow(True)

    fig, axes = plt.subplots(1, 2, figsize=(10, 3.8), constrained_layout=True)
    for i, arm in enumerate(ARMS):
        dot(axes[0], data['raw'][arm]['metrics']['default/score'], i, COLORS[i], MARKERS[i], True)
    setup(axes[0], LABELS)
    axes[0].set_title('(a) All proposals, before selection', loc='left')
    axes[0].set_xlabel('Payoff gain over parent (per round)')
    comparisons = [('Accurate - mismatched', data['primary']),
                   ('Accurate - score', data['secondary']['raw_accurate-score']),
                   ('Accurate - background', data['secondary']['raw_accurate-background']),
                   ('Accurate - cooperation', data['secondary']['raw_accurate-cooperation'])]
    for i, (_, row) in enumerate(comparisons):
        dot(axes[1], row, i, '#333333', 'o', True)
    setup(axes[1], [label for label, _ in comparisons])
    axes[1].set_title('(b) Paired feedback contrasts', loc='left')
    axes[1].set_xlabel('Difference in payoff gain (per round)')
    save(fig, 'specificity_proposals')

    fig, axes = plt.subplots(1, 3, figsize=(10, 3.5), sharex=True, sharey=True, constrained_layout=True)
    for ax, rule, title in zip(axes, ('S1', 'S2', 'S3'), ('S1: training, 5 repeats', 'S2: training, 20 repeats', 'S3: validation, 20 repeats')):
        for i, arm in enumerate(ARMS):
            dot(ax, data['selected'][rule + '/' + arm]['metrics']['default'], i, COLORS[i], MARKERS[i])
        setup(ax, LABELS)
        ax.set_title(title, loc='left')
        ax.set_xlabel('Payoff gain over parent\n(per round)')
    save(fig, 'specificity_selection')

    fig, axes = plt.subplots(2, 2, figsize=(10, 6), sharex='col', constrained_layout=True)
    for row_index, mode in enumerate(('controlled', 'natural')):
        for col_index, metric, title, unit in [
            (0, 'recovery_time_capped', 'Recovery delay', 'Change in capped recovery time (rounds)'),
            (1, 'sustained_unilateral_cooperation_last5', 'Persistent exploitation', 'Change in unilateral cooperation (fraction)')]:
            ax = axes[row_index, col_index]
            for i, arm in enumerate(ARMS):
                dot(ax, data['raw'][arm]['behavior'][mode + '/' + metric], i, COLORS[i], MARKERS[i])
            setup(ax, LABELS)
            history_label = 'Supplied CC' if mode == 'controlled' else 'Empty history'
            ax.set_title(f'{history_label}: {title}', loc='left')
            ax.set_xlabel(unit + ('\nLower indicates faster recovery' if col_index == 0 else '\nLower indicates less exposure'))
            ax.xaxis.set_major_locator(MaxNLocator(nbins=4))
            ax.tick_params(axis='x', labelbottom=True)
    save(fig, 'specificity_behavior')
    p = data['primary']
    caption = [
        '# Figure captions and provenance', '',
        f"Proposal contrast: accurate minus mismatched diagnosis is {p['mean']:+.5f} payoff per round "
        f"(95% seed-bootstrap interval [{p['ci95'][0]:+.5f}, {p['ci95'][1]:+.5f}]). "
        f"The primary paired sign-swap p-value is {p['sign_swap_p']:.6f}. "
        'Left: mean offspring-minus-parent payoff on the frozen 100-round, no-noise test panel. '
        'Right: paired feedback contrasts. Small points are the 20 independent population means or differences; '
        'large markers and horizontal lines are means and unadjusted 95% bootstrap intervals. '
        'The first contrast is primary; secondary p-values are Holm-adjusted in the report. '
        'Invalid or runtime-failing proposals retain the parent under the frozen deployment rule.', '',
        'Selection figures show output gains for the same candidate pools. S1 selects on original training opponents '
        'with five repeats; S2 uses those opponents with 20 repeats; S3 uses a separate validation panel with '
        '20 repeats. Each rule accepts the best of two children only if it exceeds the parent on that rule. '
        'The independent test panel never selects candidates. S2 and S3 have matched evaluation game counts; '
        'S1 has a smaller evaluation budget. All intervals use population clusters. '
        f"Under S3, accurate-diagnosis output gains {data['selected']['S3/accurate']['metrics']['default']['mean']:+.5f} "
        'per round over the parent, but its contrast against score-only output is '
        f"{data['secondary']['S3_accurate-score']['mean']:+.5f}; a positive selected output alone does not isolate a diagnostic benefit.", '',
        'Behavior figures show two distinct types of modification on independent probes. Recovery delay is the '
        'time after the defection episode until five consecutive mutually cooperative rounds, capped at the '
        'observation window for non-recovery. Persistent exploitation is unilateral cooperation in the final '
        'five rounds against sustained defection. Controlled probes start with seven supplied CC rounds; '
        'natural probes start with empty histories. Negative changes indicate less delay or less exposure, '
        'but these measures alone do not establish payoff improvement. The same metric uses the same horizontal scale '
        'in both history conditions. Accurate-diagnosis proposals show longer recovery delay and lower mean exposure '
        'than their parents; this is a tradeoff, not evidence of simultaneous repair. These endpoints are exploratory.', '',
        'All PDFs and SVGs contain vector plot elements; PNG files are previews. Marker shape and direct labels '
        'supplement color. All payoff-change axes include zero. Figures contain no modeled or imputed successes.', ''
    ]
    (output / 'CAPTIONS.md').write_text('\n'.join(caption), encoding='utf-8')
    write_json(output / 'PROVENANCE.json', {'analysis_hash': digest((root / 'ANALYSIS.json').read_text(encoding='utf-8')),
                                        'files': files, 'input': str(root / 'ANALYSIS.json'),
                                        'script_hash': digest(Path(__file__).read_text(encoding='utf-8'))})
    return files


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', nargs='?', default='results/feedback_specificity_v2')
    args = parser.parse_args()
    print(json.dumps(plot(args.root)))
