"""Workflow integrity and module boundaries, without model requests."""
import ast
from pathlib import Path
import sys
from unittest.mock import patch

import pytest

from experiments.direct_reciprocity import records, specificity, paired_control
from experiments.direct_reciprocity.specificity_assets import ARMS, SCORE_ARMS

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def configured_models(monkeypatch):
    monkeypatch.setenv('DEEPSEEK_MODEL', 'offline-deepseek')
    monkeypatch.setenv('QWEN_MODEL', 'offline-qwen')


def test_experiments_are_self_contained_with_one_native_entry_point():
    for path in (ROOT / 'experiments').rglob('*.py'):
        tree = ast.parse(path.read_text(encoding='utf-8-sig'))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert not (node.module or '').startswith('tools'), path
            if isinstance(node, ast.Import):
                assert not any(alias.name.startswith('tools') for alias in node.names), path
    assert {p.name for p in (ROOT / 'tools').rglob('*.py')} == {
        '__init__.py', 'render_report.py', 'reproduce.py', 'freeze_paper_snapshot.py',
        'package_reproduction.py', 'run_fresh_reproduction.py', 'reproduction_status.py'}
    assert {p.name for p in (ROOT / 'tools').rglob('*.sh')} >= {'generate_api.sh', 'plot.sh'}
    assert not (ROOT / 'experiments/direct_reciprocity/generate_api.sh').exists()
    assert not (ROOT / 'experiments/direct_reciprocity/plot.sh').exists()
    assert specificity.initial_job.__module__ == specificity.main.__module__


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
    assert records.cached_request(path, dict(spec, prompt='two')) == saved


def test_holdout_release_accepts_the_current_selection_state(tmp_path):
    with pytest.raises(RuntimeError, match='not released'):
        records.require_holdout(tmp_path)
    records.write_json(tmp_path / 'SELECTIONS_SEALED.json', {'rows': []})
    records.release_holdout(tmp_path)
    records.require_holdout(tmp_path)
    records.write_json(tmp_path / 'SELECTIONS_SEALED.json', {'rows': [{'winner': 'changed'}]})
    records.require_holdout(tmp_path)


def test_batch_lock_rejects_a_second_writer_and_releases(tmp_path):
    with records.runner_lock(tmp_path, 'all'):
        with pytest.raises(OSError):
            with records.runner_lock(tmp_path, 'all'):
                pass
    with records.runner_lock(tmp_path, 'all'):
        pass


@pytest.mark.parametrize('difference', [None, 'parent', 'seed'])
def test_paired_holdouts_use_parent_data_instead_of_source_path_identity(tmp_path, difference):
    root, source = tmp_path / 'paired', tmp_path / 'relocated-source'
    cid = 's901-rank1'
    context = {'seed': 901, 'parent': {'name': 'parent', 'code': 'def strategy(h, r): return "C"'}}
    original = dict(context)
    if difference == 'parent':
        original['parent'] = dict(context['parent'], code='def strategy(h, r): return "D"')
    elif difference == 'seed':
        original['seed'] = 902
    records.write_json(root / 'contexts' / (cid + '.json'), context)
    records.write_json(source / 'contexts' / (cid + '.json'), original)
    parent_result = {'id': cid, 'measured': {'default': {'score': 3.}}}
    records.write_json(source / 'holdout' / (cid + '.json'), parent_result)
    manifest = {'jobs': [{'context': cid}]}
    with patch.object(paired_control, 'seal_selections') as selected:
        if difference:
            with pytest.raises(RuntimeError, match='Source parent differs'):
                paired_control.release_parents(root, source, manifest)
            assert not (root / 'H_RELEASED.json').exists()
        else:
            paired_control.release_parents(root, source, manifest)
            assert records.read_json(root / 'holdout' / (cid + '.json')) == parent_result
            records.require_holdout(root)
        selected.assert_called_once_with(root, manifest)


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
    output = tmp_path / 'qwen3_8' / mode if provider == 'qwen' else tmp_path / 'thinking'
    original_settings = paired_control.settings
    def settings_without_protocol(provider, root, **kwargs):
        selected_mode, _, api, version = original_settings(provider, root, **kwargs)
        return selected_mode, tmp_path / 'absent-protocol.md', api, version
    monkeypatch.setattr(paired_control, 'settings', settings_without_protocol)
    frozen = paired_control.prepare(output, source, provider)
    assert not (output / 'PROTOCOL.md').exists()
    assert frozen['new_calls'] == 2 * len(arms) and frozen['reused_initial_calls'] == 12
    first_arm = 'score' if 'score' in arms else 'accurate'
    assert frozen['generation_order'][0] == first_arm
    assert frozen['jobs'][0]['arm'] == first_arm
    assert paired_control.prepare(output, source, provider) == frozen
    env_file = tmp_path / '.env'
    env_file.write_text('DEEPSEEK_MODEL=offline-deepseek\nQWEN_MODEL=offline-qwen\n', encoding='utf-8')
    args = ['paired_control', 'first', '--provider', provider, '--output', str(output), '--source', str(source),
            '--env-file', str(env_file)]
    monkeypatch.setattr(sys, 'argv', args)
    with patch.object(paired_control, 'candidate_job') as generated:
        monkeypatch.setattr(sys, 'argv', args + ['--arm', 'mismatched'])
        with pytest.raises(RuntimeError, match='Complete ' + first_arm):
            paired_control.main()
        generated.assert_not_called()
    monkeypatch.setattr(sys, 'argv', args)
    with patch.object(paired_control, 'candidate_job', return_value={'id': frozen['jobs'][0]['id']}) as generated:
        paired_control.main()
        generated.assert_called_once_with((str(output), frozen['jobs'][0]), provider=provider, mode=mode,
                                          model=frozen['api']['model'])
    assert not (output / 'FIRST_REQUEST_CHECK.json').exists()
    args[1] = 'generate'
    monkeypatch.setattr(sys, 'argv', args)
    with patch.object(paired_control, 'generate_conditions') as generated:
        paired_control.main()
        generated.assert_called_once()
    copied = output / 'contexts' / (cid + '.json')
    copied.write_text('{}')
    assert paired_control.verify(output, provider)['reused_initial_calls'] == 12
    assert paired_control.prepare(output, tmp_path / 'moved-source', provider) == frozen
