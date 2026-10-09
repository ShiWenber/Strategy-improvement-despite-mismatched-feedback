"""Score conditions and paired estimates, using no provider requests."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import pytest

from experiments.direct_reciprocity import cross_model_summary as summary
from experiments.direct_reciprocity.records import check_manifest
from experiments.direct_reciprocity.specificity import freeze
from experiments.direct_reciprocity.specificity_assets import ARMS, SCORE_ARMS, experiment_arms, generation_arms


def test_frozen_conditions_reject_silent_resume_with_another_budget(tmp_path):
    freeze(tmp_path, seeds=[901], ranks=[1], arms=ARMS)
    with pytest.raises(ValueError, match='conditions differ'):
        freeze(tmp_path, arms=SCORE_ARMS)
    with pytest.raises(ValueError, match='Require accurate and mismatched'):
        freeze(tmp_path / 'invalid', arms=['score'])


def test_information_conditions_are_frozen_parameters_with_a_three_arm_default(tmp_path):
    manifest = freeze(tmp_path, seeds=[901], ranks=[1])
    assert manifest['arms'] == list(SCORE_ARMS)
    assert manifest['generation_order'] == ['score', 'accurate', 'mismatched']
    assert manifest['requested_calls'] == {'initial': 12, 'candidates': 6, 'total': 18}
    assert freeze(tmp_path, arms=['score', 'accurate', 'mismatched']) == manifest
    assert experiment_arms(['mismatched', 'accurate']) == ARMS
    assert generation_arms(['mismatched', 'score', 'accurate']) == ('score', 'accurate', 'mismatched')
    for invalid in ([], ['score'], ['accurate', 'mismatched', 'score', 'score'],
                    ['accurate', 'mismatched', 'background']):
        with pytest.raises(ValueError, match='Require accurate and mismatched'):
            experiment_arms(invalid)


def test_historical_records_cannot_be_resumed_as_new_generation(tmp_path):
    from experiments.direct_reciprocity.records import write_json
    write_json(tmp_path / 'manifest.json', {'archive_projection': {'date': '2026-10-08'}})
    with pytest.raises(RuntimeError, match='Historical archive is read-only'):
        check_manifest(tmp_path)


def test_score_estimates_are_population_paired_and_fail_closed_for_missing_arms():
    metric = lambda values: {'seed_values': values, 'n_seeds': 2, 'mean': sum(values) / 2, 'ci95': [min(values), max(values)]}
    result = {'raw': {}, 'selected': {}}
    for arm, values in [('score', [10., 20.]), ('accurate', [12., 19.]), ('mismatched', [9., 23.])]:
        result['raw'][arm] = {'metrics': {'default/score': metric(values)}, 'n': 12, 'valid': 11,
                              'fallbacks': {s: 1 for s in ('default', 'noise01', 'long', 'behavior')}}
        result['selected']['S3/' + arm] = {'metrics': {'default': metric(values)}}
    manifest = {'seeds': [205, 200], 'arms': list(SCORE_ARMS), 'jobs': []}

    def fake_read(relative, suffix=''):
        if Path(relative).name == 'manifest.json':
            return manifest
        return dict(result, thinking=deepcopy(result), result=deepcopy(result))

    with patch.object(summary, 'read', fake_read), patch.object(summary, 'filehash', return_value='fixture'):
        report = summary.score_baseline()
        for data in report['configurations'].values():
            contrast = data['comparisons']['raw']['accurate_minus_score']
            assert data['seed_ids'] == [205, 200]
            assert contrast['seed_values'] == [2., -1.]
            assert contrast['mean'] == pytest.approx(.5)
        manifest['arms'] = ['accurate', 'mismatched']
        with pytest.raises(ValueError, match='Score records required'):
            summary.score_baseline()
