"""A missing long-match baseline must not erase observed primary outcomes."""
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

import pytest

from experiments.direct_reciprocity import specificity
from experiments.direct_reciprocity import specificity_analysis as analysis
from experiments.direct_reciprocity import role_analysis
from experiments.direct_reciprocity.core import Policy
from experiments.direct_reciprocity.holdout_metrics import audit_deltas
from experiments.direct_reciprocity.records import read_json, write_json
from experiments.direct_reciprocity.thinking_control_analysis import aggregate, paired_metric_contrast


POLICY = Policy('parent', "def strategy(history, rng):\n    return 'C'\n")


def measurement(score=1.):
    cell = dict(status='ok', score=score, cooperation=.5, worst_score=score,
                families={family: score for family in ('recovery', 'exploitation', 'random', 'memory')})
    means = {key: .2 for key in ('not_recovered', 'recovery_time_capped', 'mutual_cooperation_last5',
                                'own_cooperation_last5', 'unilateral_cooperation_last5', 'score')}
    probes = {f'{mode}_{probe}': {'mean': deepcopy(means)}
              for mode in ('controlled', 'natural')
              for probe in ('two_D_TFT', 'five_D_GTFT', 'three_D_ALLC', 'sustained_D')}
    return {**{s: deepcopy(cell) for s in ('default', 'noise01', 'long')},
            'behavior': {'status': 'ok', 'probes': probes}}


def test_recover_skipped_child_archives_original_and_keeps_other_settings(tmp_path):
    root = tmp_path
    cid = 's1-rank1'
    write_json(root / 'H_RELEASED.json', {})
    write_json(root / 'contexts' / f'{cid}.json', {'seed': 1, 'parent': asdict(POLICY)})
    write_json(root / 'candidates/c1.json', {'id': 'c1', 'context': cid, 'child': asdict(POLICY)})
    parent = measurement()
    parent['long'] = {'status': 'failed', 'error_type': 'PolicyError'}
    write_json(root / 'holdout' / f'{cid}.json', {'id': cid, 'status': 'runtime_failure', 'measured': parent})
    original = {'id': 'c1', 'status': 'skipped', 'skip_reason': 'parent_holdout_failed'}
    write_json(root / 'holdout/c1.json', original)
    original_bytes = (root / 'holdout/c1.json').read_bytes()
    with patch.object(specificity, 'holdout_measure', return_value=measurement(4.)) as run:
        result = specificity.holdout_job((str(root), 'child', 'c1'))
    assert run.call_count == 1
    assert result['status'] == 'complete'
    row = read_json(root / 'holdout/c1.json')
    assert row['delta']['default']['score'] == pytest.approx(3.)
    assert row['delta']['noise01']['score'] == pytest.approx(3.)
    assert row['deployed']['behavior']['status'] == 'ok'
    assert row['delta']['long'] == dict.fromkeys(('score', 'cooperation', 'worst_score'))
    assert row['deployed']['long'] is None and row['fallback']['long'] is None
    assert row['missing_reasons']['long']['error_type'] == 'PolicyError'
    history = list((root / 'evaluation_history').glob('*/holdout/c1.json'))
    assert len(history) == 1 and history[0].read_bytes() == original_bytes
    assert audit_deltas(row, {'measured': parent}, 'c1') == []
    with patch.object(specificity, 'holdout_measure', side_effect=AssertionError('must use cached evaluation')):
        assert specificity.holdout_job((str(root), 'child', 'c1'))['cached']


def fixture_records(root):
    manifest = {'seeds': [1, 2], 'arms': ['accurate', 'mismatched'], 'draws': 2, 'jobs': []}
    seals = []
    for seed in manifest['seeds']:
        cid = f's{seed}-rank1'
        write_json(root / 'contexts' / f'{cid}.json', {'slot': 0})
        diagnostic = {probe: {'mean': {'mutual_cooperation_last5': .1 * seed,
                                       'unilateral_cooperation_last5': .1 * seed}}
                      for probe in ('one_D_TFT', 'four_D_TFT', 'four_D_ALLC', 'sustained_D')}
        write_json(root / 'populations' / f's{seed}.json', {'diagnostics': [diagnostic]})
        measured = measurement()
        if seed == 1:
            measured['long'] = {'status': 'failed', 'error_type': 'PolicyError'}
        write_json(root / 'holdout' / f'{cid}.json', {'id': cid, 'measured': measured,
                   'status': 'runtime_failure' if seed == 1 else 'complete'})
        write_json(root / 'selection_scores' / f'{cid}.json',
                   {'metrics': {rule: {'status': 'ok', 'score': 1.} for rule in ('S1', 'S2', 'S3')}})
        for arm in manifest['arms']:
            for draw in (0, 1):
                identity = f'{cid}-{arm}-{draw}'
                job = dict(id=identity, context=cid, seed=seed, arm=arm, draw=draw)
                manifest['jobs'].append(job)
                gain = float(seed + draw)
                deployed = measurement(1. + gain)
                deltas = {setting: {'score': gain, 'cooperation': 0., 'worst_score': gain}
                          for setting in ('default', 'noise01', 'long')}
                fallback = dict.fromkeys(('default', 'noise01', 'long', 'behavior'), False)
                row = {**job, 'status': 'complete', 'valid': True, 'child': asdict(POLICY),
                       'parent_key': POLICY.key, 'deployed': deployed, 'delta': deltas, 'fallback': fallback}
                if seed == 1:
                    row['deployed']['long'] = None
                    row['delta']['long'] = dict.fromkeys(('score', 'cooperation', 'worst_score'))
                    row['fallback']['long'] = None
                    row['missing_reasons'] = {'long': {'reason': 'parent_measurement_failed', 'error_type': 'PolicyError'}}
                write_json(root / 'holdout' / f'{identity}.json', row)
                write_json(root / 'selection_scores' / f'{identity}.json',
                           {'metrics': {rule: {'status': 'ok', 'score': 2. + draw} for rule in ('S1', 'S2', 'S3')}})
            for rule in ('S1', 'S2', 'S3'):
                seals.append(dict(context=cid, seed=seed, arm=arm, rule=rule,
                                  winner=f'{cid}-{arm}-1', accepted=True))
    write_json(root / 'manifest.json', manifest)
    write_json(root / 'COMPLETE.json', {})
    write_json(root / 'SELECTIONS_SEALED.json', {'rows': seals})
    return manifest


def test_long_uses_evaluable_matched_contexts_without_imputing_missing_populations(tmp_path):
    manifest = fixture_records(tmp_path)
    with patch.object(analysis, 'audit', return_value={'issues': []}):
        report = analysis.analyze(tmp_path, '_reproduct')
    assert aggregate(tmp_path, manifest)['raw']['accurate']['metrics']['long/score'] == report['raw']['accurate']['metrics']['long/score']
    for arm in manifest['arms']:
        default = report['raw'][arm]['metrics']['default/score']
        long = report['raw'][arm]['metrics']['long/score']
        behavior = report['raw'][arm]['behavior']['controlled/recovery_time_capped']
        assert (default['n_contexts'], default['n_observations'], default['seed_ids']) == (2, 4, [1, 2])
        assert behavior['n_contexts'] == 2
        assert (long['n_contexts'], long['n_observations'], long['seed_ids']) == (1, 2, [2])
        assert long['seed_values'] == [2.5] and long['mean'] == 2.5
        assert long['missing_contexts'] == ['s1-rank1']
        assert report['selected']['S3/' + arm]['metrics']['long']['seed_values'] == [3.]
    destination = role_analysis.run(tmp_path, 'ANALYSIS_reproduct.json', '_reproduct')
    policy = read_json(destination / 'ANALYSIS_reproduct.json')
    assert policy['counts']['accurate']['candidates'] == 4
    long_policy = policy['summaries']['accurate/S3/long']
    assert long_policy['R']['seed_ids'] == [2] and long_policy['R']['seed_values'] == [2.5]
    assert long_policy['n_unavailable_pools'] == 1
    assert long_policy['R']['missing_reasons']['s1-rank1']['reason'] == 'parent_measurement_failed'
    assert all(row['R'] is None for row in policy['rows'] if row['setting'] == 'long' and row['seed'] == 1)


def test_complete_batches_keep_the_existing_scientific_output_schema(tmp_path):
    manifest = fixture_records(tmp_path)
    parent = read_json(tmp_path / 'holdout/s1-rank1.json')
    parent['measured'] = measurement()
    parent['status'] = 'complete'
    write_json(tmp_path / 'holdout/s1-rank1.json', parent)
    for job in manifest['jobs']:
        if job['seed'] != 1:
            continue
        path = tmp_path / 'holdout' / (job['id'] + '.json')
        row = read_json(path)
        row['deployed']['long'] = deepcopy(row['deployed']['default'])
        row['delta']['long'] = deepcopy(row['delta']['default'])
        row['fallback']['long'] = False
        row.pop('missing_reasons', None)
        write_json(path, row)
    report = aggregate(tmp_path, manifest)
    assert set(report) == {'raw', 'selected'}
    assert set(report['raw']['accurate']) == {'n', 'valid', 'metrics', 'behavior', 'fallbacks'}
    assert set(report['selected']['S3/accurate']) == {'n', 'accepted', 'metrics'}
    assert set(report['raw']['accurate']['metrics']['long/score']) == {'n_seeds', 'seed_values', 'mean', 'ci95'}
    write_json(tmp_path / 'ANALYSIS_reproduct.json', report)
    output = role_analysis.run(tmp_path, 'ANALYSIS_reproduct.json', '_reproduct')
    policies = read_json(output / 'ANALYSIS_reproduct.json')
    assert set(policies['summaries']['accurate/S3/long']['R']) == {'mean', 'ci95', 'seed_values'}


def test_entirely_unavailable_long_setting_has_null_estimates_and_keeps_primary(tmp_path):
    manifest = fixture_records(tmp_path)
    parent_path = tmp_path / 'holdout/s2-rank1.json'
    parent = read_json(parent_path)
    parent['measured']['long'] = {'status': 'failed', 'error_type': 'PolicyError'}
    parent['status'] = 'runtime_failure'
    write_json(parent_path, parent)
    for job in manifest['jobs']:
        if job['seed'] != 2:
            continue
        path = tmp_path / 'holdout' / (job['id'] + '.json')
        row = read_json(path)
        row['deployed']['long'] = None
        row['delta']['long'] = dict.fromkeys(('score', 'cooperation', 'worst_score'))
        row['fallback']['long'] = None
        row['missing_reasons'] = {'long': {'reason': 'parent_measurement_failed', 'error_type': 'PolicyError'}}
        write_json(path, row)
    report = aggregate(tmp_path, manifest)
    for arm in manifest['arms']:
        assert report['raw'][arm]['metrics']['default/score']['n_observations'] == 4
        long = report['raw'][arm]['metrics']['long/score']
        assert long['mean'] is None and long['ci95'] is None
        assert long['n_seeds'] == long['n_contexts'] == long['n_observations'] == 0
        assert long['estimable'] is False and len(long['missing_contexts']) == 2
        selected = report['selected']['S3/' + arm]['metrics']['long']
        assert selected['mean'] is None and selected['seed_values'] == []
    write_json(tmp_path / 'ANALYSIS_reproduct.json', report)
    output = role_analysis.run(tmp_path, 'ANALYSIS_reproduct.json', '_reproduct')
    policy = read_json(output / 'ANALYSIS_reproduct.json')
    assert policy['summaries']['pooled/S3/long']['R']['mean'] is None


def test_missing_gain_is_not_a_zero_fallback_and_empty_contrast_is_not_estimable():
    parent = {'measured': {'long': {'status': 'failed', 'error_type': 'PolicyError'}}}
    row = {'status': 'complete', 'delta': {'long': {'score': 0.}}, 'deployed': {'long': None},
           'fallback': {'long': None}, 'missing_reasons': {'long': {'reason': 'parent_measurement_failed'}}}
    assert any('must be null: long' in issue for issue in audit_deltas(row, parent, 'c'))
    missing = dict(context_ids=[], seed_ids=[], seed_values=[], n_contexts=0,
                   missing_contexts=['s1-rank1'], missing_reasons={'s1-rank1': {'reason': 'parent_measurement_failed'}})
    difference = paired_metric_contrast(missing, missing, [1])
    assert difference['mean'] is None and difference['ci95'] is None
    assert difference['sign_swap_p'] is None and difference['n_seeds'] == 0
