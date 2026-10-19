"""Render the two Results figures from frozen summaries, without inference.

Exports figure2/3 assets from the supplied analysis files.
Layout audits can be called separately with audit_figure().
"""
from __future__ import annotations
import argparse
import json
import os
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
os.environ.setdefault('MPLCONFIGDIR', str(ROOT / 'tmp/results_figure_mplconfig'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import to_hex, to_rgb
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
import numpy as np
from .results_plot_style import save_figure, apply_style, panel_heading, panel_legend, IntervalKey, BLUE, ORANGE, DARK, GREY, GREEN
from .plot_data import fit_axis, interval_values, draw_intervals, finite_values
INPUTS = {}
ORDER = ['DeepSeek/OFF', 'DeepSeek/ON', 'Qwen/OFF', 'Qwen/ON']
DEFAULT_DISPLAY_MODELS = {'DeepSeek': 'deepseek-v4.1-flash', 'Qwen': 'qwen3.8-flash'}
DISPLAY_MODELS = dict(DEFAULT_DISPLAY_MODELS)
SEEDS = []
ARMS = ['accurate', 'mismatched']
GAIN_CONDITIONS = ['mismatched', 'accurate', 'score']

def raw_tint(color):
    """Use the Fig. 3 condition color, mixed with 60% white, for Raw bars."""
    return to_hex(0.4 * np.asarray(to_rgb(color)) + 0.6)

GAIN_COLORS = {'mismatched': (raw_tint(ORANGE), ORANGE),
               'accurate': (raw_tint(BLUE), BLUE),
               'score': (raw_tint(GREEN), GREEN)}
GAIN_KEYS = [f'{stage}_{arm}' for arm in GAIN_CONDITIONS for stage in ['raw', 's3']]
WIDTH, HEIGHT = (175 / 25.4, 138 / 25.4)

def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def vector(report, stage, arm):
    if stage == 'raw':
        values = report['raw'][arm]['metrics']['default/score']['seed_values']
    else:
        values = report['selected']['S3/' + arm]['metrics']['default']['seed_values']
    result = np.asarray(values, dtype=float)
    assert result.ndim == 1 and result.size and np.isfinite(result).all()
    return result


def display_models(manifests):
    """Use recorded model identities before optional environment/default labels."""
    labels = {}
    for provider, cells in [('DeepSeek', ('deepseek_off', 'deepseek_on')),
                            ('Qwen', ('qwen_off', 'qwen_on'))]:
        models = {manifests[cell].get('api', {}).get('model') or manifests[cell].get('model')
                  for cell in cells}
        models.discard(None)
        models.discard('')
        if len(models) > 1:
            raise ValueError(provider + ' OFF and ON manifests must use the same model')
        labels[provider] = (next(iter(models)) if models else
                            os.environ.get(provider.upper() + '_MODEL') or DEFAULT_DISPLAY_MODELS[provider])
    return labels


def load(figure='all'):
    global SEEDS, DISPLAY_MODELS
    if figure == '3':
        return {}, {}, read(INPUTS['opponents']), read(INPUTS['behavior'])
    manifests = {mode: read(INPUTS[f'qwen_{mode}_manifest']) for mode in ('off', 'on')}
    SEEDS = manifests['off']['seeds']
    if not SEEDS or len(set(SEEDS)) != len(SEEDS) or manifests['on']['seeds'] != SEEDS:
        raise ValueError('Configurations must use the same nonempty ordered population seeds')
    all_manifests = {'qwen_' + mode: manifest for mode, manifest in manifests.items()}
    for name in ('deepseek_off', 'deepseek_on'):
        all_manifests[name] = read(INPUTS[name].parent / 'manifest.json')
        if all_manifests[name]['seeds'] != SEEDS:
            raise ValueError('DeepSeek and Qwen population seed orders differ')
    DISPLAY_MODELS = display_models(all_manifests)
    cross = read(INPUTS['cross_model'])['statistics']
    ds_off = read(INPUTS['deepseek_off'])
    ds_on = read(INPUTS['deepseek_on'])['thinking']
    reports = {'DeepSeek/OFF': ds_off, 'DeepSeek/ON': ds_on}
    pairs = {}
    for cell, report in [('DeepSeek/OFF', ds_off), ('DeepSeek/ON', ds_on)]:
        pairs[cell] = {stage: np.mean([vector(report, stage, arm) for arm in ARMS], axis=0)
                       for stage in ['raw', 'S3']}
    for mode in ['off', 'on']:
        report = read(INPUTS[f'qwen_{mode}_analysis'])['result']
        reports['Qwen/' + mode.upper()] = report
        pairs['Qwen/' + mode.upper()] = {stage: np.mean([vector(report, stage, arm) for arm in ARMS], axis=0) for stage in ['raw', 'S3']}
    for cell in ORDER:
        report = reports[cell]
        for arm in GAIN_CONDITIONS:
            for stage in ['raw', 's3']:
                metric = (report['raw'][arm]['metrics']['default/score'] if stage == 'raw'
                          else report['selected']['S3/' + arm]['metrics']['default'])
                key = f'{stage}_{arm}'
                cross[cell][key] = metric
    opponents = read(INPUTS['opponents']) if figure == 'all' else {}
    behavior = read(INPUTS['behavior']) if figure == 'all' else {}
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
    draw_intervals(ax, y, low, high, color=color, elinewidth=1, capsize=2, capthick=0.8, zorder=4)
    ax.plot(mean, y, marker=marker, color=color, markerfacecolor=color if fill else 'white',
            markeredgewidth=.9, markersize=4.6, zorder=4, linestyle='none')

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
    for _, ax, handles, labels, ncol in legend_specs:
        panel_legend(ax, handles, labels, ncol=ncol)
    fig._results_headings = headings
    fig._results_legend_specs = legend_specs


def figure2(cross, pairs):
    apply_style()
    fig = plt.figure(figsize=(WIDTH, HEIGHT), facecolor='white')
    axa = fig.add_axes([0.105, 0.605, 0.40, 0.30])
    axb = fig.add_axes([0.72, 0.605, 0.26, 0.30])
    count = len(ORDER)
    axb.set_ylim(count - .45, -1.35)
    axb.set_yticks(range(count), [f'{DISPLAY_MODELS[model]}\n{mode}' for model, mode in (cell.split('/') for cell in ORDER)])
    clean(axb)
    for key, offset in zip(GAIN_KEYS, [-0.325, -0.215, -0.055, 0.055, 0.215, 0.325]):
        stage, arm = key.split('_')
        color = GAIN_COLORS[arm][stage == 's3']
        rows = [cross[cell][key] for cell in ORDER]
        means = np.asarray([row['mean'] for row in rows])
        intervals = np.asarray([row['ci95'] for row in rows])
        positions = np.arange(count) + offset
        axa.bar(positions, means, width=0.10, color=color, zorder=3)
        draw_intervals(axa, positions, intervals[:, 0], intervals[:, 1], axis='y',
                       ecolor='black', elinewidth=.7, capsize=1, capthick=.7, zorder=4)
    for index, cell in enumerate(ORDER):
        point_interval(axb, cross[cell]['raw_accurate_minus_mismatched'], index, DARK, 'o')
    axa.set_xlim(-.55, count - .45)
    fit_axis(axa, interval_values([cross[cell][key] for cell in ORDER for key in GAIN_KEYS]),
             axis='y', include_zero=True)
    axa.set_xticks(range(count), [cell.split('/')[1] for cell in ORDER])
    for model, center in [('DeepSeek', 0.5), ('Qwen', 2.5)]:
        axa.text(center, -0.286, DISPLAY_MODELS[model], transform=axa.get_xaxis_transform(),
                 ha='center', va='top', fontsize=8.5)
    clean(axa, 'y')
    axa.set_ylabel('Payoff gain per round\nvs parent')
    fit_axis(axb, interval_values([cross[cell]['raw_accurate_minus_mismatched'] for cell in ORDER]),
             include_zero=True)
    axb.set_xlabel('Raw Accurate − Mismatched\n(payoff per round)')
    above = sum(np.count_nonzero(pairs[cell]['S3'] > pairs[cell]['raw']) for cell in ORDER)
    total = sum(len(pairs[cell]['raw']) for cell in ORDER)
    headings = [panel_heading(fig, 'a', 'Information conditions', 0.025, 0.947),
                panel_heading(fig, 'b', 'Correct report matching', 0.535, 0.947),
                panel_heading(fig, 'c', f'Same-pool selection: S3 above Raw in {above} of {total} population pairs', 0.025, 0.470)]
    axb.text(1, 1.01, 'Accurate higher →', transform=axb.transAxes, ha='right', fontsize=8.5, color='#505050')
    lefts = [0.165, 0.3775, 0.59, 0.8025]
    pair_values = np.concatenate([finite_values(row[stage]) for row in pairs.values() for stage in ('raw', 'S3')])
    for i, (cell, left) in enumerate(zip(ORDER, lefts)):
        ax = fig.add_axes([left, 0.110, 0.1775, 0.235])
        row = pairs[cell]
        for raw, s3 in zip(row['raw'], row['S3']):
            ax.plot([0, 1], [raw, s3], color='#C1C1C1', linewidth=0.65, alpha=0.8, zorder=2)
        means = [float(row['raw'].mean()), float(row['S3'].mean())]
        ax.plot([0], [means[0]], marker='o', color=GREY, markerfacecolor='white', markersize=6, zorder=5)
        ax.plot([1], [means[1]], marker='s', color=DARK, markersize=5.5, zorder=5)
        ax.set_xlim(-0.22, 1.22)
        fit_axis(ax, pair_values, axis='y', include_zero=True)
        ax.set_xticks([0, 1], ['Raw', 'S3'])
        if i == 0:
            ax.set_ylabel('Payoff gain per round vs parent')
        else:
            ax.tick_params(labelleft=False)
            ax.spines['left'].set_visible(False)
        clean(ax, 'y')
        model, mode = cell.split('/')
        ax.set_title(f'{DISPLAY_MODELS[model]}\n{mode}', fontsize=9, pad=5)
        fig.text(left + 0.08875, 0.04, f'{means[0]:+.3f} / {means[1]:+.3f}', ha='center', fontsize=8.5, color=DARK)
    # Keep the six-entry legend in a header band, clear of all error bars.
    axa.set_position([0.105, 0.605, 0.40, 0.210])
    a_legend_ax = fig.add_axes([0.105, 0.825, 0.40, 0.112], frameon=False)
    a_legend_ax.set_axis_off()
    a_legend_ax.set_xticks([])
    a_legend_ax.set_yticks([])
    c_legend_ax = fig.add_axes([0.105, 0.415, 0.875, 0.050], frameon=False)
    c_legend_ax.set_axis_off()
    c_legend_ax.set_xticks([])
    c_legend_ax.set_yticks([])
    register_style(fig, headings, [
        ('a', a_legend_ax,
         [Patch(facecolor=GAIN_COLORS[arm][index]) for index in range(2) for arm in GAIN_CONDITIONS],
         [f'{stage}-{arm.capitalize()}' for stage in ['Raw', 'S3'] for arm in GAIN_CONDITIONS], 2),
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
    fig = plt.figure(figsize=(WIDTH, 130 / 25.4), facecolor='white')
    headings = []
    legend_specs = []
    families = opponents['families']
    names = {'recovery': 'Recovery', 'exploitation': 'Exploitation',
             'random': 'Random', 'memory': 'Memory-one'}
    family_names = [names.get(family, family.replace('_', ' ').capitalize()) for family in families]
    ypos = list(reversed(range(len(families))))
    payoff_values = interval_values([
        opponents['configs'][config]['summaries'][stage][arm][family]
        for config in ('non_thinking', 'thinking') for stage in ('raw', 'S3')
        for arm in ARMS for family in families], 'ci95_exploratory_unadjusted')
    for panel, stage, bottom, heading_y, legend_bottom, title in [
        ('a', 'raw', 0.59, 0.96, 0.905, 'Raw candidates'),
        ('b', 'S3', 0.09, 0.48, 0.425, 'S3 outputs'),
    ]:
        # Separate thinking modes into aligned columns, leaving only four
        # opponent-family rows in each plotting area.
        for column, (config, mode, left) in enumerate([
            ('non_thinking', 'OFF', 0.135), ('thinking', 'ON', 0.395)
        ]):
            ax = fig.add_axes([left, bottom, 0.235, 0.255])
            for j, family in enumerate(families):
                y = ypos[j]
                if j % 2 == 0:
                    ax.axhspan(y - 0.5, y + 0.5, color='#F3F5F7', zorder=0)
                for arm, color, marker, offset in [('accurate', BLUE, 'o', 0.26), ('mismatched', ORANGE, 's', -0.26)]:
                    row = opponents['configs'][config]['summaries'][stage][arm][family]
                    point_interval(ax, row, y + offset, color, marker, 'ci95_exploratory_unadjusted')
            ax.set_yticks(ypos, family_names if column == 0 else [])
            ax.set_ylim(-.6, len(families) - .4)
            fit_axis(ax, payoff_values, include_zero=True)
            for separator in np.arange(len(families) - 1) + .5:
                ax.axhline(separator, color='#E1E5E9', linewidth=0.5, zorder=0)
            clean(ax)
            ax.set_title(f'Thinking {mode}', fontsize=9, pad=3)
            ax.set_xlabel('Payoff gain per round')
        headings.append(panel_heading(fig, panel, title, 0.03, heading_y))
        legend_ax = fig.add_axes([0.235, legend_bottom, 0.395, 0.055], frameon=False)
        legend_ax.set_axis_off()
        legend_specs.append((panel, legend_ax,
            [Line2D([], [], color=BLUE, marker='o', lw=0),
             Line2D([], [], color=ORANGE, marker='s', lw=0)],
            ['Accurate', 'Mismatched'], 2))
    for panel, metric, bottom, heading_y, title, ylabel in [('c', 'defection_exposure', 0.59, 0.96, 'Unilateral cooperation', 'Late unilateral cooperation (%)'), ('d', 'recovery_rounds', 0.09, 0.48, 'Capped recovery time', 'Capped recovery time (rounds)')]:
        ax = fig.add_axes([0.70, bottom, 0.275, 0.255])
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
            draw_intervals(ax, x, intervals[:, 0], intervals[:, 1], axis='y', color=DARK,
                           capsize=2, capthick=.8, elinewidth=1, zorder=4)
            ax.plot(x, means, linestyle='none', marker=marker, color=DARK,
                    markerfacecolor=DARK if config == 'non_thinking' else 'white', markersize=4.7, zorder=4)
        draw_intervals(ax, [0], [plo], [phi], axis='y', color=DARK, capsize=2, elinewidth=1, zorder=5)
        ax.plot([0], [pm], linestyle='none', marker='s', color=DARK, markerfacecolor='#A0A0A0', markersize=4.8, zorder=5)
        ax.set_xticks([0, 1, 2], ['Shared\nparent', 'Raw', 'S3'])
        ax.set_xlim(-0.22, 2.22)
        values = interval_values([behavior['configs'][config]['summaries'][key][stage]
                                  for config in ('non_thinking', 'thinking')
                                  for stage in ('parent', 'raw', 'S3')], 'ci95_exploratory') * scale
        fit_axis(ax, values, axis='y', nonnegative=True, headroom=.32)
        ax.set_ylabel(ylabel)
        clean(ax, 'y', zero=False)
        headings.append(panel_heading(fig, panel, title, 0.68, heading_y))
        legend_specs.append((panel, ax,
            [Line2D([], [], color=DARK, marker='o', lw=1, linestyle='-'),
             Line2D([], [], color=DARK, marker='^', markerfacecolor='white', lw=1, linestyle='--'),
             Line2D([], [], color=DARK, marker='s', markerfacecolor='#A0A0A0', lw=0)],
            ['OFF', 'ON', 'Parent'], 3))
    register_style(fig, headings, legend_specs)
    return fig

def normalized_bounds(box, canvas):
    return [float((box.x0-canvas.x0)/canvas.width), float((box.y0-canvas.y0)/canvas.height),
            float((box.x1-canvas.x0)/canvas.width), float((box.y1-canvas.y0)/canvas.height)]

def audit_figure(fig, stem):
    """Explicitly inspect fonts, legends and bounds without exporting files."""
    from matplotlib.text import Text
    from matplotlib.transforms import Bbox
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    hidden = set()
    for ax in fig.axes:
        for axis in (ax.xaxis, ax.yaxis):
            low, high = sorted(axis.get_view_interval())
            for tick in (*axis.get_major_ticks(), *axis.get_minor_ticks()):
                if not low - 1e-10 <= tick.get_loc() <= high + 1e-10:
                    hidden.update((tick.label1, tick.label2))
    texts = [t for t in fig.findobj(Text) if t not in hidden and t.get_visible() and t.get_text().strip()]
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
    meta = {'panel_headings': fig._results_headings, 'legends': [
        {'panel': panel, 'owner': ax, 'legend': ax.get_legend(), 'ncol': ncol,
         'entries': [legend_record(handle, label) for handle, label in zip(handles, labels)]}
        for panel, ax, handles, labels, ncol in fig._results_legend_specs]}
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
    assert all(t.get_text().startswith(f'({p}) ') and t.get_text()[4:].strip()
               for t, p in zip(meta['panel_headings'], expected_panels))
    result = {'width_mm': float(fig.get_figwidth() * 25.4), 'height_mm': float(fig.get_figheight() * 25.4), 'minimum_font_pt': minimum,
              'out_of_canvas_text': outside,
              'legend': {'count': len(legend_records), 'figure_legends': 0,
                         'axis_legends': len(legend_records), 'panels': legend_records},
              'panel_titles': headings, 'text_fonts_and_bounds': text_records,
              'axes_bounds_figure_fraction': [list(ax.get_position().bounds) for ax in fig.axes]}
    return result

def save(fig, directory, stem):
    result = save_figure(fig, stem, directory, dpi=300)
    plt.close(fig)
    return result

def main():
    global INPUTS
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--cross-model', type=Path)
    parser.add_argument('--deepseek-off', type=Path)
    parser.add_argument('--deepseek-on', type=Path)
    parser.add_argument('--qwen-off-manifest', type=Path)
    parser.add_argument('--qwen-off-analysis', type=Path)
    parser.add_argument('--qwen-on-manifest', type=Path)
    parser.add_argument('--qwen-on-analysis', type=Path)
    parser.add_argument('--opponent-profiles', type=Path)
    parser.add_argument('--behavior-analysis', type=Path)
    parser.add_argument('--figure', choices=['all', '2', '3'], default='all',
                        help='Render a single figure without rewriting the other figure assets.')
    args = parser.parse_args()
    paths = {
        'cross_model': args.cross_model,
        'deepseek_off': args.deepseek_off,
        'deepseek_on': args.deepseek_on,
        'qwen_off_manifest': args.qwen_off_manifest,
        'qwen_off_analysis': args.qwen_off_analysis,
        'qwen_on_manifest': args.qwen_on_manifest,
        'qwen_on_analysis': args.qwen_on_analysis,
        'opponents': args.opponent_profiles,
        'behavior': args.behavior_analysis,
    }
    required = (list(paths) if args.figure == 'all' else
                ['opponents', 'behavior'] if args.figure == '3' else
                [name for name in paths if name not in ('opponents', 'behavior')])
    missing = [name for name in required if paths[name] is None]
    if missing:
        parser.error('Missing figure inputs: ' + ', '.join(missing))
    INPUTS = {name: path.resolve() for name, path in paths.items() if path is not None}
    output = args.output_dir.resolve()
    cross, pairs, opponents, behavior = load(args.figure)
    exports = {}
    if args.figure in ['all', '2']:
        exports['figure2'] = save(figure2(cross, pairs), output, 'fig2')
    if args.figure in ['all', '3']:
        exports['figure3'] = save(figure3(opponents, behavior), output, 'fig3')
    print(json.dumps(exports, ensure_ascii=False, indent=2))
if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    main()
