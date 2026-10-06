"""Guard the published two-condition archive against stale-arm data leakage."""
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
def test_archive_contains_only_complete_report_matching_pairs(relative):
    root = ROOT / 'results' / relative
    manifest = read(root / 'manifest.json')
    assert manifest['arms'] == ['accurate', 'mismatched']
    jobs = manifest['jobs']
    assert len(jobs) == 240
    assert Counter(j['arm'] for j in jobs) == {'accurate': 120, 'mismatched': 120}
    assert len({j['context'] for j in jobs}) == 60
    assert all(n == 2 for n in Counter((j['context'], j['arm']) for j in jobs).values())
    identities = {j['id'] for j in jobs}
    contexts = {j['context'] for j in jobs}
    for folder in ['candidates', 'requests_candidates']:
        assert {p.stem for p in (root / folder).glob('*.json')} == identities
    for folder in ['holdout', 'selection_scores']:
        assert {p.stem for p in (root / folder).glob('*.json')} == identities | contexts
    selections = read(root / 'SELECTIONS_SEALED.json')['rows']
    assert len(selections) == 360
    assert {r['arm'] for r in selections} == {'accurate', 'mismatched'}
    for job in jobs:
        context = read(root / 'contexts' / (job['context'] + '.json'))
        request = read(root / 'requests_candidates' / (job['id'] + '.json'))
        assert set(context['prompts']) == set(manifest['arms'])
        assert set(context['block_tokens']) == set(manifest['arms'])
        assert request['prompt'] == context['prompts'][job['arm']]
        # Keep original identifiers/positions, even when their positions have gaps.
        assert job['id'].endswith('pos' + str(job['position']))


def test_reasoning_annotations_match_the_retained_on_requests():
    jobs = read(ROOT / 'results/feedback_specificity_thinking_384k_20260923/manifest.json')['jobs']
    identities = {j['id'] for j in jobs}
    for folder in ['judgments', 'summaries']:
        paths = list((ROOT / 'results/mismatch_detection_jev' / folder).glob('*.json'))
        assert {p.stem for p in paths} == identities
        if folder == 'judgments':
            assert {read(p)['arm'] for p in paths} == {'accurate', 'mismatched'}


# Compare scientific results only; output paths and script hashes are provenance.
ANALYSIS_CHECKS = [
    ('results/feedback_specificity_v2/ANALYSIS.json', [('raw',), ('selected',), ('primary',)]),
    ('results/feedback_specificity_v2/role_analysis/ANALYSIS.json', [('summaries',)]),
    *[('results/feedback_specificity_thinking_384k_20260923/ANALYSIS.json', [(key,)])
      for key in ('thinking', 'historical', 'focus_holm_two', 'configuration_differences_exploratory', 'audit')],
    *[(f'results/qwen3_8/{mode}/ANALYSIS.json', [('result',)]) for mode in ('off', 'on')],
    ('results/reciprocity_population_visuals_20260924/population_summary.json', [('configurations',)]),
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


def test_paper_inputs_keep_their_recorded_hashes(record_property):
    from hashlib import sha256
    records = read(ROOT / 'results/reproduction/INPUT_MANIFEST.json')['records']
    for row in records:
        assert sha256((ROOT / row['path']).read_bytes()).hexdigest() == row['sha256'], row['path']
    record_property('input_hashes_verified', len(records))


@pytest.mark.parametrize('name,rows,digest', [
    ('candidate_gains', 2880, '9dc5972a6fcd0c6e37dc26afddd1efc1a7b60cc82d9a184289e62f2dfd8b1082'),
    ('population_gains', 640, '38ae40ec49586a64cb82dbdb16824c3be2964c12e16dd6b5281993b5b8ff7ab2'),
    ('condition_statistics', 32, '168505d95f2aa6504dcb3694523b16bf60d61496333db202b108189983bebac3'),
])
def test_recomputed_csv_matches_full_precision_reference(name, rows, digest):
    import csv
    from hashlib import sha256
    path = ROOT / 'results/model_comparison_20260928' / (name + '_reproduct.csv')
    assert sha256(path.read_bytes()).hexdigest() == digest
    with path.open(encoding='utf-8', newline='') as handle:
        assert sum(1 for _ in csv.DictReader(handle)) == rows


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
    result = subprocess.run([sys.executable, str(ROOT / 'results/model_comparison_20260928/cross_model_summary.py'),
                             '--work', str(ROOT), '--analysis-suffix', '_missing', '--output', str(output)],
                            capture_output=True, text=True, cwd=ROOT)
    assert result.returncode != 0 and 'ANALYSIS_missing.json' in result.stderr
    assert not output.exists()
