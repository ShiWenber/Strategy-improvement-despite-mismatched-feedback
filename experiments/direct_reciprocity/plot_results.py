"""Export per-seed scientific figures; incomplete runs remain visible."""
import argparse
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from .run import read_json, write_json


def plot_results(root):
    root = Path(root)
    analysis = read_json(root/'analysis.json')
    curves = read_json(root/'TRAJECTORIES.json')['curves']
    plan = read_json(root/'matrix_plan.json')
    complete = sum(c['complete'] for c in analysis['cells'])
    total = len(plan['cells'])
    seeds = sorted({c['seed'] for c in plan['cells']})
    colors = plt.get_cmap('tab10').colors
    out = root/'figures'
    out.mkdir(exist_ok=True)
    outputs = []
    prompts = ('minimal', 'score', 'full')
    selections = ('paper_truncation',)
    for metric, label, filename in [('default_score', 'Held-out payoff per round', 'holdout_evolution'),
                                    ('default_cooperation', 'Held-out cooperation rate', 'cooperation_evolution')]:
        for budget_axis in (False, True):
            fig, axes = plt.subplots(len(prompts), len(selections),
                                     figsize=(4.2*len(selections), 3*len(prompts)),
                                     sharex=True, sharey=True, squeeze=False)
            for row, prompt in enumerate(prompts):
                for col, selection in enumerate(selections):
                    ax = axes[row, col]
                    available, finished = 0, 0
                    for seed in seeds:
                        name = f'{prompt}__{selection}__seed{seed}'
                        points = curves.get(name, [])
                        if not points:
                            continue
                        available += 1
                        done = len(points) == plan['generations'] and (root/name/'complete.json').exists()
                        finished += done
                        x = [p['requests'] if budget_axis else p['generation'] for p in points]
                        y = [float('nan') if p[metric] is None else p[metric] for p in points]
                        ax.plot(x, y, color=colors[seed % len(colors)], lw=1.4,
                                linestyle='-' if done else '--', marker='o', markersize=2.3)
                        failed = [i for i, p in enumerate(points) if p[metric] is None]
                        if failed:
                            ax.scatter([x[i] for i in failed], [.03]*len(failed), transform=ax.get_xaxis_transform(),
                                       marker='x', color=colors[seed % len(colors)], s=25)
                    ax.set_title(f'{prompt} / {selection}\n{finished}/{len(seeds)} complete; {available} started', fontsize=10)
                    ax.grid(alpha=.2)
                    if metric.endswith('cooperation'):
                        ax.set_ylim(-.03, 1.03)
                    else:
                        ax.set_ylim(-.1, 5.1)
                    if not budget_axis:
                        ax.set_xlim(0, plan['generations']-1)
                    if row == 2:
                        ax.set_xlabel('Cumulative requests' if budget_axis else 'Evaluated generation')
                    if col == 0:
                        ax.set_ylabel(label)
            handles = [plt.Line2D([0], [0], color=colors[s % len(colors)], label=f'Seed {s}') for s in seeds]
            fig.legend(handles=handles, loc='lower center', ncol=len(seeds), bbox_to_anchor=(.5, .028), frameon=False)
            status = 'COMPLETE MAIN MATRIX' if complete == total else 'INTERIM — incomplete main matrix'
            fig.suptitle(f'{status}: {complete}/{total} runs\n{label}', fontsize=14)
            fig.text(.5, .012, 'Dashed: unfinished run. Missing tests are gaps (x at panel bottom). Lines connect observed checkpoints; no imputed scores.',
                     ha='center', fontsize=8)
            fig.tight_layout(rect=(0, .07, 1, .93))
            stem = filename+('_requests' if budget_axis else '_generations')
            for extension in ('png', 'svg'):
                path = out/(stem+'.'+extension)
                fig.savefig(path, dpi=180, facecolor='white')
                outputs.append(str(path.resolve()))
            plt.close(fig)
    write_json(out/'manifest.json', {'main_complete': complete, 'main_total': total,
                                  'source': ['analysis.json', 'TRAJECTORIES.json'], 'files': outputs})
    print({'figures': len(outputs), 'completed_main_runs': complete})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    plot_results(parser.parse_args().root)
