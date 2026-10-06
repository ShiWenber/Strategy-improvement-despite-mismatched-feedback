"""Render the two Results figures from frozen summaries, without inference.

Only figure2/3 assets are written. Source hashes, read keys, population order,
plotted means/intervals and font/canvas checks are emitted as JSON on stdout.
No experiments, model requests, games, bootstrap samples or tests are run.
"""
from __future__ import annotations
from hashlib import sha256
import argparse
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
from matplotlib.patches import Patch
from matplotlib.text import Text
from matplotlib.ticker import FuncFormatter, MaxNLocator
from matplotlib.transforms import Bbox
import numpy as np
from results_plot_style import apply_style, panel_heading, panel_legend, IntervalKey
SOURCES = {}
READ_KEYS = {}
ANALYSIS_SUFFIX = ""
ORDER = ['DeepSeek/OFF', 'DeepSeek/ON', 'Qwen/OFF', 'Qwen/ON']
DISPLAY_MODELS = {'DeepSeek': 'deepseek-v4.1-flash', 'Qwen': 'qwen3.8-flash'}
SEEDS = list(range(200, 220))
ARMS = ['accurate', 'mismatched']
BLUE, ORANGE, DARK, GREY = ('#0072B2', '#D55E00', '#303030', '#737373')
WIDTH, HEIGHT = (175 / 25.4, 138 / 25.4)

def read(rel, keys):
    path = Path(rel)
    if path.name != 'manifest.json':
        path = path.with_name(path.stem + ANALYSIS_SUFFIX + path.suffix)
    rel = path.as_posix()
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
    assert result.shape == (len(SEEDS),) and np.isfinite(result).all()
    return result

def load(run_root=None):
    global SEEDS, ORDER
    if run_root:
        source = run_root.resolve().relative_to(ROOT).as_posix()
        manifest = read(source + '/manifest.json', ['seeds', 'model'])
        SEEDS, ORDER = sorted(manifest['seeds']), ['DeepSeek/OFF']
        DISPLAY_MODELS['DeepSeek'] = manifest['model']
        report = read(source + '/ANALYSIS.json', ['raw', 'selected', 'primary'])
        population = read(source + '/population_summary.json', ['configurations'])['configurations']['Off / 6k']
        assert population['seed_ids'] == SEEDS
        cross = {'DeepSeek/OFF': {
            'raw_mismatched': report['raw']['mismatched']['metrics']['default/score'],
            's3_mismatched': report['selected']['S3/mismatched']['metrics']['default'],
            'raw_accurate_minus_mismatched': report['primary']}}
        pairs = {'DeepSeek/OFF': {stage: np.asarray(population[field]) for stage, field in [('raw', 'raw_seed_means'), ('S3', 's3_seed_means')]}}
        for stage in ['raw', 'S3']:
            assert np.allclose(pairs['DeepSeek/OFF'][stage], np.mean([vector(report, stage, arm) for arm in ARMS], axis=0), atol=1e-12, rtol=0)
        opponents = read(source + '/opponent_profiles.json', ['configs', 'seeds'])
        behavior = read(source + '/behavior.json', ['configs', 'seeds'])
        assert opponents['seeds'] == behavior['seeds'] == SEEDS
        return cross, pairs, opponents, behavior
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
            assert row['n_seeds'] == len(SEEDS)
            assert abs(np.mean(row['seed_values']) - row['mean']) < 1e-12
            assert row['ci95'][0] <= row['mean'] <= row['ci95'][1]
    opponents = read('results/figure4_opponent_profiles_20260926/ANALYSIS.json', ['configs[*].summaries[raw/S3][accurate/mismatched][recovery/exploitation/random/memory].mean', 'configs[*].summaries[raw/S3][accurate/mismatched][recovery/exploitation/random/memory].ci95_exploratory_unadjusted'])
    behavior = read('results/reciprocity_population_visuals_20260924/behavior/ANALYSIS.json', ['configs[*].summaries[controlled/pooled/defection_exposure][parent/raw/S3]', 'configs[*].summaries[controlled/pooled/recovery_rounds][parent/raw/S3]'])
    assert opponents['seeds'] == behavior['seeds'] == SEEDS
    assert opponents['n_independent_populations'] == 20
    for metric in ['defection_exposure', 'recovery_rounds']:
        key = 'controlled/pooled/' + metric
        assert behavior['configs']['non_thinking']['summaries'][key]['parent'] == behavior['configs']['thinking']['summaries'][key]['parent']
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
    if isinstance(handle, tuple):
        return {'label': label, 'handle': 'tuple',
                'components': [legend_record(item, label) for item in handle]}
    if isinstance(handle, Patch):
        return {'label': label, 'handle': 'Patch',
                'facecolor': handle.get_facecolor(), 'edgecolor': handle.get_edgecolor()}
    if isinstance(handle, IntervalKey):
        return {'label': label, 'handle': 'IntervalKey', 'marker': 'horizontal interval with two end caps', 'color': handle.color, 'linewidth': 1}
    return {'label': label, 'handle': 'Line2D', 'marker': handle.get_marker(),
            'marker_facecolor': handle.get_markerfacecolor(),
            'marker_edgecolor': handle.get_markeredgecolor(),
            'color': handle.get_color(), 'linestyle': handle.get_linestyle(),
            'linewidth': handle.get_linewidth()}

def register_style(fig, headings, legend_specs):
    legends = []
    for panel, ax, handles, labels, ncol in legend_specs:
        legends.append({'panel': panel, 'owner': ax,
                        'legend': panel_legend(ax, handles, labels, ncol=ncol),
                        'ncol': ncol,
                        'entries': [legend_record(h, l) for h, l in zip(handles, labels)]})
    fig._results_style = {'legends': legends, 'panel_headings': headings}

def figure2(cross, pairs):
    apply_style()
    n_configs = len(ORDER)
    fig = plt.figure(figsize=(WIDTH, HEIGHT), facecolor='white')
    axa = fig.add_axes([0.105, 0.605, 0.40, 0.30])
    axb = fig.add_axes([0.72, 0.605, 0.26, 0.30])
    axb.set_ylim(n_configs - .45, -1.35)
    axb.set_yticks(range(n_configs), [f'{DISPLAY_MODELS[model]}\n{mode}' for model, mode in (cell.split('/') for cell in ORDER)])
    clean(axb)
    for key, offset, color in [('raw_mismatched', -0.17, GREY), ('s3_mismatched', 0.17, DARK)]:
        rows = [cross[cell][key] for cell in ORDER]
        means = np.asarray([row['mean'] for row in rows])
        intervals = np.asarray([row['ci95'] for row in rows])
        axa.bar(np.arange(n_configs) + offset, means, width=0.28, color=color,
                yerr=np.stack([means - intervals[:, 0], intervals[:, 1] - means]),
                capsize=2.5, error_kw={'ecolor': DARK, 'elinewidth': 1, 'capthick': 0.8}, zorder=3)
    for index, cell in enumerate(ORDER):
        point_interval(axb, cross[cell]['raw_accurate_minus_mismatched'], index, DARK, 'o')
    axa.set_xlim(-0.55, n_configs - .45)
    axa.set_ylim(-0.02, 0.25)
    axa.set_yticks([0, 0.05, 0.1, 0.15, 0.2])
    axa.yaxis.set_major_formatter(FuncFormatter(lambda x, _: f'{x:.2f}'))
    axa.set_xticks(range(n_configs), [cell.split('/')[1] for cell in ORDER])
    for model in dict.fromkeys(cell.split('/')[0] for cell in ORDER):
        center = np.mean([i for i, cell in enumerate(ORDER) if cell.split('/')[0] == model])
        axa.text(center, -0.20, DISPLAY_MODELS[model], transform=axa.get_xaxis_transform(),
                 ha='center', va='top', fontsize=8.5)
    clean(axa, 'y')
    axa.set_ylabel('Payoff gain per round\nvs parent')
    axb.set_xlim(-0.03, 0.035)
    axb.set_xticks([-0.02, 0, 0.02])
    axb.xaxis.set_major_formatter(FuncFormatter(lambda x, _: f'{x:.2f}'))
    axb.set_xlabel('Raw Accurate − Mismatched\n(payoff per round)')
    headings = [panel_heading(fig, 'a', '', 0.025, 0.947),
                panel_heading(fig, 'b', '', 0.535, 0.947),
                panel_heading(fig, 'c', '', 0.025, 0.470)]
    axb.text(1, 1.01, 'Accurate higher →', transform=axb.transAxes, ha='right', fontsize=8.5, color='#505050')
    panel_width = .85 / n_configs - .035
    lefts = [.13 + i * .85 / n_configs for i in range(n_configs)]
    for i, (cell, left) in enumerate(zip(ORDER, lefts)):
        ax = fig.add_axes([left, 0.110, panel_width, 0.235])
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
        fig.text(left + panel_width / 2, 0.04, f'{means[0]:+.3f} / {means[1]:+.3f}', ha='center', fontsize=8.5, color=DARK)
        assert np.min([row['raw'], row['S3']]) > -0.075 and np.max([row['raw'], row['S3']]) < 0.3
    c_legend_ax = fig.add_axes([0.105, 0.415, 0.875, 0.050], frameon=False)
    c_legend_ax.set_axis_off()
    c_legend_ax.set_xticks([])
    c_legend_ax.set_yticks([])
    register_style(fig, headings, [
        ('a', axa, [Patch(facecolor=GREY), Patch(facecolor=DARK)],
         ['Raw', 'S3'], 2),
        ('b', axb, [Line2D([], [], color=DARK, marker='o', lw=0)],
         ['Contrast'], 1),
        ('c', c_legend_ax, [Line2D([], [], color=GREY, marker='o', markerfacecolor='white', lw=0),
                          Line2D([], [], color=DARK, marker='s', lw=0),
                          Line2D([], [], color='#C1C1C1', lw=.65)],
         ['Raw mean', 'S3 mean', 'Population pair'], 3),
    ])
    return fig

def figure3(opponents, behavior):
    apply_style()
    fig = plt.figure(figsize=(WIDTH, 190 / 25.4), facecolor='white')
    headings = []
    legend_specs = []
    families = ['recovery', 'exploitation', 'random', 'memory']
    family_names = ['Recovery', 'Exploitation', 'Random', 'Memory-one']
    intervals = [row['ci95_exploratory_unadjusted'] for config in opponents['configs'].values()
                 for stage in config['summaries'].values() for arm in stage.values()
                 for family, row in arm.items() if family != 'overall']
    payoff_limits = [min(-.13, min(row[0] for row in intervals) - .025),
                     max(.23, max(row[1] for row in intervals) + .025)]
    ypos = [3, 2, 1, 0]
    for panel, stage, bottom, heading_y, legend_bottom, title in [
        ('a', 'raw', 0.745, 0.970, 0.937, ''),
        ('b', 'S3', 0.435, 0.675, 0.642, ''),
    ]:
        # Separate thinking modes into aligned columns, leaving only four
        # opponent-family rows in each plotting area.
        configs = [config for config in ('non_thinking', 'thinking') if config in opponents['configs']]
        for column, config in enumerate(configs):
            mode = 'OFF' if config == 'non_thinking' else 'ON'
            left = .205 + column * .46
            ax = fig.add_axes([left, bottom, .775 if len(configs) == 1 else .31, 0.175])
            for j, family in enumerate(families):
                y = ypos[j]
                if j % 2 == 0:
                    ax.axhspan(y - 0.5, y + 0.5, color='#F3F5F7', zorder=0)
                for arm, color, marker, offset in [('accurate', BLUE, 'o', 0.26), ('mismatched', ORANGE, 's', -0.26)]:
                    row = opponents['configs'][config]['summaries'][stage][arm][family]
                    assert payoff_limits[0] < row['ci95_exploratory_unadjusted'][0] <= row['ci95_exploratory_unadjusted'][1] < payoff_limits[1]
                    point_interval(ax, row, y + offset, color, marker, 'ci95_exploratory_unadjusted')
            ax.set_yticks(ypos, family_names if column == 0 else [])
            ax.set_ylim(-0.6, 3.6)
            ax.set_xlim(*payoff_limits)
            for separator in [0.5, 1.5, 2.5]:
                ax.axhline(separator, color='#E1E5E9', linewidth=0.5, zorder=0)
            ax.xaxis.set_major_locator(MaxNLocator(nbins=4))
            ax.xaxis.set_major_formatter(FuncFormatter(lambda x, _: f'{x:.2f}'))
            clean(ax)
            ax.set_title(f'Thinking {mode}', fontsize=9, pad=3)
            ax.set_xlabel('Payoff gain per round vs parent')
        headings.append(panel_heading(fig, panel, title, 0.03, heading_y))
        legend_ax = fig.add_axes([0.32, legend_bottom, 0.66, 0.045], frameon=False)
        legend_ax.set_axis_off()
        legend_specs.append((panel, legend_ax,
            [Line2D([], [], color=BLUE, marker='o', lw=0),
             Line2D([], [], color=ORANGE, marker='s', lw=0)],
            ['Accurate', 'Mismatched'], 2))
    for panel, metric, left, title, ylabel in [('c', 'defection_exposure', 0.205, 'Late unilateral cooperation', 'Late unilateral cooperation (%)'), ('d', 'recovery_rounds', 0.665, 'Capped recovery time', 'Capped recovery time (rounds)')]:
        ax = fig.add_axes([left, 0.080, 0.31, 0.22])
        key = 'controlled/pooled/' + metric
        scale = 100 if metric == 'defection_exposure' else 1
        baseline = behavior['configs']['non_thinking']['summaries'][key]['parent']
        pm, (plo, phi) = (baseline['mean'] * scale, np.asarray(baseline['ci95_exploratory']) * scale)
        for config, offset, marker, ls in [('non_thinking', -0.045, 'o', '-'), ('thinking', 0.045, '^', '--')]:
            if config not in behavior['configs']:
                continue
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
        upper = max(27, 1.5 * max(row['ci95_exploratory'][1] * scale
                                for config in behavior['configs'].values()
                                for stage, row in config['summaries'][key].items() if stage in ['parent', 'raw', 'S3']))
        ax.set_ylim(0, upper)
        ax.yaxis.set_major_locator(MaxNLocator(nbins=5))
        ax.set_ylabel(ylabel)
        clean(ax, 'y', zero=False)
        headings.append(panel_heading(fig, panel, '', left - 0.025, 0.321))
        handles = [Line2D([], [], color=DARK, marker='o', lw=1, linestyle='-')]
        labels = ['OFF']
        if 'thinking' in behavior['configs']:
            handles.append(Line2D([], [], color=DARK, marker='^', markerfacecolor='white', lw=1, linestyle='--'))
            labels.append('ON')
        handles.append(Line2D([], [], color=DARK, marker='s', markerfacecolor='#A0A0A0', lw=0))
        legend_specs.append((panel, ax, handles, labels + ['Parent'], len(handles)))
    register_style(fig, headings, legend_specs)
    fig._results_layout = {
        'payoff_panels': 'Raw above S3; Thinking OFF and ON in separate columns',
        'family_order': family_names,
        'payoff_row_centres': ypos,
        'report_offsets': {'accurate': 0.26, 'mismatched': -0.26},
        'payoff_limits': payoff_limits,
        'behaviour_panels': 'c and d side by side in the bottom row',
    }
    return fig

def normalized_bounds(box, canvas):
    return [float((box.x0-canvas.x0)/canvas.width), float((box.y0-canvas.y0)/canvas.height),
            float((box.x1-canvas.x0)/canvas.width), float((box.y1-canvas.y0)/canvas.height)]

def save(fig, directory, stem):
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    inactive_ticks = set()
    for ax in fig.axes:
        for axis in (ax.xaxis, ax.yaxis):
            low, high = sorted(axis.get_view_interval())
            for tick in (*axis.get_major_ticks(), *axis.get_minor_ticks()):
                if not low - 1e-10 <= tick.get_loc() <= high + 1e-10:
                    inactive_ticks.update((tick.label1, tick.label2))
    texts = [t for t in fig.findobj(Text) if t not in inactive_ticks and t.get_visible() and t.get_text().strip()]
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
    headings = [{'text': t.get_text(), 'font_pt': float(t.get_fontsize()),
                 'font_weight': t.get_fontweight(), 'horizontal_alignment': t.get_ha(),
                 'bounds_figure_fraction': normalized_bounds(t.get_window_extent(renderer), bounds)} for t in meta['panel_headings']]
    expected_panels = list('abc' if stem == 'fig2' else 'abcd')
    assert [item['panel'] for item in meta['legends']] == expected_panels
    assert not fig.legends
    assert sum(ax.get_legend() is not None for ax in fig.axes) == len(expected_panels)
    legend_records = []
    for item in meta['legends']:
        ax, legend = item['owner'], item['legend']
        legend_box = legend.get_window_extent(renderer)
        owner_box = ax.get_window_extent(renderer)
        assert owner_box.contains(legend_box.x0, legend_box.y0) and owner_box.contains(legend_box.x1, legend_box.y1)
        annotations = [*fig.texts, *[t for other in fig.axes for t in [other.title, *other.texts]]]
        overlaps = [t.get_text() for t in annotations if t.get_visible() and t.get_text().strip()
                    and legend_box.overlaps(t.get_window_extent(renderer))]
        assert not overlaps, (item['panel'], overlaps)
        data_overlaps = []
        data_axes = [ax] if ax.axison else fig.axes
        for artist in [artist for other in data_axes for artist in [*other.lines, *other.patches]]:
            if artist.get_visible() and artist.get_zorder() > 1:
                if legend_box.overlaps(artist.get_window_extent(renderer)):
                    data_overlaps.append(type(artist).__name__)
        for collection in [collection for other in data_axes for collection in other.collections]:
            if collection.get_visible() and collection.get_zorder() > 1:
                for segment in collection.get_segments():
                    points = collection.get_transform().transform(segment)
                    box = Bbox.from_extents(*points.min(axis=0), *points.max(axis=0))
                    if legend_box.overlaps(box):
                        data_overlaps.append(type(collection).__name__)
        assert not data_overlaps, (item['panel'], data_overlaps)
        legend_records.append({'panel': item['panel'], 'location': 'upper center inside panel' if ax.axison else 'dedicated panel header band',
            'ncol': item['ncol'], 'font_pt': 8.5,
            'bounds_figure_fraction': normalized_bounds(legend_box, bounds),
            'owner_bounds_figure_fraction': normalized_bounds(owner_box, bounds),
            'handles': item['entries'], 'overlapping_headings': overlaps,
            'overlapping_data': data_overlaps})
    assert all(t.get_fontsize() == 9.5 and t.get_fontweight() == 'bold' and t.get_ha() == 'left' for t in meta['panel_headings'])
    assert [t.get_text() for t in meta['panel_headings']] == [f'({p})' for p in expected_panels]
    directory.mkdir(parents=True, exist_ok=True)
    exports = {}
    for extension in ['pdf', 'svg', 'png']:
        path = directory / f'{stem}.{extension}'
        fig.savefig(path, dpi=300, facecolor='white')
        exports[str(path.relative_to(ROOT)).replace('\\', '/')] = sha256(path.read_bytes()).hexdigest()
    result = {'width_mm': float(fig.get_figwidth() * 25.4), 'height_mm': float(fig.get_figheight() * 25.4), 'minimum_font_pt': minimum,
              'out_of_canvas_text': outside, 'exports_sha256': exports,
              'legend': {'count': len(legend_records), 'figure_legends': 0,
                         'axis_legends': len(legend_records), 'panels': legend_records},
              'panel_titles': headings, 'text_fonts_and_bounds': text_records,
              'axes_bounds_figure_fraction': [list(ax.get_position().bounds) for ax in fig.axes],
              **({'layout': fig._results_layout} if hasattr(fig, '_results_layout') else {})}
    plt.close(fig)
    return result

def main():
    global ROOT, ANALYSIS_SUFFIX
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, default=ROOT)
    parser.add_argument('--analysis-suffix', default='')
    parser.add_argument('--run-root', type=Path, help='Render one OFF experiment and its downstream summaries.')
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--audit-dir', type=Path)
    parser.add_argument('--figure', choices=['all', '2', '3'], default='all',
                        help='Render a single figure without rewriting the other figure assets.')
    args = parser.parse_args()
    ROOT, ANALYSIS_SUFFIX = args.work.resolve(), args.analysis_suffix
    output = (args.output_dir or ROOT / 'reproduct').resolve()
    cross, pairs, opponents, behavior = load(args.run_root)
    figure1_paths = [ROOT / 'assets/figure1.png']
    figure1_before = {str(p): sha256(p.read_bytes()).hexdigest() for p in figure1_paths}
    exports = {}
    if args.figure in ['all', '2']:
        exports['figure2'] = save(figure2(cross, pairs), output, 'fig2')
    if args.figure in ['all', '3']:
        exports['figure3'] = save(figure3(opponents, behavior), output, 'fig3')
    for rel, digest in SOURCES.items():
        assert sha256((ROOT / rel).read_bytes()).hexdigest() == digest
    assert figure1_before == {str(p): sha256(p.read_bytes()).hexdigest() for p in figure1_paths}
    qa_directory = args.audit_dir or ROOT / 'results/reproduction'
    qa_directory.mkdir(parents=True, exist_ok=True)
    for number, stem in [('figure2', 'fig2'), ('figure3', 'fig3')]:
        if number not in exports:
            continue
        qa = {'status': 'passed', 'asset': stem, 'figure_language': 'English',
              'population_unit': len(SEEDS), 'seed_order': SEEDS, 'source_hashes_unchanged': True,
              'inputs_sha256': SOURCES, 'read_keys': READ_KEYS,
              'render_script_sha256': sha256(Path(__file__).read_bytes()).hexdigest(),
              'style_helper_sha256': sha256(Path(__file__).with_name('results_plot_style.py').read_bytes()).hexdigest(),
              **exports[number],
              'figure1_unchanged': True,
              'science_unchanged': 'Frozen means and stored intervals; render-only changes.'}
        (qa_directory / f'{stem}_qa_reproduct.json').write_text(json.dumps(qa, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    report = {'status': 'passed', 'source_hashes_unchanged': True, 'new_games': 0, 'new_model_calls': 0, 'new_bootstraps': 0, 'new_tests': 0, 'population_unit': len(SEEDS), 'configuration_order': ORDER, 'seed_order': SEEDS, 'sources_sha256': SOURCES, 'read_keys': READ_KEYS, 'exports': exports, 'figure2a_b': {cell: {key: {f: row[f] for f in ['mean', 'ci95']} for key, row in cross[cell].items() if key in ['raw_mismatched', 's3_mismatched', 'raw_accurate_minus_mismatched']} for cell in ORDER}, 'figure2c': {cell: {stage: float(values.mean()) for stage, values in pairs[cell].items()} for cell in ORDER}, 'figure2c_pairs_above_raw': {'total': int(sum((pairs[cell]['S3'] > pairs[cell]['raw']).sum() for cell in ORDER)), 'of': len(SEEDS) * len(ORDER), 'by_cell': {cell: int((pairs[cell]['S3'] > pairs[cell]['raw']).sum()) for cell in ORDER}, 'minimum_pair_difference': float(min((pairs[cell]['S3'] - pairs[cell]['raw']).min() for cell in ORDER))}, 'figure3a_b': {config: {stage: {arm: {family: {'mean': row['mean'], 'ci95': row['ci95_exploratory_unadjusted']} for family, row in arm_rows.items() if family != 'overall'} for arm, arm_rows in stage_rows.items()} for stage, stage_rows in c['summaries'].items()} for config, c in opponents['configs'].items()}, 'figure3c_d': {config: {metric: {stage: {'mean': row['mean'], 'ci95': row['ci95_exploratory']} for stage, row in c['summaries']['controlled/pooled/' + metric].items() if stage in ['parent', 'raw', 'S3']} for metric in ['defection_exposure', 'recovery_rounds']} for config, c in behavior['configs'].items()}, 'figure1_unchanged': True, 'figure_language': 'English only; one shared asset set', 'note': 'Figure2c computes existing within-population equal-condition means only; all intervals are reused frozen values.'}
    print(json.dumps(report, ensure_ascii=False, indent=2))
if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    main()
