"""Workflow integrity and module boundaries, without model requests."""
import ast
from pathlib import Path
import sys
from unittest.mock import patch

import pytest

from experiments.direct_reciprocity import records, specificity, paired_control

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


def test_frozen_source_identity_covers_each_experiment_module_once(tmp_path, monkeypatch):
    science = tmp_path / 'experiments/direct_reciprocity'
    figures = science / 'figures'
    science.mkdir(parents=True)
    figures.mkdir()
    (science / 'core.py').write_text('x=1\n')
    (science / 'records.py').write_text('x=2\n')
    (figures / 'plot.py').write_text('x=3\n')
    monkeypatch.setattr(records, 'ROOT', tmp_path)
    monkeypatch.setattr(records, 'EXPERIMENTS', science)
    first = records.implementation_hash()
    expected = records.digest('\n'.join(p.relative_to(tmp_path).as_posix() + ':' +
                              records.digest(p.read_text()) for p in sorted(science.rglob('*.py'))))
    assert first == expected
    (science / 'records.py').write_text('x=4\n')
    second = records.implementation_hash()
    (science / 'core.py').write_text('x=5\n')
    third = records.implementation_hash()
    (figures / 'plot.py').write_text('x=6\n')
    assert len({first, second, third, records.implementation_hash()}) == 4


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
    args = ['paired_control', 'first', '--provider', provider, '--output', str(output), '--source', str(source)]
    monkeypatch.setattr(sys, 'argv', args)
    with patch.object(paired_control, 'candidate_job', return_value={'id': frozen['jobs'][0]['id']}) as generated:
        paired_control.main()
        generated.assert_called_once_with((str(output), frozen['jobs'][0]), provider=provider, mode=mode)
    assert records.read_json(output / 'FIRST_REQUEST_CHECK.json')['completed']
    copied = output / 'contexts' / (cid + '.json')
    copied.write_text('{}')
    with pytest.raises(RuntimeError, match='Reused input changed'):
        paired_control.verify(output, source, provider)
