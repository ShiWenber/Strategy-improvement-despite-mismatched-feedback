"""Score integrity and paired estimates, using no provider requests."""
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
import shutil
from unittest.mock import patch

import pytest

from experiments.direct_reciprocity import cross_model_summary as summary
from experiments.direct_reciprocity import restore_score as migration
from experiments.direct_reciprocity.core import Policy
from experiments.direct_reciprocity.records import write_json, filehash, check_manifest, digest, read_json
from experiments.direct_reciprocity.restore_score import verify_restoration
from experiments.direct_reciprocity.specificity import freeze, seal_selections
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
    write_json(tmp_path / 'manifest.json', {'archive_projection': {'date': '2026-10-08'}})
    with pytest.raises(RuntimeError, match='Historical archive is read-only'):
        check_manifest(tmp_path)


def test_restoration_receipt_detects_record_and_receipt_tampering(tmp_path):
    record = tmp_path / 'candidates/example.json'
    write_json(record, {'id': 'example'})
    receipt = tmp_path / 'SCORE_RESTORE.json'
    write_json(receipt, {'record_sha256': {'candidates/example.json': filehash(record)}})
    write_json(tmp_path / 'manifest.json', {'archive_projection': {'restore_receipt_sha256': filehash(receipt)}})
    verify_restoration(tmp_path)
    write_json(record, {'id': 'other'})
    with pytest.raises(RuntimeError, match='record changed'):
        verify_restoration(tmp_path)
    write_json(receipt, {'record_sha256': {}})
    with pytest.raises(RuntimeError, match='receipt changed'):
        verify_restoration(tmp_path)


def test_score_estimates_are_population_paired_and_fail_closed_for_missing_arms():
    # The difference of paired values is [2, -1], with mean .5.
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


@pytest.fixture
def historical_projection(tmp_path, monkeypatch):
    """Small source archive with original position gaps; no games or API calls."""
    run = 'feedback_specificity_v2'
    monkeypatch.setattr(migration, 'RUNS', (run,))
    source, work = tmp_path / 'source', tmp_path / 'work'
    original, current = source / 'results' / run, work / 'results' / run
    cid = 's901-rank1'
    parent = Policy('parent', 'def strategy(history, opponent_history):\n    return "C"\n')
    context = {'id': cid, 'seed': 901, 'rank': 1, 'slot': 0, 'parent': asdict(parent),
               'block_tokens': {'accurate': 1, 'mismatched': 1, 'score': 0},
               'prompts': {a: 'training scores and code: ' + a for a in SCORE_ARMS}}
    write_json(original / 'contexts' / (cid + '.json'), context)
    write_json(original / 'populations/s901.json', {'seed': 901})
    settings = ('default', 'noise01', 'long')
    metrics = ('score', 'cooperation', 'worst_score')
    measured = {s: {m: 1. for m in metrics} for s in settings}
    write_json(original / 'holdout' / (cid + '.json'), {'measured': measured})
    write_json(original / 'selection_scores' / (cid + '.json'),
               {'metrics': {s: {'status': 'ok', 'score': 1.} for s in ('S1', 'S2', 'S3')}})
    jobs = []
    for arm, position in zip(SCORE_ARMS, (0, 1, 4)):
        for draw in range(2):
            identity = f'{cid}-d{draw}-pos{position}'
            job = {'id': identity, 'context': cid, 'arm': arm, 'seed': 901,
                   'rank': 1, 'draw': draw, 'position': position}
            jobs.append(job)
            write_json(original / 'requests_candidates' / (identity + '.json'),
                       {'prompt': context['prompts'][arm], 'status': 'valid', 'code_hash': parent.key})
            write_json(original / 'candidates' / (identity + '.json'),
                       dict(job, child=asdict(parent), parent_key=parent.key, valid=True))
            write_json(original / 'selection_scores' / (identity + '.json'),
                       {'metrics': {s: {'status': 'ok', 'score': 2. + draw} for s in ('S1', 'S2', 'S3')}})
            write_json(original / 'holdout' / (identity + '.json'),
                       {'deployed': {s: {m: 2. for m in metrics} for s in settings},
                        'delta': {s: {m: 1. for m in metrics} for s in settings},
                        'fallback': {s: False for s in settings}})
    manifest = {'seeds': [901], 'ranks': [1], 'draws': 2, 'config': {},
                'arms': list(SCORE_ARMS), 'jobs': jobs, 'init_jobs': [],
                'retained_calls': {}, 'implementation_hash': 'historical-fixture',
                'arm_position_permutations': {'901': list(SCORE_ARMS)}}
    write_json(original / 'manifest.json', manifest)
    write_json(original / 'SELECTIONS_SEALED.json', seal_selections(original, manifest, readonly=True))
    write_json(original / 'H_RELEASED.json', {'selection_digest': digest((original / 'SELECTIONS_SEALED.json').read_text())})
    write_json(original / 'COMPLETE.json', {'candidates': 6, 'contexts': 1})
    shutil.copytree(original, current)
    for job in jobs:
        if job['arm'] == 'score':
            for folder in migration.FOLDERS:
                (current / folder / (job['id'] + '.json')).unlink()
    two = dict(manifest, arms=['accurate', 'mismatched'], jobs=[j for j in jobs if j['arm'] != 'score'],
               archive_projection={'source_manifest_sha256': filehash(original / 'manifest.json')})
    write_json(current / 'manifest.json', two)
    context['prompts'].pop('score')
    context['block_tokens'].pop('score')
    write_json(current / 'contexts' / (cid + '.json'), context)
    (current / 'SELECTIONS_SEALED.json').unlink()
    write_json(current / 'SELECTIONS_SEALED.json', seal_selections(current, two, readonly=True))
    write_json(current / 'H_RELEASED.json', {'selection_digest': digest((current / 'SELECTIONS_SEALED.json').read_text())})
    write_json(current / 'COMPLETE.json', {'candidates': 4, 'contexts': 1})
    return source, work, original, current


def snapshot(directory):
    return {p.relative_to(directory).as_posix(): p.read_bytes() for p in directory.rglob('*') if p.is_file()}


def test_restore_validates_without_writes_then_installs_and_is_idempotent(historical_projection):
    source, work, original, current = historical_projection
    source_before, before = snapshot(source), snapshot(current)
    assert migration.restore(source, work)['status'] == 'validated'
    assert snapshot(current) == before
    result = migration.restore(source, work, apply=True)
    assert result['status'] == 'restored'
    assert result['runs']['feedback_specificity_v2']['score_candidates'] == 2
    assert len(read_json(current / 'SELECTIONS_SEALED.json')['rows']) == 9
    verify_restoration(current)
    after = snapshot(current)
    assert migration.restore(source, work, apply=True)['status'] == 'already_restored'
    assert snapshot(current) == after
    assert snapshot(source) == source_before
    for job in read_json(original / 'manifest.json')['jobs']:
        for folder in migration.FOLDERS:
            assert filehash(current / folder / (job['id'] + '.json')) == filehash(original / folder / (job['id'] + '.json'))


@pytest.mark.parametrize('problem', ['missing_score', 'matching_conflict'])
def test_restore_rejects_incomplete_or_conflicting_records_before_any_install(historical_projection, problem):
    source, work, original, current = historical_projection
    if problem == 'missing_score':
        (original / 'holdout/s901-rank1-d0-pos4.json').unlink()
    else:
        write_json(current / 'requests_candidates/s901-rank1-d0-pos0.json', {'conflict': True})
    before = snapshot(current)
    with pytest.raises((RuntimeError, FileNotFoundError)):
        migration.restore(source, work, apply=True)
    assert snapshot(current) == before


def test_restore_rolls_back_failed_installation(historical_projection, monkeypatch):
    source, work, original, current = historical_projection
    before = snapshot(current)
    copy = migration.copy_record
    failed = False

    def injected_failure(source_path, target):
        nonlocal failed
        if not failed and target == current / 'candidates/s901-rank1-d0-pos4.json':
            failed = True
            raise OSError('simulated disk failure')
        return copy(source_path, target)

    monkeypatch.setattr(migration, 'copy_record', injected_failure)
    with pytest.raises(OSError, match='simulated disk failure'):
        migration.restore(source, work, apply=True)
    assert failed and snapshot(current) == before
