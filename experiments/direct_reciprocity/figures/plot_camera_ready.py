"""Render existing frozen statistics at their IEEE placement sizes.

No new analysis, model requests, or games. Writes figures to reproduct and
a font/bounds report to results/reproduction; Figure 1 is untouched.
"""
from hashlib import sha256
import argparse
import json
import os
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
ROOT = REPO
OUT = REPO
FIGURES = {3: 'figS1', 4: 'figS5', 5: 'figS3'}
os.environ.setdefault('MPLCONFIGDIR', str(REPO/'.mplconfig'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator
from matplotlib.text import Text
from matplotlib.lines import Line2D
from .results_plot_style import apply_style, panel_title, panel_legend
from .results_plot_audit import render_audit
import numpy as np

ARMS = ('accurate', 'mismatched')
LABELS = ('Accurate', 'Mismatched')
COLORS = ('#0072B2', '#D55E00')
MARKERS = ('o', 's')
TEXTWIDTH = 175 / 25.4
FRACTIONS = {3:1., 4:1., 5:1.}
WIDTHS = {i: TEXTWIDTH*f for i,f in FRACTIONS.items()}


audits = []
INPUTS = []
AUDIT_DIR = REPO

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
    # No tight bounding box: physical width equals the LaTeX placement width,
    # so an 8.5 pt artist remains 8.5 pt in the final paper.
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    bounds = fig.bbox
    clipped=[]
    sizes=[]
    not_drawn=set()
    for ax in fig.axes:
        for axis in (ax.xaxis,ax.yaxis):
            low,high=sorted(axis.get_view_interval())
            for tick in (*axis.get_major_ticks(),*axis.get_minor_ticks()):
                if not low-1e-10 <= tick.get_loc() <= high+1e-10:
                    not_drawn.update((tick.label1,tick.label2))
    for artist in fig.findobj(Text):
        if artist in not_drawn or not artist.get_visible() or not artist.get_text().strip():
            continue
        bb=artist.get_window_extent(renderer)
        # Hidden shared-axis labels may be positioned beyond the rendered axes.
        if bb.width == 0 or bb.height == 0:
            continue
        sizes.append(artist.get_fontsize())
        if bb.x0 < bounds.x0-.5 or bb.y0 < bounds.y0-.5 or bb.x1 > bounds.x1+.5 or bb.y1 > bounds.y1+.5:
            clipped.append(artist.get_text())
    assert min(sizes) >= 8.5
    assert not clipped, (index,clipped)
    labels=[t.get_text() for ax in fig.axes for t in ax.get_legend().get_texts()]
    render_audit(fig,FIGURES[index],INPUTS,__file__,labels,
                 ['Stored population means and 95% bootstrap intervals are reused unchanged; interval definitions are in the caption.'],
                 output_dir=OUT,audit_dir=AUDIT_DIR)
    audits.append(dict(figure=index,width_inches=fig.get_figwidth(),height_inches=fig.get_figheight(),
                       placement_fraction=FRACTIONS[index],minimum_artist_font_pt=min(sizes),
                       out_of_canvas_text=clipped))
    plt.close(fig)

def condition_legend(ax):
    handles = [Line2D([], [], color=color, marker=marker, linestyle='none',
                      markersize=4.8) for color, marker in zip(COLORS, MARKERS)]
    return panel_legend(ax, handles, list(LABELS), ncol=1)


def make_figure3(data, thinking):
    """Stored selector means and intervals; six parallel descriptive panels."""
    apply_style()
    fig, axes = plt.subplots(2, 3, figsize=(WIDTHS[3], 5.10), layout='constrained')
    fig.get_layout_engine().set(rect=(0, 0, 1, 1), w_pad=.035, h_pad=.065,
                                wspace=.07, hspace=.14)
    for row, (mode, values) in enumerate((('Thinking OFF', data), ('Thinking ON', thinking))):
        for column, (rule, title) in enumerate(zip(
                ('S1', 'S2', 'S3'),
                ('S1: training (5)', 'S2: training (20)', 'S3: validation (20)'))):
            ax = axes[row, column]
            for i, arm in enumerate(ARMS):
                dot(ax, values['selected'][rule + '/' + arm]['metrics']['default'],
                    i, COLORS[i], MARKERS[i])
            setup(ax)
            panel_title(ax, chr(97 + row * 3 + column), mode + '\n' + title)
            condition_legend(ax)
            ax.set_xlim(-.01, .14)
            ax.set_xticks([0, .05, .10])
            ax.set_xlabel('Payoff gain\nper round')
    save(fig, 3)


def make_figure4(data):
    """Stored Thinking OFF raw proposal changes under both history settings."""
    apply_style()
    fig, axes = plt.subplots(2, 2, figsize=(WIDTHS[4], 4.85), sharex='col', layout='constrained')
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
    fig, axes = plt.subplots(1, 2, figsize=(WIDTHS[5], 3.55), layout='constrained',
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
        lo = np.array([row[k]['ci95'][0] for k in ('R', 'G', 'U', 'B')])
        hi = np.array([row[k]['ci95'][1] for k in ('R', 'G', 'U', 'B')])
        axes[0].errorbar(x, y, yerr=[y - lo, hi - y], color=color,
                         marker=policy_markers[i], markersize=4.3, capsize=2.5, lw=1.2)
    axes[0].set_xticks(range(4), ['Random\nN', 'Gated\nG', 'Eligible\nU', 'Best\nB'])
    axes[0].set_ylabel('Test payoff gain per round')
    panel_title(axes[0], 'a', 'Four fixed-pool policies\nThinking OFF, post hoc')
    axes[0].axhline(0, color='#444444', ls='--', lw=.7)
    axes[0].grid(axis='y', alpha=.2)
    axes[0].set_ylim(-.01, .056)
    row = role['summaries']['pooled/S3/default']
    for i, k in enumerate(('gate', 'opportunity', 'ranking', 'total')):
        v = row[k]
        axes[1].errorbar(v['mean'], i,
                         xerr=[[v['mean'] - v['ci95'][0]], [v['ci95'][1] - v['mean']]],
                         fmt='D' if k == 'total' else 'o',
                         color='#222222' if k == 'total' else '#0072B2',
                         markersize=4.8, capsize=3, lw=1.5)
    axes[1].set_yticks(range(4), ['Gate\nG − N', 'Opportunity\nU − G', 'Ranking\nB − U', 'Total\nB − N'])
    axes[1].invert_yaxis()
    axes[1].set_ylim(3.5,-1.4)
    axes[1].tick_params(axis='y', length=0)
    axes[1].axvline(0, color='#444444', ls='--', lw=.7)
    axes[1].grid(axis='x', alpha=.2)
    axes[1].set_xlabel('Paired payoff difference\nper round')
    panel_title(axes[1], 'b', 'S3 selection differences\nThinking OFF, post hoc')
    axes[1].set_xlim(-.001, .032)
    axes[1].xaxis.set_major_locator(MaxNLocator(nbins=3))
    save(fig, 5)


def main():
    global OUT, INPUTS, AUDIT_DIR
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--figures', nargs='+', type=int, choices=(3, 4, 5), default=[3, 4, 5])
    parser.add_argument('--work', type=Path, default=REPO)
    parser.add_argument('--analysis-suffix', default='')
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--audit-dir', type=Path, required=True)
    parser.add_argument('--off-analysis', type=Path, required=True)
    parser.add_argument('--off-role-analysis', type=Path, required=True)
    parser.add_argument('--on-analysis', type=Path, required=True)
    args = parser.parse_args()
    work = args.work.resolve()
    OUT = args.output_dir.resolve()
    OUT.mkdir(parents=True, exist_ok=True)
    audit_dir = args.audit_dir.resolve()
    audit_dir.mkdir(parents=True, exist_ok=True)
    data_path = args.off_analysis.resolve()
    role_path = args.off_role_analysis.resolve()
    thinking_path = args.on_analysis.resolve()
    INPUTS = [data_path, role_path, thinking_path]
    AUDIT_DIR = audit_dir
    data, role, thinking_report = [json.loads(p.read_text(encoding='utf-8')) for p in (data_path, role_path, thinking_path)]
    assert not data['audit']['issues']
    makers = {3: lambda: make_figure3(data, thinking_report['thinking']),
              4: lambda: make_figure4(data), 5: lambda: make_figure5(role)}
    for index in args.figures:
        makers[index]()
    provenance = {
        'input_sha256': {str(p.relative_to(work)): sha256(p.read_bytes()).hexdigest()
                         for p in (data_path, role_path, thinking_path)},
        'script_sha256': sha256(Path(__file__).read_bytes()).hexdigest(),
        'textwidth_inches': TEXTWIDTH, 'figures': audits,
        'data_changes': False, 'new_analysis': False, 'new_model_calls': 0, 'new_games': 0,
        'note': 'Stored means and intervals rendered unchanged; only selected output targets are written.'}
    (audit_dir / 'FIGURE_FONT_AUDIT_reproduct.json').write_text(json.dumps(provenance, indent=2), encoding='utf-8')
    print(json.dumps(audits, indent=2))


if __name__ == '__main__':
    main()
