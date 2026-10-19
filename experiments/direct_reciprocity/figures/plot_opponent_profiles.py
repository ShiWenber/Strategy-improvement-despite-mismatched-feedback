"""Pure render of frozen opponent-family summaries; no table writes."""
from pathlib import Path
import argparse,json,os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from matplotlib.lines import Line2D
import numpy as np
from .results_plot_style import apply_style,panel_title,panel_legend,BLUE,ORANGE,GREY
from .results_plot_style import save_figure, WIDTH
from .plot_data import fit_axis, data_limits, interval_values, draw_intervals


def opponent_figure(data):
    families = data['families']
    names = {'recovery': 'Recovery', 'exploitation': 'Exploitation', 'random': 'Random', 'memory': 'Memory-one'}
    labels = [names.get(family, family.replace('_', ' ').capitalize()) for family in families]
    stages, modes = ('raw', 'S3'), ('non_thinking', 'thinking')
    colors = {'accurate': BLUE, 'mismatched': ORANGE}
    values = interval_values([data['configs'][mode]['summaries'][stage][arm][family]
                              for mode in modes for stage in stages for arm in colors
                              for family in families], 'ci95_exploratory_unadjusted')
    low, _ = data_limits(values, include_zero=True)
    fig, axes = plt.subplots(len(stages), len(modes), figsize=(WIDTH, 5.50), sharex=True, sharey=True)
    fig.subplots_adjust(left=.19, right=.975, bottom=.12, top=.93, wspace=.26, hspace=.80)
    for row, stage in enumerate(stages):
        for column, mode in enumerate(modes):
            ax = axes[row, column]
            ax.axvspan(low, 0, color='#F4F5F6', zorder=0)
            ax.axvline(0, color=GREY, lw=.8, zorder=0)
            for index in range(len(families)):
                if index % 2 == 0: ax.axhspan(index-.45, index+.45, color='#F5F7F9', alpha=.45, zorder=0)
            for arm, offset in [('accurate', -.17), ('mismatched', .17)]:
                records = [data['configs'][mode]['summaries'][stage][arm][family] for family in families]
                means = np.array([record['mean'] for record in records])
                intervals = np.array([record['ci95_exploratory_unadjusted'] for record in records])
                positions = np.arange(len(families)) + offset
                ax.barh(positions, means, height=.28, color=colors[arm], alpha=.8, edgecolor='white', lw=.35, hatch='///' if arm=='mismatched' else None, zorder=3)
                draw_intervals(ax, positions, intervals[:,0], intervals[:,1], ecolor=colors[arm], elinewidth=.85, capsize=2, capthick=.8, zorder=4)
            ax.set_yticks(range(len(families)), labels)
            ax.set_ylim(len(families)-.45, -1.2)
            fit_axis(ax, values, include_zero=True)
            ax.tick_params(axis='y', length=0, pad=8)
            ax.tick_params(axis='x', length=3, labelbottom=True)
            panel_title(ax, chr(97+row*len(modes)+column), ('Raw' if stage=='raw' else 'S3')+': '+('Thinking OFF' if mode=='non_thinking' else 'Thinking ON'))
            ax.set_xlabel('Payoff gain per round\nvs parent')
            panel_legend(ax, [Patch(facecolor=BLUE, alpha=.8), Patch(facecolor=ORANGE, alpha=.8, hatch='///', edgecolor='white')], ['Accurate','Mismatched'], ncol=2)
    return fig


def main():
    W=Path(__file__).resolve().parents[3]
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args()
    INPUT=args.input
    os.environ.setdefault('MPLCONFIGDIR',str(W/'.mplconfig'))
    apply_style();D=json.loads(INPUT.read_text(encoding='utf-8'))
    fig=opponent_figure(D)
    r=save_figure(fig,'figS4',args.output_dir);plt.close(fig)
    print(json.dumps(r))


if __name__ == '__main__':
    main()
