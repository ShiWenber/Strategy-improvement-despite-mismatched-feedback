"""Guard the matching mainline and restored exploratory Score archive."""
from collections import Counter
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RUNS = ['feedback_specificity_v2', 'feedback_specificity_thinking_384k_20260923',
        'qwen3_8/off', 'qwen3_8/on']


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


@pytest.mark.parametrize('relative', RUNS)
def test_archive_contains_complete_matching_and_score_pools(relative):
    root = ROOT / 'results' / relative
    manifest = read(root / 'manifest.json')
    assert manifest['arms'] == ['accurate', 'mismatched', 'score']
    jobs = manifest['jobs']
    assert len(jobs) == 360
    assert Counter(j['arm'] for j in jobs) == {'accurate': 120, 'mismatched': 120, 'score': 120}
    assert len({j['context'] for j in jobs}) == 60
    assert all(n == 2 for n in Counter((j['context'], j['arm']) for j in jobs).values())
    identities = {j['id'] for j in jobs}
    contexts = {j['context'] for j in jobs}
    for folder in ['candidates', 'requests_candidates']:
        assert {p.stem for p in (root / folder).glob('*.json')} == identities
    for folder in ['holdout', 'selection_scores']:
        assert {p.stem for p in (root / folder).glob('*.json')} == identities | contexts
    selections = read(root / 'SELECTIONS_SEALED.json')['rows']
    assert len(selections) == 540
    assert {r['arm'] for r in selections} == set(manifest['arms'])
    for job in jobs:
        context = read(root / 'contexts' / (job['context'] + '.json'))
        request = read(root / 'requests_candidates' / (job['id'] + '.json'))
        assert set(context['prompts']) == set(manifest['arms'])
        assert set(context['block_tokens']) == set(manifest['arms'])
        assert request['prompt'] == context['prompts'][job['arm']]
        # Keep original identifiers/positions, even when their positions have gaps.
        assert job['id'].endswith('pos' + str(job['position']))


@pytest.mark.parametrize('relative', RUNS)
def test_score_raw_population_contrasts_match_original_records(relative):
    root = ROOT / 'results' / relative
    manifest = read(root / 'manifest.json')
    name = {'feedback_specificity_v2': 'DeepSeek/OFF',
            'feedback_specificity_thinking_384k_20260923': 'DeepSeek/ON',
            'qwen3_8/off': 'Qwen/OFF', 'qwen3_8/on': 'Qwen/ON'}[relative]
    summary = read(ROOT / 'results/model_comparison_20260928/score_baseline_data_reproduct.json')['configurations'][name]
    records = [read(root / 'holdout' / (job['id'] + '.json')) for job in manifest['jobs']]
    for arm in ('accurate', 'mismatched'):
        values = []
        for seed in manifest['seeds']:
            groups = [[r['delta']['default']['score'] for r in records if r['seed'] == seed and r['arm'] == a]
                      for a in (arm, 'score')]
            assert all(len(v) == 6 for v in groups)
            values.append(sum(groups[0]) / 6 - sum(groups[1]) / 6)
        actual = summary['comparisons']['raw'][arm + '_minus_score']
        assert actual['seed_values'] == pytest.approx(values, abs=1e-12, rel=0)
        assert actual['mean'] == pytest.approx(sum(values) / 20, abs=1e-12, rel=0)


@pytest.mark.parametrize('relative', RUNS)
def test_condition_data_logs_are_complete_and_preserve_original_records(relative):
    root = ROOT / 'results' / relative
    jobs = read(root / 'manifest.json')['jobs']
    for arm in ('score', 'accurate', 'mismatched'):
        with (root / 'arm_logs' / (arm + '.jsonl')).open(encoding='utf-8') as stream:
            logged = [json.loads(line) for line in stream]
        expected = {j['id']: j for j in jobs if j['arm'] == arm}
        assert len(logged) == len(expected) == 120
        assert {row['id'] for row in logged} == set(expected)
        for row in logged:
            assert row['job'] == expected[row['id']] and row['arm'] == arm
            assert row['status'] in ('valid', 'invalid')
            for folder, key in [('requests_candidates', 'request'), ('candidates', 'candidate'),
                                ('selection_scores', 'selection_scores'), ('holdout', 'holdout')]:
                relative_path = folder + '/' + row['id'] + '.json'
                assert row[key] == read(root / relative_path)


def test_reasoning_annotations_match_the_retained_on_requests():
    jobs = read(ROOT / 'results/feedback_specificity_thinking_384k_20260923/manifest.json')['jobs']
    identities = {j['id'] for j in jobs if j['arm'] in ('accurate', 'mismatched')}
    for folder in ['judgments', 'summaries']:
        paths = list((ROOT / 'results/mismatch_detection_jev' / folder).glob('*.json'))
        assert {p.stem for p in paths} == identities
        if folder == 'judgments':
            assert {read(p)['arm'] for p in paths} == {'accurate', 'mismatched'}


# Compare scientific results only; output paths are provenance.
ANALYSIS_CHECKS = [
    ('results/feedback_specificity_v2/ANALYSIS.json', [('raw',), ('selected',), ('primary',)]),
    ('results/feedback_specificity_v2/role_analysis/ANALYSIS.json', [('summaries',)]),
    *[('results/feedback_specificity_thinking_384k_20260923/ANALYSIS.json', [(key,)])
      for key in ('thinking', 'historical', 'focus_holm_two', 'configuration_differences_exploratory', 'audit')],
    *[(f'results/qwen3_8/{mode}/ANALYSIS.json', [('result',)]) for mode in ('off', 'on')],
    *[('results/figure4_opponent_profiles_20260926/ANALYSIS.json', [('configs', mode, 'summaries')])
      for mode in ('non_thinking', 'thinking')],
    *[('results/reciprocity_population_visuals_20260924/behavior/ANALYSIS.json', [('configs', mode, 'summaries')])
      for mode in ('non_thinking', 'thinking')],
    *[(f'docs/direct_reciprocity/mismatch_distance/mismatch_distance_thinking_{mode}.json', [(key,)])
      for mode in ('off', 'on')
      for key in ('rows', 'distance_summary', 'distance_diagnostics', 'weak_mismatch_sensitivity')],
    ('results/model_comparison_20260928/cross_model_mainline_data.json', [('statistics',)]),
]


def assert_same_results(expected, actual):
    """Recursively compare independently stored reference values, including keys."""
    if isinstance(expected, dict):
        assert isinstance(actual, dict) and expected.keys() == actual.keys()
        return sum(assert_same_results(value, actual[key]) for key, value in expected.items())
    if isinstance(expected, list):
        assert isinstance(actual, list) and len(expected) == len(actual)
        return sum(assert_same_results(a, b) for a, b in zip(expected, actual))
    if isinstance(expected, (int, float)) and not isinstance(expected, bool):
        assert isinstance(actual, (int, float)) and not isinstance(actual, bool)
        assert actual == pytest.approx(expected, abs=1e-12, rel=0)
        return 1
    assert actual == expected
    return 0


@pytest.mark.parametrize('relative,branches', ANALYSIS_CHECKS)
def test_recomputed_analyses_match_paper_statistics(relative, branches, record_property):
    path = ROOT / relative
    original, recomputed = read(path), read(path.with_name(path.stem + '_reproduct' + path.suffix))
    numbers = 0
    for branch in branches:
        before, after = original, recomputed
        for key in branch:
            before, after = before[key], after[key]
        numbers += assert_same_results(before, after)
    record_property('numeric_values_compared', numbers)


def test_paper_inputs_manifest_points_to_existing_files(record_property):
    records = read(ROOT / 'results/reproduction/INPUT_MANIFEST.json')['records']
    for row in records:
        assert (ROOT / row['path']).is_file(), row['path']
    record_property('inputs_verified', len(records))


@pytest.mark.parametrize('name,rows', [
    ('candidate_gains', 2880),
    ('population_gains', 640),
    ('condition_statistics', 32),
])
def test_recomputed_csv_preserves_full_precision_matching_reference(name, rows):
    import csv
    path = ROOT / 'results/model_comparison_20260928' / (name + '_reproduct.csv')
    with path.open(encoding='utf-8', newline='') as handle:
        reader = csv.DictReader(handle)
        values = list(reader)
    matching = [r for r in values if r['arm'] in ('accurate', 'mismatched')]
    assert len(matching) == rows
    assert len(values) == rows * 3 // 2
    assert {r['arm'] for r in values} == {'accurate', 'mismatched', 'score'}


def test_cached_label_report_matches_paper_counts():
    report = read(ROOT / 'results/mismatch_detection_jev/jev_recount_reproduct.json')
    assert report['threshold'] == .4 and report['confidence_gate'] == .6
    assert report['files_judged'] == 240
    assert all(report['by_arm'][arm]['files'] == 120 for arm in ('accurate', 'mismatched'))
    assert report['by_arm']['accurate']['confident'] == 0
    mismatch = report['by_arm']['mismatched']
    assert mismatch['confident'] == 31
    assert mismatch['kept_using_among_confident'] == pytest.approx(30 / 31)


def test_sampled_replay_matches_recorded_games():
    report = read(ROOT / 'results/reproduction/replay_reproduct.json')
    assert report['games_replayed'] == 2640 and len(report['records']) == 12
    assert report['max_abs_error'] <= 1e-12 and report['live_api_calls'] == 0
    assert all(r['status'] in ('ok', 'invalid_candidate_no_game_replay') for r in report['records'])


def test_missing_parameterized_input_does_not_fall_back_to_paper_data(tmp_path):
    import subprocess
    import sys
    output = tmp_path / 'summary.json'
    result = subprocess.run([sys.executable, str(ROOT / 'experiments/direct_reciprocity/cross_model_summary.py'),
                             '--work', str(ROOT), '--analysis-suffix', '_missing', '--output', str(output)],
                            capture_output=True, text=True, cwd=ROOT)
    assert result.returncode != 0 and 'ANALYSIS_missing.json' in result.stderr
    assert not output.exists()
