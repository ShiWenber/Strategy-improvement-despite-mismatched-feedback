"""Render the two Results figures from frozen summaries, without inference.

Only figure2/3 assets are written. Source hashes, read keys, population order,
plotted means/intervals and font/canvas checks are emitted as JSON on stdout.
No experiments, model requests, games, bootstrap samples or tests are run.
"""
from __future__ import annotations
from hashlib import sha256
import json
import os
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
os.environ.setdefault('MPLCONFIGDIR', str(ROOT / 'tmp/results_figure_mplconfig'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.text import Text
from matplotlib.ticker import FuncFormatter
import numpy as np
from results_plot_style import apply_style, panel_heading, top_legend, IntervalKey
SOURCES = {}
READ_KEYS = {}
ORDER = ['DeepSeek/OFF', 'DeepSeek/ON', 'Qwen/OFF', 'Qwen/ON']
DISPLAY_MODELS = {'DeepSeek': 'deepseek-v4.1-flash', 'Qwen': 'qwen3.8-flash'}
SEEDS = list(range(200, 220))
ARMS = ['accurate', 'mismatched']
BLUE, ORANGE, DARK, GREY = ('#0072B2', '#D55E00', '#303030', '#737373')
WIDTH, HEIGHT = (175 / 25.4, 138 / 25.4)

def read(rel, keys):
    raw = (ROOT / rel).read_bytes()
    SOURCES[rel] = sha256(raw).hexdigest()
    READ_KEYS[rel] = keys
    return json.loads(raw)

def vector(report, stage, arm):
    if stage == 'raw':
        values = report['raw'][arm]['metrics']['default/score']['seed_values']
    else:
        values = report['selected']['S3/' + arm]['metrics']['default']['seed_values']
    result = np.asarray(values, dtype=float)
    assert result.shape == (20,) and np.isfinite(result).all()
    return result

def load():
    cross = read('results/model_comparison_20260928/cross_model_mainline_data.json', ['statistics[*].raw_mismatched', 'statistics[*].s3_mismatched', 'statistics[*].raw_accurate_minus_mismatched'])['statistics']
    population = read('results/reciprocity_population_visuals_20260924/population_summary.json', ['configurations[*].seed_ids', 'configurations[*].raw_seed_means', 'configurations[*].s3_seed_means'])['configurations']
    ds_off = read('results/feedback_specificity_v2/ANALYSIS.json', ['raw[*].metrics.default/score.seed_values', 'selected[S3/*].metrics.default.seed_values'])
    ds_on = read('results/feedback_specificity_thinking_384k_20260923/ANALYSIS.json', ['thinking.raw[*].metrics.default/score.seed_values', 'thinking.selected[S3/*].metrics.default.seed_values'])['thinking']
    pairs = {}
    for cell, cache_key, report in [('DeepSeek/OFF', 'Off / 6k', ds_off), ('DeepSeek/ON', 'On / 384k', ds_on)]:
        row = population[cache_key]
        assert row['seed_ids'] == SEEDS
        pairs[cell] = {stage: np.asarray(row[field], dtype=float) for stage, field in [('raw', 'raw_seed_means'), ('S3', 's3_seed_means')]}
        for stage in ['raw', 'S3']:
            assert np.allclose(pairs[cell][stage], np.mean([vector(report, stage, a) for a in ARMS], axis=0), atol=1e-12, rtol=0)
    for mode in ['off', 'on']:
        rel = f'results/qwen3_8/{mode}/'
        manifest = read(rel + 'manifest.json', ['seeds'])
        assert manifest['seeds'] == SEEDS
        report = read(rel + 'ANALYSIS.json', ['result.raw[*].metrics.default/score.seed_values', 'result.selected[S3/*].metrics.default.seed_values'])['result']
        pairs['Qwen/' + mode.upper()] = {stage: np.mean([vector(report, stage, arm) for arm in ARMS], axis=0) for stage in ['raw', 'S3']}
    for cell in ORDER:
        for key in ['raw_mismatched', 's3_mismatched', 'raw_accurate_minus_mismatched']:
            row = cross[cell][key]
            assert row['n_seeds'] == 20
            assert abs(np.mean(row['seed_values']) - row['mean']) < 1e-12
            assert row['ci95'][0] < row['mean'] < row['ci95'][1]
        assert cross[cell]['raw_accurate_minus_mismatched']['ci95'][0] < 0 < cross[cell]['raw_accurate_minus_mismatched']['ci95'][1]
    opponents = read('results/figure4_opponent_profiles_20260926/ANALYSIS.json', ['configs[*].summaries[raw/S3][accurate/mismatched][recovery/exploitation/random/memory].mean', 'configs[*].summaries[raw/S3][accurate/mismatched][recovery/exploitation/random/memory].ci95_exploratory_unadjusted'])
    behavior = read('results/reciprocity_population_visuals_20260924/behavior/ANALYSIS.json', ['configs[*].summaries[controlled/pooled/defection_exposure][parent/raw/S3]', 'configs[*].summaries[controlled/pooled/recovery_rounds][parent/raw/S3]'])
    assert opponents['seeds'] == behavior['seeds'] == SEEDS
    assert opponents['n_independent_populations'] == 20
    for metric in ['defection_exposure', 'recovery_rounds']:
        key = 'controlled/pooled/' + metric
        assert behavior['configs']['non_thinking']['summaries'][key]['parent'] == behavior['configs']['thinking']['summaries'][key]['parent']
    # Figure 2c carries this claim in its heading; keep it enforced by the data.
    assert sum(int(np.sum(pairs[cell]['S3'] > pairs[cell]['raw'])) for cell in ORDER) == 79
    return (cross, pairs, opponents, behavior)

def clean(ax, direction='x', zero=True):
    ax.grid(axis=direction, color='#E8E8E8', linewidth=0.5, zorder=0)
    if zero:
        if direction == 'x':
            ax.axvline(0, color='#888888', linewidth=0.7, zorder=1)
        else:
            ax.axhline(0, color='#888888', linewidth=0.7, zorder=1)
    ax.tick_params(axis='y', length=0, pad=5)
    ax.spines['left'].set_visible(False if direction == 'x' else True)

def point_interval(ax, row, y, color, marker, key='ci95', fill=True):
    mean, (low, high) = (row['mean'], row[key])
    ax.errorbar(mean, y, xerr=[[mean - low], [high - mean]], fmt=marker, color=color, markerfacecolor=color if fill else 'white', markeredgecolor=color, markeredgewidth=0.9, markersize=4.6, elinewidth=1, capsize=2, capthick=0.8, zorder=4)

def legend_record(handle, label):
    if isinstance(handle, IntervalKey):
        return {'label': label, 'handle': 'IntervalKey', 'marker': 'horizontal interval with two end caps', 'color': handle.color, 'linewidth': 1}
    return {'label': label, 'handle': 'Line2D', 'marker': handle.get_marker(),
            'marker_facecolor': handle.get_markerfacecolor(),
            'marker_edgecolor': handle.get_markeredgecolor(),
            'color': handle.get_color(), 'linestyle': handle.get_linestyle(),
            'linewidth': handle.get_linewidth()}

def register_style(fig, handles, labels, headings, scope_texts=()):
    legend = top_legend(fig, handles, labels, ncol=3)
    fig._results_style = {'legend': legend,
                         'legend_entries': [legend_record(h, l) for h, l in zip(handles, labels)],
                         'panel_headings': headings, 'scope_texts': list(scope_texts)}

def figure2(cross, pairs):
    apply_style()
    fig = plt.figure(figsize=(WIDTH, HEIGHT), facecolor='white')
    axa = fig.add_axes([0.21, 0.605, 0.30, 0.23])
    axb = fig.add_axes([0.72, 0.605, 0.26, 0.23])
    for ax in [axa, axb]:
        ax.set_ylim(3.55, -0.55)
        ax.set_yticks(range(4), [f'{DISPLAY_MODELS[model]}\n{mode}' for model, mode in (cell.split('/') for cell in ORDER)])
        clean(ax)
    for index, cell in enumerate(ORDER):
        point_interval(axa, cross[cell]['raw_mismatched'], index - 0.13, GREY, 'o', fill=False)
        point_interval(axa, cross[cell]['s3_mismatched'], index + 0.13, DARK, 's')
        point_interval(axb, cross[cell]['raw_accurate_minus_mismatched'], index, DARK, 'o')
    axa.set_xlim(-0.02, 0.2)
    axa.set_xticks([0, 0.05, 0.1, 0.15, 0.2])
    axb.set_xlim(-0.03, 0.035)
    axb.set_xticks([-0.02, 0, 0.02])
    for ax in [axa, axb]:
        ax.xaxis.set_major_formatter(FuncFormatter(lambda x, _: f'{x:.2f}'))
    axa.set_xlabel('Payoff gain per round vs parent')
    axb.set_xlabel('Raw Accurate − Mismatched\n(payoff per round)')
    headings = [panel_heading(fig, 'a', 'Mismatched: gains over parents', 0.025, 0.870),
                panel_heading(fig, 'b', 'Correct report matching', 0.535, 0.870),
                panel_heading(fig, 'c', 'Same-pool selection: S3 above Raw in 79 of 80 population pairs', 0.025, 0.470)]
    axb.text(1, 1.01, 'Accurate higher →', transform=axb.transAxes, ha='right', fontsize=8.5, color='#505050')
    lefts = [0.165, 0.3775, 0.59, 0.8025]
    for i, (cell, left) in enumerate(zip(ORDER, lefts)):
        ax = fig.add_axes([left, 0.110, 0.1775, 0.275])
        row = pairs[cell]
        for raw, s3 in zip(row['raw'], row['S3']):
            ax.plot([0, 1], [raw, s3], color='#C1C1C1', linewidth=0.65, alpha=0.8, zorder=2)
        means = [float(row['raw'].mean()), float(row['S3'].mean())]
        ax.plot([0], [means[0]], marker='o', color=GREY, markerfacecolor='white', markersize=6, zorder=5)
        ax.plot([1], [means[1]], marker='s', color=DARK, markersize=5.5, zorder=5)
        ax.set_xlim(-0.22, 1.22)
        ax.set_ylim(-0.075, 0.3)
        ax.set_xticks([0, 1], ['Raw', 'S3'])
        ax.set_yticks([-0.05, 0, 0.1, 0.2, 0.3])
        ax.yaxis.set_major_formatter(FuncFormatter(lambda x, _: f'{x:.2f}'))
        if i == 0:
            ax.set_ylabel('Payoff gain per round vs parent')
        else:
            ax.tick_params(labelleft=False)
            ax.spines['left'].set_visible(False)
        clean(ax, 'y')
        model, mode = cell.split('/')
        ax.set_title(f'{DISPLAY_MODELS[model]}\n{mode}', fontsize=9, pad=5)
        fig.text(left + 0.08875, 0.04, f'{means[0]:+.3f} / {means[1]:+.3f}', ha='center', fontsize=8.5, color=DARK)
        assert np.min([row['raw'], row['S3']]) > -0.075 and np.max([row['raw'], row['S3']]) < 0.3
    handles = [Line2D([], [], color=GREY, marker='o', markerfacecolor='white', lw=0),
               Line2D([], [], color=DARK, marker='s', markerfacecolor=DARK, lw=0),
               Line2D([], [], color=DARK, marker='o', markerfacecolor=DARK, lw=0),
               Line2D([], [], color='#C1C1C1', lw=0.65), IntervalKey(GREY)]
    labels = ['Raw mean (a,c)', 'S3 mean (a,c)', 'Matching contrast (b)',
              'Population pair (c)', 'Stored 95% CI (a,b)']
    register_style(fig, handles, labels, headings)
    return fig

def figure3(opponents, behavior):
    apply_style()
    fig = plt.figure(figsize=(WIDTH, HEIGHT), facecolor='white')
    scope_texts = [fig.text(0.5, 0.875, '$H$ payoff · Accurate / Mismatched · deepseek-v4.1-flash', ha='center', fontsize=9)]
    headings = []
    families = ['recovery', 'exploitation', 'random', 'memory']
    family_names = ['Recovery', 'Exploitation', 'Random', 'Memory-one']
    ypos = [10.5, 9.5, 7.5, 6.5, 4.5, 3.5, 1.5, 0.5]
    for panel, stage, left in [('a', 'raw', 0.19), ('b', 'S3', 0.67)]:
        ax = fig.add_axes([left, 0.535, 0.31, 0.26])
        labels = []
        for j, (family, name) in enumerate(zip(families, family_names)):
            for m, config in enumerate(['non_thinking', 'thinking']):
                y = ypos[2 * j + m]
                labels.append(f'{name} · OFF' if m == 0 and panel == 'a' else 'ON' if m else 'OFF')
                for arm, color, marker, offset in [('accurate', BLUE, 'o', 0.26), ('mismatched', ORANGE, 's', -0.26)]:
                    row = opponents['configs'][config]['summaries'][stage][arm][family]
                    assert -0.13 < row['ci95_exploratory_unadjusted'][0] < row['ci95_exploratory_unadjusted'][1] < 0.23
                    point_interval(ax, row, y + offset, color, marker, 'ci95_exploratory_unadjusted')
        ax.set_yticks(ypos, labels)
        ax.set_ylim(-0.15, 11.15)
        ax.set_xlim(-0.13, 0.23)
        for separator in [2.5, 5.5, 8.5]:
            ax.axhline(separator, color='#E8E8E8', linewidth=0.5, zorder=0)
        ax.set_xticks([-0.1, 0, 0.1, 0.2])
        ax.xaxis.set_major_formatter(FuncFormatter(lambda x, _: f'{x:.2f}'))
        clean(ax)
        ax.set_xlabel('Payoff gain per round vs parent')
        headings.append(panel_heading(fig, panel, 'Raw payoff' if stage == 'raw' else 'S3 payoff', left - 0.025, 0.830))
    scope_texts.append(fig.text(0.5, 0.430, "F′ behaviour · Two report conditions averaged · deepseek-v4.1-flash", ha='center', fontsize=9))
    for panel, metric, left, ylabel, heading in [('c', 'defection_exposure', 0.19, 'Late unilateral cooperation (%)', 'Unilateral cooperation'), ('d', 'recovery_rounds', 0.67, 'Capped recovery time (rounds)', 'Recovery time')]:
        ax = fig.add_axes([left, 0.115, 0.31, 0.235])
        key = 'controlled/pooled/' + metric
        scale = 100 if metric == 'defection_exposure' else 1
        baseline = behavior['configs']['non_thinking']['summaries'][key]['parent']
        pm, (plo, phi) = (baseline['mean'] * scale, np.asarray(baseline['ci95_exploratory']) * scale)
        for config, offset, marker, ls in [('non_thinking', -0.045, 'o', '-'), ('thinking', 0.045, '^', '--')]:
            summaries = behavior['configs'][config]['summaries'][key]
            rows = [summaries['raw'], summaries['S3']]
            x = np.asarray([1, 2]) + offset
            means = np.asarray([row['mean'] for row in rows]) * scale
            intervals = np.asarray([row['ci95_exploratory'] for row in rows]) * scale
            ax.plot([0, *x], [pm, *means], color=DARK, linestyle=ls, linewidth=1, zorder=2)
            ax.errorbar(x, means, yerr=np.stack([means - intervals[:, 0], intervals[:, 1] - means]), fmt=marker, color=DARK, markerfacecolor=DARK if config == 'non_thinking' else 'white', markersize=4.7, capsize=2, capthick=0.8, elinewidth=1, zorder=4)
        ax.errorbar([0], [pm], yerr=[[pm - plo], [phi - pm]], fmt='s', color=DARK, markerfacecolor='#A0A0A0', markersize=4.8, capsize=2, elinewidth=1, zorder=5)
        ax.set_xticks([0, 1, 2], ['Shared\nparent', 'Raw', 'S3'])
        ax.set_xlim(-0.22, 2.22)
        ax.set_ylim(0, 20)
        ax.set_yticks([0, 5, 10, 15, 20])
        ax.set_ylabel(ylabel)
        clean(ax, 'y', zero=False)
        headings.append(panel_heading(fig, panel, heading, left - 0.025, 0.385))
    handles = [Line2D([], [], color=BLUE, marker='o', markerfacecolor=BLUE, lw=0),
               Line2D([], [], color=ORANGE, marker='s', markerfacecolor=ORANGE, lw=0),
               Line2D([], [], color=DARK, marker='s', markerfacecolor='#A0A0A0', lw=0),
               Line2D([], [], color=DARK, marker='o', markerfacecolor=DARK, lw=1, linestyle='-'),
               Line2D([], [], color=DARK, marker='^', markerfacecolor='white', lw=1, linestyle='--'),
               IntervalKey(GREY)]
    labels = ['Accurate mean (a,b)', 'Mismatched mean (a,b)', 'Shared parent (c,d)',
              'Thinking OFF (c,d)', 'Thinking ON (c,d)', 'Stored 95% CI (a–d)']
    register_style(fig, handles, labels, headings, scope_texts)
    return fig

def normalized_bounds(box, canvas):
    return [float((box.x0-canvas.x0)/canvas.width), float((box.y0-canvas.y0)/canvas.height),
            float((box.x1-canvas.x0)/canvas.width), float((box.y1-canvas.y0)/canvas.height)]

def save(fig, directory, stem):
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    texts = [t for t in fig.findobj(Text) if t.get_visible() and t.get_text().strip()]
    minimum = min(t.get_fontsize() for t in texts)
    assert minimum >= 8.5
    bounds = fig.bbox
    outside = []
    text_records = []
    for text in texts:
        box = text.get_window_extent(renderer)
        text_records.append({'text': text.get_text(), 'font_pt': float(text.get_fontsize()),
                             'font_weight': text.get_fontweight(), 'bounds_figure_fraction': normalized_bounds(box, bounds)})
        if box.x0 < bounds.x0 - 0.1 or box.x1 > bounds.x1 + 0.1 or box.y0 < bounds.y0 - 0.1 or box.y1 > bounds.y1 + 0.1:
            outside.append(text.get_text())
    assert not outside, outside
    meta = fig._results_style
    legend = meta['legend']
    legend_box = legend.get_window_extent(renderer)
    headings = [{'text': t.get_text(), 'font_pt': float(t.get_fontsize()),
                 'font_weight': t.get_fontweight(), 'horizontal_alignment': t.get_ha(),
                 'bounds_figure_fraction': normalized_bounds(t.get_window_extent(renderer), bounds)} for t in meta['panel_headings']]
    assert len(fig.legends) == 1 and all(ax.get_legend() is None for ax in fig.axes)
    overlaps = [t.get_text() for t in meta['panel_headings'] + meta['scope_texts'] if legend_box.overlaps(t.get_window_extent(renderer))]
    assert not overlaps, overlaps
    assert all(t.get_fontsize() == 9.5 and t.get_fontweight() == 'bold' and t.get_ha() == 'left' for t in meta['panel_headings'])
    directory.mkdir(exist_ok=True)
    exports = {}
    for extension in ['pdf', 'svg', 'png']:
        path = directory / f'{stem}.{extension}'
        fig.savefig(path, dpi=300, facecolor='white')
        exports[str(path.relative_to(ROOT)).replace('\\', '/')] = sha256(path.read_bytes()).hexdigest()
    result = {'width_mm': 175, 'height_mm': 138, 'minimum_font_pt': minimum,
              'out_of_canvas_text': outside, 'exports_sha256': exports,
              'legend': {'count': 1, 'axis_legends': 0, 'location': 'upper center',
                         'anchor_figure_fraction': [0.5, 0.988], 'ncol': 3, 'rows': 2,
                         'font_pt': 8.5, 'bounds_figure_fraction': normalized_bounds(legend_box, bounds),
                         'handles': meta['legend_entries'], 'overlapping_headings': overlaps},
              'panel_titles': headings, 'text_fonts_and_bounds': text_records,
              'axes_bounds_figure_fraction': [list(ax.get_position().bounds) for ax in fig.axes]}
    plt.close(fig)
    return result

def main():
    cross, pairs, opponents, behavior = load()
    figure1_paths = [ROOT / 'assets/figure1.png']
    figure1_before = {str(p): sha256(p.read_bytes()).hexdigest() for p in figure1_paths}
    exports = {'figure2': save(figure2(cross, pairs), ROOT / 'reproduct', 'fig2'),
               'figure3': save(figure3(opponents, behavior), ROOT / 'reproduct', 'fig3')}
    for rel, digest in SOURCES.items():
        assert sha256((ROOT / rel).read_bytes()).hexdigest() == digest
    assert figure1_before == {str(p): sha256(p.read_bytes()).hexdigest() for p in figure1_paths}
    qa_directory = ROOT / 'results/reproduction'
    qa_directory.mkdir(parents=True, exist_ok=True)
    for number, stem in [('figure2', 'fig2'), ('figure3', 'fig3')]:
        qa = {'status': 'passed', 'asset': stem, 'figure_language': 'English',
              'population_unit': 20, 'seed_order': SEEDS, 'source_hashes_unchanged': True,
              'inputs_sha256': SOURCES, 'read_keys': READ_KEYS,
              'render_script_sha256': sha256(Path(__file__).read_bytes()).hexdigest(),
              'style_helper_sha256': sha256(Path(__file__).with_name('results_plot_style.py').read_bytes()).hexdigest(),
              **exports[number],
              'figure1_unchanged': True,
              'science_unchanged': 'Frozen means and stored intervals; render-only changes.'}
        (qa_directory / f'{stem}_qa_reproduct.json').write_text(json.dumps(qa, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    report = {'status': 'passed', 'source_hashes_unchanged': True, 'new_games': 0, 'new_model_calls': 0, 'new_bootstraps': 0, 'new_tests': 0, 'population_unit': 20, 'configuration_order': ORDER, 'seed_order': SEEDS, 'sources_sha256': SOURCES, 'read_keys': READ_KEYS, 'exports': exports, 'figure2a_b': {cell: {key: {f: row[f] for f in ['mean', 'ci95']} for key, row in cross[cell].items() if key in ['raw_mismatched', 's3_mismatched', 'raw_accurate_minus_mismatched']} for cell in ORDER}, 'figure2c': {cell: {stage: float(values.mean()) for stage, values in pairs[cell].items()} for cell in ORDER}, 'figure2c_pairs_above_raw': {'total': int(sum((pairs[cell]['S3'] > pairs[cell]['raw']).sum() for cell in ORDER)), 'of': 20 * len(ORDER), 'by_cell': {cell: int((pairs[cell]['S3'] > pairs[cell]['raw']).sum()) for cell in ORDER}, 'minimum_pair_difference': float(min((pairs[cell]['S3'] - pairs[cell]['raw']).min() for cell in ORDER))}, 'figure3a_b': {config: {stage: {arm: {family: {'mean': row['mean'], 'ci95': row['ci95_exploratory_unadjusted']} for family, row in arm_rows.items() if family != 'overall'} for arm, arm_rows in stage_rows.items()} for stage, stage_rows in c['summaries'].items()} for config, c in opponents['configs'].items()}, 'figure3c_d': {config: {metric: {stage: {'mean': row['mean'], 'ci95': row['ci95_exploratory']} for stage, row in c['summaries']['controlled/pooled/' + metric].items() if stage in ['parent', 'raw', 'S3']} for metric in ['defection_exposure', 'recovery_rounds']} for config, c in behavior['configs'].items()}, 'figure1_unchanged': True, 'figure_language': 'English only; one shared asset set', 'note': 'Figure2c computes existing within-population equal-condition means only; all intervals are reused frozen values.'}
    print(json.dumps(report, ensure_ascii=False, indent=2))
if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    main()
