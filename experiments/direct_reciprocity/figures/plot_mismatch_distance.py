"""Draw report-distance display from sealed records only; no analyses."""
from pathlib import Path
import argparse,json,os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np
from .results_plot_style import apply_style,panel_title,panel_legend,BLUE,GREY
from .results_plot_style import save_figure, WIDTH
from .plot_data import fit_axis, finite_values, draw_intervals


def distance_figure(off, on):
    pairs = {row['context']: row['delta_full'] for row in off['rows']}
    other = {row['context']: row['delta_full'] for row in on['rows']}
    if pairs != other or len(pairs) != len(off['rows']) or len(other) != len(on['rows']):
        raise ValueError('Shared-distance display requires the same unique parent-donor pairs')
    x = np.sort(finite_values(list(pairs.values())))
    y = np.arange(1, len(x) + 1) / len(x)
    stat = off['distance_summary']['delta_full']
    ref = off['distance_diagnostics']['null_within_population_ordered_pairs']
    values = [*x, stat['min'], stat['max'], stat['mean'], ref['q10'], ref['q90'], ref['mean']]
    fig, axes = plt.subplots(1, 2, figsize=(WIDTH, 3.60))
    fig.subplots_adjust(left=.10, right=.97, bottom=.20, top=.90, wspace=.76)
    axes[0].step(x, y, where='post', color=BLUE, lw=1.4)
    axes[0].axvline(ref['q10'], ls=':', color=GREY, lw=1.1)
    fit_axis(axes[0], [0., *y], axis='y', nonnegative=True, headroom=.22)
    axes[0].set_ylabel('Cumulative fraction')
    axes[0].set_yticks(np.linspace(0, 1, 5))
    panel_title(axes[0], 'a', f'Shared {len(x)} parent-donor pairs')
    for position, low, high, center, color, marker in [
        (1, stat['min'], stat['max'], stat['mean'], BLUE, 'o'),
        (0, ref['q10'], ref['q90'], ref['mean'], GREY, 's'),
    ]:
        draw_intervals(axes[1], position, low, high, color=color, lw=1.25, capsize=3)
        axes[1].scatter([center], [position], color=color, marker=marker, s=32, zorder=3)
    axes[1].set(yticks=[0, 1], yticklabels=['Within-population\nreference', 'Parent-donor'], ylim=(-.6, 2.1))
    axes[1].tick_params(axis='y', length=0, pad=5)
    panel_title(axes[1], 'b', 'Descriptive reference')
    for ax in axes:
        fit_axis(ax, values, nonnegative=True)
        ax.set_xlabel('Standardized report distance')
    panel_legend(axes[0], [Line2D([], [], color=BLUE, lw=1.4), Line2D([], [], color=GREY, ls=':', lw=1.1)],
                 ['Parent-donor ECDF', 'Reference 10th percentile'], ncol=1)
    panel_legend(axes[1], [Line2D([], [], marker='o', color=BLUE, ls='none'), Line2D([], [], marker='s', color=GREY, ls='none')],
                 ['Parent-donor mean', 'Reference mean'], ncol=1)
    return fig


def main():
    ROOT=Path(__file__).resolve().parents[3]
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs',nargs=2,type=Path,default=[ROOT/f'docs/direct_reciprocity/mismatch_distance/mismatch_distance_thinking_{m}.json' for m in ('off','on')])
    parser.add_argument('--output-dir',type=Path,default=ROOT/'reproduct')
    args=parser.parse_args()
    SOURCES=args.inputs
    os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'.mplconfig'))
    apply_style();off,on=[json.loads(p.read_text(encoding='utf-8')) for p in SOURCES]
    fig=distance_figure(off,on)
    r=save_figure(fig,'figS6',args.output_dir);plt.close(fig)
    print(json.dumps(r))


if __name__ == '__main__':
    main()
