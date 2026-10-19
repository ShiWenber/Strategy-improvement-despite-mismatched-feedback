"""Renderers must follow new inputs rather than the paper's observed outcomes."""
import copy
import json
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pytest

from experiments.direct_reciprocity.figures import plot_results_three_figures as main
from experiments.direct_reciprocity.figures import plot_camera_ready as camera
from experiments.direct_reciprocity.figures import build_interface_figures as distribution
from experiments.direct_reciprocity.figures.plot_mismatch_distance import distance_figure
from experiments.direct_reciprocity.figures.plot_opponent_profiles import opponent_figure
from experiments.direct_reciprocity.figures.plot_data import data_limits, draw_intervals, interval_values
from experiments.direct_reciprocity.figures.results_plot_audit import validate_panel_layout


@pytest.fixture(autouse=True)
def close_figures():
    yield
    plt.close('all')


def statistic(values, key='ci95'):
    values = np.asarray(values, dtype=float)
    center = float(values.mean())
    return {'mean': center, key: [center - .05, center + .05],
            'seed_values': values.tolist(), 'n_seeds': len(values)}


def source_fixture(tmp_path, monkeypatch, count):
    seeds = list(range(701, 701 + count))
    reports = {}
    for cell in main.ORDER:
        report = {'raw': {}, 'selected': {}}
        for arm, level in [('accurate', .7), ('mismatched', .1), ('score', -.2)]:
            values = np.full(count, level)
            report['raw'][arm] = {'metrics': {'default/score': statistic(values)}}
            for rule in ('S1', 'S2', 'S3'):
                report['selected'][rule + '/' + arm] = {'metrics': {'default': statistic(values + .2)}}
        reports[cell] = report
    cross = {'statistics': {cell: {
        'raw_mismatched': copy.deepcopy(report['raw']['mismatched']['metrics']['default/score']),
        's3_mismatched': copy.deepcopy(report['selected']['S3/mismatched']['metrics']['default']),
        'raw_accurate_minus_mismatched': statistic(np.full(count, .6)),
    } for cell, report in reports.items()}}
    opponents = {'seeds': seeds, 'n_independent_populations': count,
                 'families': ['recovery', 'random'], 'configs': {}}
    behavior = {'seeds': seeds, 'configs': {}}
    for config in ('non_thinking', 'thinking'):
        opponents['configs'][config] = {'summaries': {
            stage: {arm: {family: statistic(np.full(count, 1.5), 'ci95_exploratory_unadjusted')
                          for family in opponents['families']} for arm in main.ARMS}
            for stage in ('raw', 'S3')}}
        behavior['configs'][config] = {'summaries': {
            'controlled/pooled/' + metric: {
                stage: statistic(np.full(count, level + index * step), 'ci95_exploratory')
                for index, stage in enumerate(('parent', 'raw', 'S3'))}
            for metric, level, step in [('defection_exposure', .4, .1), ('recovery_rounds', 45., 10.)]}}

    paths = {}
    for name, cell, wrapper in [('deepseek_off', 'DeepSeek/OFF', None),
                                ('deepseek_on', 'DeepSeek/ON', 'thinking'),
                                ('qwen_off_analysis', 'Qwen/OFF', 'result'),
                                ('qwen_on_analysis', 'Qwen/ON', 'result')]:
        path = tmp_path / name / 'ANALYSIS.json'
        path.parent.mkdir()
        payload = {wrapper: reports[cell]} if wrapper else reports[cell]
        path.write_text(json.dumps(payload), encoding='utf-8')
        manifest = path.parent / 'manifest.json'
        manifest.write_text(json.dumps({'seeds': seeds}), encoding='utf-8')
        paths[name] = path
        if name.startswith('qwen_'):
            paths[name.replace('_analysis', '_manifest')] = manifest
    for name, payload in [('cross_model', cross), ('opponents', opponents), ('behavior', behavior)]:
        paths[name] = tmp_path / (name + '.json')
        paths[name].write_text(json.dumps(payload), encoding='utf-8')
    monkeypatch.setattr(main, 'INPUTS', paths)
    monkeypatch.setattr(main, 'SEEDS', [])
    return seeds, reports, opponents, behavior


def assert_intervals_visible(fig):
    for ax in fig.axes:
        left, right = sorted(ax.get_xlim())
        bottom, top = sorted(ax.get_ylim())
        for collection in ax.collections:
            if hasattr(collection, 'get_segments'):
                for segment in collection.get_segments():
                    assert np.all(segment[:, 0] >= left) and np.all(segment[:, 0] <= right)
                    assert np.all(segment[:, 1] >= bottom) and np.all(segment[:, 1] <= top)


@pytest.mark.parametrize('count', [1, 3, 7])
def test_main_figures_accept_changed_outcomes_and_population_counts(tmp_path, monkeypatch, count):
    seeds, _, _, _ = source_fixture(tmp_path, monkeypatch, count)
    cross, pairs, _, _ = main.load()
    assert main.SEEDS == seeds
    assert cross['DeepSeek/OFF']['raw_accurate_minus_mismatched']['ci95'][0] > 0
    fig = main.figure2(cross, pairs)
    heading = next(text.get_text() for text in fig.texts if 'population pairs' in text.get_text())
    assert f'{count * len(main.ORDER)} of {count * len(main.ORDER)}' in heading
    assert fig.axes[0].get_ylim()[1] > .9
    assert_intervals_visible(fig)


def test_paired_heading_updates_when_selection_does_not_improve(tmp_path, monkeypatch):
    source_fixture(tmp_path, monkeypatch, 3)
    cross, pairs, _, _ = main.load()
    for row in pairs.values():
        row['S3'] = row['raw'] - 1
    fig = main.figure2(cross, pairs)
    assert any('0 of 12 population pairs' in text.get_text() for text in fig.texts)
    assert min(ax.get_ylim()[0] for ax in fig.axes[2:6]) < -.6


def test_main_opponent_and_behavior_axes_follow_input_intervals(tmp_path, monkeypatch):
    _, _, opponents, behavior = source_fixture(tmp_path, monkeypatch, 3)
    fig = main.figure3(opponents, behavior)
    assert len(fig.axes[0].get_yticklabels()) == len(opponents['families'])
    assert fig.axes[0].get_xlim()[1] > 1.5
    assert fig.axes[-1].get_ylim()[1] > 65
    assert_intervals_visible(fig)


@pytest.mark.parametrize('figure', ['2', '3'])
def test_single_main_figure_does_not_require_unrelated_reports(tmp_path, monkeypatch, figure):
    source_fixture(tmp_path, monkeypatch, 3)
    paths = main.INPUTS
    keys = {'opponents', 'behavior'}
    if figure == '2':
        keys = set(paths) - keys
    monkeypatch.setattr(main, 'INPUTS', {key: paths[key] for key in keys})

    cross, pairs, opponents, behavior = main.load(figure)

    if figure == '2':
        assert set(cross) == set(pairs) == set(main.ORDER)
        assert opponents == behavior == {}
    else:
        assert cross == pairs == {}
        assert opponents['families'] == ['recovery', 'random']
        assert set(behavior['configs']) == {'non_thinking', 'thinking'}


@pytest.mark.parametrize('figure, flag, maker', [
    (4, '--off-analysis', 'make_figure4'),
    (5, '--off-role-analysis', 'make_figure5'),
])
def test_single_camera_figure_loads_only_its_report(tmp_path, monkeypatch, capsys, figure, flag, maker):
    report = {'new_report': maker}
    path = tmp_path / 'analysis.json'
    path.write_text(json.dumps(report), encoding='utf-8')
    captured = []
    monkeypatch.setattr(camera, maker, captured.append)
    monkeypatch.setattr(sys, 'argv', ['camera', '--figures', str(figure),
                                    flag, str(path), '--output-dir', str(tmp_path / 'plots')])

    camera.main()

    assert captured == [report]
    assert json.loads(capsys.readouterr().out) == []


def test_supplementary_opponent_axes_follow_the_input(tmp_path, monkeypatch):
    _, _, opponents, _ = source_fixture(tmp_path, monkeypatch, 3)
    fig = opponent_figure(opponents)
    assert fig.axes[0].get_xlim()[1] > 1.5
    assert len(fig.axes[0].get_yticklabels()) == len(opponents['families'])
    assert_intervals_visible(fig)


@pytest.mark.parametrize('values', [[-9., -2., 0., 1., 4., 12.], [5., 5., 5.], [2.]])
def test_density_display_uses_all_observations_without_a_fixed_range(values):
    pop = {mode: {'n': len(values), 'all_raw_gains': values} for mode in distribution.MODES}
    display = distribution.build_display(pop, bins=8)
    for mode in distribution.MODES:
        bars = display['histograms'][mode]
        assert bars[0]['left'] <= min(values) and bars[-1]['right'] >= max(values)
        assert sum((bar['right'] - bar['left']) * bar['height'] for bar in bars) == pytest.approx(1.)
        assert display['sample_sizes'][mode] == len(values)
        assert bool(display['density_curves'][mode]) == (len(set(values)) > 1)


def test_distribution_includes_equal_payoffs_and_actual_pool_counts(tmp_path, monkeypatch):
    captured = []
    monkeypatch.setattr(distribution, 'save_figure', lambda fig, *args, **kwargs: captured.append(fig) or {})
    pop = {}
    for index, mode in enumerate(distribution.MODES):
        counts = {'s3_retained_parent': 1, 's3_accepted_test_better': 1,
                  's3_accepted_test_worse': index, 's3_accepted_test_equal': 1}
        pools = sum(counts.values())
        pop[mode] = {**counts, 'n': pools * 2, 'all_raw_gains': list(np.linspace(-3, 4, pools * 2)),
                     's3_accepted': pools - counts['s3_retained_parent']}
    distribution.generation_figure(pop, distribution.build_display(pop), tmp_path)
    fig, = captured
    ax = fig.axes[1]
    assert 'Selected: H = 0' in [text.get_text() for text in ax.get_legend().get_texts()]
    assert sum(patch.get_width() for patch in ax.patches if patch.get_y() < .5) == pytest.approx(3.)
    assert ax.get_xlim()[1] == pytest.approx(4.)
    assert '120' not in ax.get_xlabel()
    validate_panel_layout(fig, 'figS2')


def test_distance_display_follows_pair_count_and_scale():
    values = [80., 100., 160.]
    data = {'rows': [{'context': f'p{index}', 'delta_full': value} for index, value in enumerate(values)],
            'distance_summary': {'delta_full': {'min': min(values), 'max': max(values), 'mean': np.mean(values)}},
            'distance_diagnostics': {'null_within_population_ordered_pairs': {
                'n': 42, 'q10': 75., 'q90': 120., 'mean': 95.}}}
    fig = distance_figure(data, copy.deepcopy(data))
    assert '3 parent-donor pairs' in fig.axes[0].get_title(loc='left')
    assert all(ax.get_xlim()[1] > max(values) for ax in fig.axes)
    assert_intervals_visible(fig)


def test_selector_axes_and_titles_use_recorded_values(tmp_path, monkeypatch):
    _, reports, _, _ = source_fixture(tmp_path, monkeypatch, 3)
    saved = []
    monkeypatch.setattr(camera, 'save', lambda fig, index: saved.append(fig))
    camera.make_figure3(reports['DeepSeek/OFF'], reports['DeepSeek/ON'], {'S1': 9, 'S2': 11, 'S3': 13})
    fig, = saved
    assert '(9)' in fig.axes[0].get_title(loc='left')
    assert all(ax.get_xlim()[1] > .9 for ax in fig.axes)
    assert_intervals_visible(fig)


def test_policy_axes_cover_new_means_and_intervals(monkeypatch):
    rows = {}
    for rule in ('S1', 'S2', 'S3'):
        row = {key: statistic([value]) for key, value in zip(('R', 'G', 'U', 'B'), [-1., -.5, .5, 1.])}
        row.update({key: statistic([value]) for key, value in zip(('gate', 'opportunity', 'ranking', 'total'), [.5, 1., .5, 2.])})
        rows['pooled/' + rule + '/default'] = row
    saved = []
    monkeypatch.setattr(camera, 'save', lambda fig, index: saved.append(fig))
    camera.make_figure5({'summaries': rows})
    fig, = saved
    assert fig.axes[0].get_ylim()[0] < -1 and fig.axes[0].get_ylim()[1] > 1
    assert fig.axes[1].get_xlim()[1] > 2
    assert_intervals_visible(fig)


@pytest.mark.parametrize('values', [[], [np.nan], [np.inf]])
def test_nonfinite_or_empty_data_is_rejected_instead_of_dropped(values):
    with pytest.raises(ValueError):
        data_limits(values)


def test_zero_width_intervals_and_means_outside_intervals_are_preserved():
    fig, ax = plt.subplots()
    draw_intervals(ax, [0, 1], [2., 4.], [2., 5.])
    segments = ax.collections[0].get_segments()
    assert np.array_equal(segments[0], [[2., 0.], [2., 0.]])
    assert np.array_equal(segments[1], [[4., 1.], [5., 1.]])
    assert interval_values([{'mean': 6., 'ci95': [4., 5.]}]).tolist() == [6., 4., 5.]
    low, high = data_limits([0., 0.], include_zero=True)
    assert low < 0 < high
