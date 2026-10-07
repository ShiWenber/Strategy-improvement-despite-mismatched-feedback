"""Workflow integrity and module boundaries, without model requests."""
import ast
import importlib
import json
from pathlib import Path
import sys
from unittest.mock import patch

import pytest

from experiments.direct_reciprocity import specificity as experiment
from tools.direct_reciprocity import records, specificity, paired_control

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('path', sorted((ROOT / 'tools/direct_reciprocity').glob('*.py')))
def test_moved_modules_import(path):
    assert importlib.import_module('tools.direct_reciprocity.' + path.stem)


def test_experiment_package_contains_no_record_integrity_implementations():
    forbidden = {'freeze', 'check_manifest', 'verify', 'audit', 'source_hash', 'implementation_hash',
                 'filehash', 'digest', 'seal_selections', 'release_parents', 'seed_lock', 'recover'}
    for path in (ROOT / 'experiments/direct_reciprocity').glob('*.py'):
        tree = ast.parse(path.read_text(encoding='utf-8-sig'))
        assert not {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)} & forbidden, path
        assert not any(isinstance(node, ast.Import) and any(a.name == 'hashlib' for a in node.names)
                       for node in ast.walk(tree)), path
    assert not (ROOT / 'experiments/direct_reciprocity/specificity_analysis.py').exists()


def test_frozen_source_identity_covers_experimental_and_tool_implementations(tmp_path, monkeypatch):
    science = tmp_path / 'experiments/direct_reciprocity'
    tools = tmp_path / 'tools/direct_reciprocity'
    science.mkdir(parents=True)
    tools.mkdir(parents=True)
    (science / 'core.py').write_text('x=1\n')
    (tools / 'records.py').write_text('x=2\n')
    monkeypatch.setattr(records, 'ROOT', tmp_path)
    monkeypatch.setattr(records, 'EXPERIMENTS', science)
    monkeypatch.setattr(records, '__file__', str(tools / 'records.py'))
    first = records.implementation_hash()
    (tools / 'records.py').write_text('x=3\n')
    second = records.implementation_hash()
    (science / 'core.py').write_text('x=4\n')
    assert len({first, second, records.implementation_hash()}) == 3


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
def test_paired_cli_reuses_frozen_inputs_and_dispatches_existing_kernels(tmp_path, monkeypatch, provider, mode):
    source = tmp_path / 'off'
    manifest = specificity.freeze(source, seeds=[901], ranks=[1])
    cid = 's901-rank1'
    context = dict(parent={'name': 'parent', 'code': 'def strategy(h, r): return "C"'},
                   prompts={arm: f'{arm} fixture' for arm in manifest['arms']})
    records.write_json(source / 'contexts' / (cid + '.json'), context)
    records.write_json(source / 'populations/s901.json', {'fixture': True})
    records.write_json(source / 'selection_scores' / (cid + '.json'), {'fixture': True})
    records.write_json(source / 'COMPLETE.json', {'fixture': True})
    output = tmp_path / 'qwen3_8' / mode if provider == 'qwen' else tmp_path / 'thinking'
    frozen = paired_control.prepare(output, source, provider)
    assert frozen['new_calls'] == 4 and frozen['reused_initial_calls'] == 12
    assert frozen['prompt_hashes'] == {job['id']: records.digest(context['prompts'][job['arm']])
                                       for job in manifest['jobs']}
    assert paired_control.prepare(output, source, provider) == frozen
    module = paired_control.settings(provider, output)[0]
    args = ['paired_control', 'first', '--provider', provider, '--output', str(output), '--source', str(source)]
    monkeypatch.setattr(sys, 'argv', args)
    with patch.object(module, 'generate_one', return_value={'id': frozen['jobs'][0]['id']}) as generated:
        paired_control.main()
        generated.assert_called_once_with((str(output), frozen['jobs'][0]))
    assert records.read_json(output / 'FIRST_REQUEST_CHECK.json')['completed']
    copied = output / 'contexts' / (cid + '.json')
    copied.write_text('{}')
    with pytest.raises(RuntimeError, match='Reused input changed'):
        paired_control.verify(output, source, provider)
