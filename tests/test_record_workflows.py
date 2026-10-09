"""Workflow integrity and module boundaries, without model requests."""
import ast
from pathlib import Path
import sys
from unittest.mock import patch

import pytest

from experiments.direct_reciprocity import records, specificity, paired_control
from experiments.direct_reciprocity.specificity_assets import ARMS, SCORE_ARMS

ROOT = Path(__file__).resolve().parents[1]


def test_experiments_are_self_contained_with_one_native_entry_point():
    for path in (ROOT / 'experiments').rglob('*.py'):
        tree = ast.parse(path.read_text(encoding='utf-8-sig'))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert not (node.module or '').startswith('tools'), path
            if isinstance(node, ast.Import):
                assert not any(alias.name.startswith('tools') for alias in node.names), path
    assert {p.name for p in (ROOT / 'tools').rglob('*.py')} == {'__init__.py', 'render_report.py'}
    assert specificity.initial_job.__module__ == specificity.main.__module__
    assert (ROOT / 'experiments/direct_reciprocity/generate_api.sh').is_file()


def test_exclusive_requests_resume_only_matching_finished_responses(tmp_path):
    path = tmp_path / 'requests/one.json'
    spec = dict(provider='offline', model='fixture', prompt='one', temperature=1)
    assert records.cached_request(path, spec) is None
    saved = records.begin_request(path, spec)
    with pytest.raises(FileExistsError):
        records.begin_request(path, spec)
    with pytest.raises(RuntimeError, match='Uncertain'):
        records.cached_request(path, spec)
    saved.update(status='valid', content='def strategy(h, r): return "C"')
    records.write_json(path, saved)
    before = path.read_bytes()
    assert records.cached_request(path, spec) == saved
    assert path.read_bytes() == before
    with pytest.raises(RuntimeError, match='identity collision'):
        records.cached_request(path, dict(spec, prompt='two'))


def test_holdout_release_rejects_changed_selections(tmp_path):
    with pytest.raises(RuntimeError, match='not released'):
        records.require_holdout(tmp_path)
    records.write_json(tmp_path / 'SELECTIONS_SEALED.json', {'rows': []})
    records.release_holdout(tmp_path)
    records.require_holdout(tmp_path)
    records.write_json(tmp_path / 'SELECTIONS_SEALED.json', {'rows': [{'winner': 'changed'}]})
    with pytest.raises(RuntimeError, match='seal does not match'):
        records.require_holdout(tmp_path)


def test_batch_lock_rejects_a_second_writer_and_releases(tmp_path):
    with records.runner_lock(tmp_path, 'all'):
        with pytest.raises(OSError):
            with records.runner_lock(tmp_path, 'all'):
                pass
    with records.runner_lock(tmp_path, 'all'):
        pass


@pytest.mark.parametrize('provider,mode', [('deepseek', 'on'), ('qwen', 'off'), ('qwen', 'on')])
@pytest.mark.parametrize('arms', [ARMS, SCORE_ARMS])
def test_paired_cli_reuses_frozen_inputs_and_dispatches_existing_kernels(tmp_path, monkeypatch, provider, mode, arms):
    source = tmp_path / 'off'
    manifest = specificity.freeze(source, seeds=[901], ranks=[1], arms=arms)
    cid = 's901-rank1'
    context = dict(parent={'name': 'parent', 'code': 'def strategy(h, r): return "C"'},
                   prompts={arm: f'{arm} fixture' for arm in manifest['arms']})
    records.write_json(source / 'contexts' / (cid + '.json'), context)
    records.write_json(source / 'populations/s901.json', {'fixture': True})
    records.write_json(source / 'selection_scores' / (cid + '.json'), {'fixture': True})
    records.write_json(source / 'COMPLETE.json', {'fixture': True})
    output = tmp_path / 'qwen3_8' / mode if provider == 'qwen' else tmp_path / 'thinking'
    frozen = paired_control.prepare(output, source, provider)
    assert frozen['new_calls'] == 2 * len(arms) and frozen['reused_initial_calls'] == 12
    first_arm = 'score' if 'score' in arms else 'accurate'
    assert frozen['generation_order'][0] == first_arm
    assert frozen['jobs'][0]['arm'] == first_arm
    assert frozen['prompt_hashes'] == {job['id']: records.digest(context['prompts'][job['arm']])
                                       for job in manifest['jobs']}
    assert paired_control.prepare(output, source, provider) == frozen
    args = ['paired_control', 'first', '--provider', provider, '--output', str(output), '--source', str(source)]
    monkeypatch.setattr(sys, 'argv', args)
    with patch.object(paired_control, 'candidate_job') as generated:
        monkeypatch.setattr(sys, 'argv', args + ['--arm', 'mismatched'])
        with pytest.raises(RuntimeError, match='Complete ' + first_arm):
            paired_control.main()
        generated.assert_not_called()
    monkeypatch.setattr(sys, 'argv', args)
    with patch.object(paired_control, 'candidate_job', return_value={'id': frozen['jobs'][0]['id']}) as generated:
        paired_control.main()
        generated.assert_called_once_with((str(output), frozen['jobs'][0]), provider=provider, mode=mode)
    assert records.read_json(output / 'FIRST_REQUEST_CHECK.json')['completed']
    copied = output / 'contexts' / (cid + '.json')
    copied.write_text('{}')
    with pytest.raises(RuntimeError, match='Reused input changed'):
        paired_control.verify(output, source, provider)
