"""Render existing frozen statistics at their IEEE placement sizes.

Writes figure assets from the supplied analysis files.
"""
import argparse
import json
import os
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
OUT = REPO
FIGURES = {3: 'figS1', 4: 'figS5', 5: 'figS3'}
os.environ.setdefault('MPLCONFIGDIR', str(REPO/'.mplconfig'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator
from matplotlib.lines import Line2D
from .results_plot_style import apply_style, panel_title, panel_legend
from .results_plot_style import save_figure
from .plot_data import fit_axis, interval_values, draw_intervals
import numpy as np

ARMS = ('accurate', 'mismatched')
LABELS = ('Accurate', 'Mismatched')
COLORS = ('#0072B2', '#D55E00')
MARKERS = ('o', 's')
TEXTWIDTH = 175 / 25.4


exports = []

def dot(ax, row, y, color, marker, seeds=False):
    if seeds:
        offsets = np.linspace(-.15,.15,len(row['seed_values']))
        ax.scatter(row['seed_values'], y+offsets, s=9, color=color, alpha=.25,
                   linewidths=0, zorder=1)
    lo, hi = row['ci95']
    ax.plot([lo,hi],[y,y],color=color,lw=1.45,zorder=2)
    ax.plot([lo,lo],[y-.06,y+.06],color=color,lw=.8)
    ax.plot([hi,hi],[y-.06,y+.06],color=color,lw=.8)
    ax.scatter([row['mean']],[y],marker=marker,s=29,color=color,
               edgecolors='white',linewidth=.45,zorder=3)

def setup(ax, labels=LABELS):
    ax.axvline(0,color='#444444',lw=.7,ls='--')
    ax.set_yticks(range(len(labels)),labels)
    ax.set_ylim(len(labels)-.5,-1.05)
    ax.grid(axis='x',color='#e5e5e5',linewidth=.55)
    ax.set_axisbelow(True)
    ax.xaxis.set_major_locator(MaxNLocator(nbins=4))
    ax.tick_params(axis='y',length=0,pad=3)

def save(fig, index):
    exports.append(save_figure(fig, FIGURES[index], OUT))
    plt.close(fig)


def condition_legend(ax):
    handles = [Line2D([], [], color=color, marker=marker, linestyle='none',
                      markersize=4.8) for color, marker in zip(COLORS, MARKERS)]
    return panel_legend(ax, handles, list(LABELS), ncol=1)


def make_figure3(data, thinking, selection_repeats=None):
    """Stored selector means and intervals; six parallel descriptive panels."""
    apply_style()
    fig, axes = plt.subplots(2, 3, figsize=(TEXTWIDTH, 5.10), layout='constrained')
    fig.get_layout_engine().set(rect=(0, 0, 1, 1), w_pad=.035, h_pad=.065,
                                wspace=.07, hspace=.14)
    values_for_limits = interval_values([report['selected'][rule + '/' + arm]['metrics']['default']
                                        for report in (data, thinking)
                                        for rule in ('S1', 'S2', 'S3') for arm in ARMS])
    for row, (mode, values) in enumerate((('Thinking OFF', data), ('Thinking ON', thinking))):
        for column, rule in enumerate(('S1', 'S2', 'S3')):
            title = rule + (': validation' if rule == 'S3' else ': training')
            if selection_repeats is not None:
                title += f' ({selection_repeats[rule]})'
            ax = axes[row, column]
            for i, arm in enumerate(ARMS):
                dot(ax, values['selected'][rule + '/' + arm]['metrics']['default'],
                    i, COLORS[i], MARKERS[i])
            setup(ax)
            panel_title(ax, chr(97 + row * 3 + column), mode + '\n' + title)
            condition_legend(ax)
            fit_axis(ax, values_for_limits, include_zero=True, nbins=3)
            ax.set_xlabel('Payoff gain\nper round')
    save(fig, 3)


def make_figure4(data):
    """Stored Thinking OFF raw proposal changes under both history settings."""
    apply_style()
    fig, axes = plt.subplots(2, 2, figsize=(TEXTWIDTH, 4.85), sharex='col', layout='constrained')
    fig.get_layout_engine().set(rect=(0, 0, 1, 1), w_pad=.05, h_pad=.07,
                                wspace=.09, hspace=.12)
    for ri, mode in enumerate(('controlled', 'natural')):
        for ci, metric, title, xlabel in (
            (0, 'recovery_time_capped', 'Capped recovery time',
             'Change in capped recovery time\n(rounds)'),
            (1, 'sustained_unilateral_cooperation_last5', 'Defection exposure',
             'Unilateral cooperation change\n(fraction)')):
            ax = axes[ri, ci]
            for i, arm in enumerate(ARMS):
                dot(ax, data['raw'][arm]['behavior'][mode + '/' + metric],
                    i, COLORS[i], MARKERS[i])
            setup(ax)
            history = 'Supplied CC' if mode == 'controlled' else 'Empty history'
            panel_title(ax, chr(97 + 2 * ri + ci), 'Thinking OFF: ' + history + '\n' + title)
            condition_legend(ax)
            ax.set_xlabel(xlabel)
            ax.xaxis.set_major_locator(MaxNLocator(nbins=4))
            ax.tick_params(axis='x', labelbottom=True)
    save(fig, 4)


def make_figure5(role):
    """Stored policy means and S3 paired decomposition; no new contrasts."""
    apply_style()
    fig, axes = plt.subplots(1, 2, figsize=(TEXTWIDTH, 3.55), layout='constrained',
                             gridspec_kw={'width_ratios': [1.24, 1]})
    fig.get_layout_engine().set(rect=(0, 0, 1, 1), w_pad=.04, h_pad=.05,
                                wspace=.09, hspace=.09)
    policy_colors = ('#777777', '#D55E00', '#0072B2')
    policy_markers = ('o', 's', '^')
    handles = [Line2D([], [], color=color, marker=marker, markersize=4.3, lw=1.2)
               for color, marker in zip(policy_colors, policy_markers)]
    legend = panel_legend(axes[0], handles, ['S1', 'S2', 'S3'], ncol=3)
    legend.set_loc('lower center')
    legend.set_bbox_to_anchor((.5, .82), transform=axes[0].transAxes)
    panel_legend(axes[1],[Line2D([], [], color='#0072B2', marker='o', linestyle='none', markersize=4.8),
                         Line2D([], [], color='#222222', marker='D', linestyle='none', markersize=4.8)],
                 ['Adjacent difference','Total difference'],ncol=1)
    for i, (rule, color) in enumerate(zip(('S1', 'S2', 'S3'), policy_colors)):
        row = role['summaries'][f'pooled/{rule}/default']
        x = np.arange(4) + (i - 1) * .075
        y = np.array([row[k]['mean'] for k in ('R', 'G', 'U', 'B')])
        axes[0].plot(x, y, color=color, marker=policy_markers[i], markersize=4.3, lw=1.2)
    axes[0].set_xticks(range(4), ['Random\nN', 'Gated\nG', 'Eligible\nU', 'Best\nB'])
    axes[0].set_ylabel('Test payoff gain per round')
    panel_title(axes[0], 'a', 'Four fixed-pool policies\nThinking OFF, post hoc')
    axes[0].axhline(0, color='#444444', ls='--', lw=.7)
    axes[0].grid(axis='y', alpha=.2)
    fit_axis(axes[0], [role['summaries'][f'pooled/{rule}/default'][key]['mean']
                       for rule in ('S1', 'S2', 'S3') for key in ('R', 'G', 'U', 'B')],
             axis='y', include_zero=True, headroom=.5)
    row = role['summaries']['pooled/S3/default']
    for i, k in enumerate(('gate', 'opportunity', 'ranking', 'total')):
        v = row[k]
        color = '#222222' if k == 'total' else '#0072B2'
        draw_intervals(axes[1], i, *v['ci95'], color=color, capsize=3, lw=1.5)
        axes[1].plot(v['mean'], i, linestyle='none', marker='D' if k == 'total' else 'o',
                     color=color, markersize=4.8)
    axes[1].set_yticks(range(4), ['Gate\nG − N', 'Opportunity\nU − G', 'Ranking\nB − U', 'Total\nB − N'])
    axes[1].invert_yaxis()
    axes[1].set_ylim(3.5,-1.4)
    axes[1].tick_params(axis='y', length=0)
    axes[1].axvline(0, color='#444444', ls='--', lw=.7)
    axes[1].grid(axis='x', alpha=.2)
    axes[1].set_xlabel('Paired payoff difference\nper round')
    panel_title(axes[1], 'b', 'S3 selection differences\nThinking OFF, post hoc')
    fit_axis(axes[1], interval_values([row[k] for k in ('gate', 'opportunity', 'ranking', 'total')]),
             include_zero=True, nbins=3)
    save(fig, 5)


def main():
    global OUT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--figures', nargs='+', type=int, choices=(3, 4, 5), default=[3, 4, 5])
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--off-analysis', type=Path)
    parser.add_argument('--off-role-analysis', type=Path)
    parser.add_argument('--on-analysis', type=Path)
    args = parser.parse_args()
    OUT = args.output_dir.resolve()
    OUT.mkdir(parents=True, exist_ok=True)
    required = []
    if 3 in args.figures or 4 in args.figures:
        required.append(('off_analysis', args.off_analysis))
    if 3 in args.figures:
        required.append(('on_analysis', args.on_analysis))
    if 5 in args.figures:
        required.append(('off_role_analysis', args.off_role_analysis))
    missing = [name for name, path in required if path is None]
    if missing:
        parser.error('Missing figure inputs: ' + ', '.join(missing))
    data = {name: json.loads(path.read_text(encoding='utf-8')) for name, path in required}
    exports.clear()
    for index in args.figures:
        if index == 3:
            manifest = json.loads((args.off_analysis.parent / 'manifest.json').read_text(encoding='utf-8-sig'))
            make_figure3(data['off_analysis'], data['on_analysis']['thinking'], manifest['selection_repeats'])
        elif index == 4:
            make_figure4(data['off_analysis'])
        else:
            make_figure5(data['off_role_analysis'])
    print(json.dumps(exports, indent=2))


if __name__ == '__main__':
    main()
