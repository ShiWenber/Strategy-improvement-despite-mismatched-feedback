"""Render the post-hoc fixed-pool policy analysis, without new simulations."""
import hashlib
import json
import os
from pathlib import Path


def plot(root='results/feedback_specificity_v2/role_analysis'):
    root = Path(root)
    data = json.loads((root/'ANALYSIS.json').read_text(encoding='utf-8'))
    os.environ.setdefault('MPLCONFIGDIR', str(root/'.mplconfig'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10,
                         'axes.spines.top': False, 'axes.spines.right': False,
                         'pdf.fonttype': 42, 'svg.fonttype': 'none'})
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), gridspec_kw={'width_ratios': [1.15, 1]}, layout='constrained')
    colors = ['#777777', '#D55E00', '#0072B2']
    for i, (rule, color) in enumerate(zip(('S1', 'S2', 'S3'), colors)):
        row = data['summaries'][f'pooled/{rule}/default']
        x = np.arange(4) + (i-1)*.075
        y = np.array([row[k]['mean'] for k in ('R', 'G', 'U', 'B')])
        lo = np.array([row[k]['ci95'][0] for k in ('R', 'G', 'U', 'B')])
        hi = np.array([row[k]['ci95'][1] for k in ('R', 'G', 'U', 'B')])
        axes[0].errorbar(x, y, yerr=[y-lo, hi-y], color=color, marker=('o','s','^')[i],
                         capsize=3, lw=1.5, label={'S1':'S1: training (5)', 'S2':'S2: training (20)', 'S3':'S3: validation (20)'}[rule])
    axes[0].set_xticks(range(4), ['Random\nchild (R)', 'Random,\nthen gate (G)', 'Random\neligible (U)', 'Best\neligible (B)'])
    axes[0].set_ylabel('Held-out payoff gain per round')
    axes[0].set_title('a  Same proposals, different adoption rules', loc='left', pad=15)
    axes[0].legend(loc='upper left', frameon=False, fontsize=9)
    axes[0].axhline(0, color='#444444', ls='--', lw=.8)
    axes[0].grid(axis='y', alpha=.2)
    axes[0].set_ylim(-.008, .047)
    row = data['summaries']['pooled/S3/default']
    labels = ['Gate\nG − R', 'Extra opportunity\nU − G', 'Ranking\nB − U', 'Total\nB − R']
    for i, k in enumerate(('gate', 'opportunity', 'ranking', 'total')):
        v = row[k]
        axes[1].errorbar(v['mean'], i, xerr=[[v['mean']-v['ci95'][0]], [v['ci95'][1]-v['mean']]],
                         fmt='D' if k == 'total' else 'o', color='#222222' if k == 'total' else '#0072B2', capsize=4, lw=2)
    axes[1].set_yticks(range(4), labels)
    axes[1].invert_yaxis()
    axes[1].axvline(0, color='#444444', ls='--', lw=.8)
    axes[1].grid(axis='x', alpha=.2)
    axes[1].set_xlabel('Paired payoff difference per round')
    axes[1].set_title('b  Decomposing validation selection', loc='left', pad=15)
    axes[1].set_xlim(-.001, .032)
    for ext in ('png', 'svg', 'pdf'):
        fig.savefig(root/f'role_decomposition.{ext}', dpi=200, bbox_inches='tight')
    plt.close(fig)
    (root/'FIGURE_PROVENANCE.json').write_text(json.dumps({
        'input_sha256': hashlib.sha256((root/'ANALYSIS.json').read_bytes()).hexdigest(),
        'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'note': 'Post-hoc, equal-arm population means; unadjusted population bootstrap intervals. Policy axis is not time.'
    }, indent=2), encoding='utf-8')
    return root/'role_decomposition.png'


if __name__ == '__main__':
    print(plot())
