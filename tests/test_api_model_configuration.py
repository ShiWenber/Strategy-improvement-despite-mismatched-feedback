"""Selected .env models reach new API work; frozen offline inputs retain identity."""
from argparse import Namespace
import json
import os
from pathlib import Path

import openai
import pytest

from experiments.config import load_env
from experiments.direct_reciprocity import paired_control, specificity
from experiments.direct_reciprocity.records import read_json, write_json
from tools import run_fresh_reproduction as fresh


@pytest.fixture(autouse=True)
def isolated_models_and_no_api(monkeypatch):
    for name in ('DEEPSEEK_MODEL', 'QWEN_MODEL'):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(openai, 'OpenAI', lambda *args, **kwargs: pytest.fail('Model tests must not call an API'))
    monkeypatch.setattr(fresh.subprocess, 'run',
                        lambda *args, **kwargs: pytest.fail('Model tests must not dispatch a subprocess'))


def env_file(tmp_path, *, deepseek='file-deepseek-fixture', qwen='file-qwen-fixture'):
    path = tmp_path / 'chosen.env'
    path.write_text(f'DEEPSEEK_MODEL={deepseek}\nQWEN_MODEL={qwen}\n', encoding='utf-8')
    return path


def arguments(tmp_path, path, *, steps='api_call'):
    return Namespace(output=tmp_path / 'fresh', env_file=path, steps=steps,
                     api_workers=12, workers=36)


def test_selected_env_file_overrides_process_models_without_mutating_either(tmp_path, monkeypatch):
    path = env_file(tmp_path)
    inherited = {'DEEPSEEK_MODEL': 'process-deepseek-fixture', 'QWEN_MODEL': 'process-qwen-fixture',
                 'UNRELATED_SETTING': 'preserved'}
    for key, value in inherited.items():
        monkeypatch.setenv(key, value)
    before = inherited.copy()
    merged = load_env.api_environment(path, environ=inherited)
    assert merged['DEEPSEEK_MODEL'] == 'file-deepseek-fixture'
    assert merged['QWEN_MODEL'] == 'file-qwen-fixture'
    assert merged['UNRELATED_SETTING'] == 'preserved'
    assert inherited == before and merged is not inherited
    assert os.environ['DEEPSEEK_MODEL'] == before['DEEPSEEK_MODEL']
    assert os.environ['QWEN_MODEL'] == before['QWEN_MODEL']


def test_missing_env_file_can_use_explicit_process_models(tmp_path):
    inherited = {'DEEPSEEK_MODEL': 'process-deepseek-fixture', 'QWEN_MODEL': 'process-qwen-fixture'}
    merged = load_env.api_environment(tmp_path / 'absent.env', environ=inherited)
    assert load_env.require_model('deepseek', environ=merged) == inherited['DEEPSEEK_MODEL']
    assert load_env.require_model('qwen', environ=merged) == inherited['QWEN_MODEL']
    assert merged is not inherited


@pytest.mark.parametrize('declaration', ['QWEN_MODEL', 'QWEN_MODEL=', "QWEN_MODEL='   '"])
def test_empty_file_model_never_falls_back_to_process_value(tmp_path, declaration):
    path = tmp_path / 'chosen.env'
    path.write_text(declaration + '\n', encoding='utf-8')
    merged = load_env.api_environment(path, environ={'QWEN_MODEL': 'process-qwen-fixture'})
    with pytest.raises(ValueError, match='QWEN_MODEL'):
        load_env.require_model('qwen', environ=merged)


@pytest.mark.parametrize('provider', ['deepseek', 'qwen'])
@pytest.mark.parametrize('value', [None, '', ' \t '])
def test_required_models_have_no_missing_or_blank_default(provider, value):
    values = {} if value is None else {provider.upper() + '_MODEL': value}
    with pytest.raises(ValueError, match=provider.upper() + '_MODEL'):
        load_env.require_model(provider, environ=values)


def test_model_values_are_trimmed(tmp_path):
    path = env_file(tmp_path, deepseek="'  file-deepseek-fixture  '", qwen="' file-qwen-fixture '")
    values = load_env.api_environment(path, environ={})
    assert load_env.require_model('deepseek', environ=values) == 'file-deepseek-fixture'
    assert load_env.require_model('qwen', environ=values) == 'file-qwen-fixture'


def test_generic_run_dry_run_uses_selected_env_over_process_model(tmp_path, monkeypatch, capsys):
    from experiments.direct_reciprocity import run as generic_run
    path = env_file(tmp_path)
    output = tmp_path / 'generic-output'
    monkeypatch.setenv('DEEPSEEK_MODEL', 'process-deepseek-fixture')
    monkeypatch.setattr(generic_run, 'get_api_key', lambda provider: '')
    monkeypatch.setattr(generic_run, 'run', lambda *args: pytest.fail('Dry-run must not generate strategies'))
    monkeypatch.setattr('sys.argv', ['run', '--provider', 'deepseek', '--env-file', str(path),
                                   '--output', str(output), '--dry-run'])
    generic_run.main()
    report = json.loads(capsys.readouterr().out)
    assert report['model'] == 'file-deepseek-fixture'
    assert report['provider'] == 'deepseek' and report['configured'] is False
    assert not output.exists()


def test_generic_run_dry_run_explicit_model_overrides_file_and_process(tmp_path, monkeypatch, capsys):
    from experiments.direct_reciprocity import run as generic_run
    path = env_file(tmp_path)
    output = tmp_path / 'generic-output'
    monkeypatch.setenv('QWEN_MODEL', 'process-qwen-fixture')
    monkeypatch.setattr(generic_run, 'get_api_key', lambda provider: '')
    monkeypatch.setattr(generic_run, 'run', lambda *args: pytest.fail('Dry-run must not generate strategies'))
    monkeypatch.setattr('sys.argv', ['run', '--provider', 'qwen', '--env-file', str(path),
                                   '--model', 'explicit-qwen-fixture', '--output', str(output), '--dry-run'])
    generic_run.main()
    report = json.loads(capsys.readouterr().out)
    assert report['model'] == 'explicit-qwen-fixture'
    assert report['provider'] == 'qwen' and report['configured'] is False
    assert not output.exists()


def test_fresh_workflow_records_and_exports_models_from_selected_file(tmp_path, monkeypatch):
    path = env_file(tmp_path)
    monkeypatch.setenv('DEEPSEEK_MODEL', 'process-deepseek-fixture')
    monkeypatch.setenv('QWEN_MODEL', 'process-qwen-fixture')
    workflow = fresh.Workflow(arguments(tmp_path, path))
    expected = {'deepseek': 'file-deepseek-fixture', 'qwen': 'file-qwen-fixture'}
    assert workflow.models == workflow.state['models'] == expected
    assert workflow.env['DEEPSEEK_MODEL'] == expected['deepseek']
    assert workflow.env['QWEN_MODEL'] == expected['qwen']
    assert os.environ['DEEPSEEK_MODEL'] == 'process-deepseek-fixture'
    assert os.environ['QWEN_MODEL'] == 'process-qwen-fixture'
    workflow.document()
    document = (workflow.root / 'README.md').read_text(encoding='utf-8')
    assert all(model in document for model in expected.values())

    def render_fixture(name, command, stage, resume=True):
        output = Path(command[command.index('--output-dir') + 1])
        output.mkdir(parents=True, exist_ok=True)
        for source, _, _ in fresh.FIGURES:
            for extension in ('png', 'pdf', 'svg'):
                (output / f'{source}.{extension}').write_bytes(b'offline figure fixture')

    monkeypatch.setattr(workflow, 'run_command', render_fixture)
    workflow.plots()
    assert read_json(workflow.plot / 'FIGURES_MANIFEST.json')['models'] == expected


@pytest.mark.parametrize('missing', ['deepseek', 'qwen'])
def test_fresh_api_work_fails_before_dispatch_when_model_is_missing(tmp_path, missing):
    path = tmp_path / 'chosen.env'
    other = 'QWEN_MODEL=file-qwen-fixture' if missing == 'deepseek' else 'DEEPSEEK_MODEL=file-deepseek-fixture'
    path.write_text(other + '\n', encoding='utf-8')
    with pytest.raises(ValueError, match=missing.upper() + '_MODEL'):
        fresh.Workflow(arguments(tmp_path, path))
    assert not (tmp_path / 'fresh/RUN_STATUS.json').exists()


@pytest.mark.parametrize('changed_provider', ['deepseek', 'qwen'])
def test_api_resume_rejects_changed_models_without_writing_any_output(tmp_path, changed_provider):
    path = env_file(tmp_path)
    args = arguments(tmp_path, path)
    first = fresh.Workflow(args)
    before_files = {p.relative_to(first.root): p.read_bytes() for p in first.root.rglob('*') if p.is_file()}
    before_directories = {p.relative_to(first.root) for p in first.root.rglob('*') if p.is_dir()}
    models = {'deepseek': 'file-deepseek-fixture', 'qwen': 'file-qwen-fixture'}
    models[changed_provider] = 'different-' + changed_provider + '-fixture'
    env_file(tmp_path, **models)
    with pytest.raises(ValueError, match='model'):
        fresh.Workflow(args)
    after_files = {p.relative_to(first.root): p.read_bytes() for p in first.root.rglob('*') if p.is_file()}
    after_directories = {p.relative_to(first.root) for p in first.root.rglob('*') if p.is_dir()}
    assert after_files == before_files and after_directories == before_directories


def test_api_resume_accepts_unchanged_custom_models(tmp_path):
    path = env_file(tmp_path)
    args = arguments(tmp_path, path)
    first = fresh.Workflow(args)
    resumed = fresh.Workflow(args)
    assert resumed.models == first.models
    assert resumed.state['models'] == first.state['models']


@pytest.mark.parametrize('steps', ['analysis', 'plot'])
@pytest.mark.parametrize('current_values', [('different-ds-fixture', 'different-qwen-fixture'), ('', '')])
def test_offline_resume_uses_recorded_models_even_if_current_file_changes(tmp_path, steps, current_values):
    path = env_file(tmp_path)
    first = fresh.Workflow(arguments(tmp_path, path))
    expected = first.models.copy()
    env_file(tmp_path, deepseek=current_values[0], qwen=current_values[1])
    offline = fresh.Workflow(arguments(tmp_path, path, steps=steps))
    assert offline.models == offline.state['models'] == expected
    assert offline.env['DEEPSEEK_MODEL'] == expected['deepseek']
    assert offline.env['QWEN_MODEL'] == expected['qwen']


def test_freeze_cli_loads_selected_env_before_freezing_and_initialization_uses_frozen_model(tmp_path, monkeypatch):
    path = env_file(tmp_path)
    monkeypatch.setenv('DEEPSEEK_MODEL', 'process-deepseek-fixture')
    output = tmp_path / 'specificity'
    monkeypatch.setattr('sys.argv', ['specificity', 'freeze', '--output', str(output), '--env-file', str(path),
                                   '--seeds', '901', '--ranks', '1'])
    specificity.main()
    manifest = read_json(output / 'manifest.json')
    assert manifest['model'] == 'file-deepseek-fixture'
    monkeypatch.setenv('DEEPSEEK_MODEL', 'changed-after-freeze-fixture')
    dispatched = []

    def generate(self, identity, prompt, cfg):
        dispatched.append((self.provider, self.model, identity))
        return None

    monkeypatch.setattr(specificity.Generator, 'generate', generate)
    job = manifest['init_jobs'][0]
    specificity.initial_job((str(output), job))
    assert dispatched == [('deepseek', manifest['model'], job['id'])]


@pytest.mark.parametrize('provider,mode', [('deepseek', 'on'), ('qwen', 'off'), ('qwen', 'on')])
def test_paired_api_resume_rejects_environment_model_change_without_rewriting_manifest(tmp_path, monkeypatch, provider, mode):
    name = provider.upper() + '_MODEL'
    monkeypatch.setenv(name, 'frozen-' + provider + '-fixture')
    output = tmp_path / 'qwen3_8' / mode if provider == 'qwen' else tmp_path / 'thinking'
    actual_mode, _, api, version = paired_control.settings(provider, output)
    manifest = {'api': api, 'version': version, 'mode': actual_mode}
    write_json(output / 'manifest.json', manifest)
    before = (output / 'manifest.json').read_bytes()
    monkeypatch.setenv(name, 'changed-' + provider + '-fixture')
    with pytest.raises((ValueError, RuntimeError), match='[Cc]hang|[Mm]odel|identity|configuration'):
        paired_control.verify(output, provider)
    assert (output / 'manifest.json').read_bytes() == before
    assert paired_control.verify(output, provider, check_model=False) == manifest


def test_standalone_api_audit_resolves_custom_models_from_manifests_without_writes(tmp_path, monkeypatch):
    models = {'deepseek': 'recorded-deepseek-fixture', 'qwen': 'recorded-qwen-fixture'}
    monkeypatch.setenv('DEEPSEEK_MODEL', 'unrelated-process-model')
    monkeypatch.setenv('QWEN_MODEL', 'unrelated-process-model')
    api = tmp_path / 'api_call'
    # Holdout validation has separate tests; this fixture isolates request model identity.
    monkeypatch.setattr(fresh.Workflow, 'validate_holdouts', lambda *args: {})
    for run in fresh.RUNS:
        directory = api / 'results' / run
        provider = 'qwen' if 'qwen' in run else 'deepseek'
        identity = {'api': {'model': models[provider]}} if provider == 'qwen' or run != fresh.RUNS[0] else {'model': models[provider]}
        write_json(directory / 'manifest.json', {**identity, 'frozen_at': 1, 'jobs': []})
        write_json(directory / 'COMPLETE.json', {})
        write_json(directory / 'SELECTIONS_SEALED.json', {'rows': [{}] * 540})
        request = json.dumps({'status': 'valid', 'model': models[provider], 'returned_model': models[provider],
                              'started_at': 2})
        for folder, count in [('requests_initial', 240 if run == fresh.RUNS[0] else 0), ('requests_candidates', 360)]:
            target = directory / folder
            target.mkdir(parents=True, exist_ok=True)
            for index in range(count):
                (target / f'{index}.json').write_text(request, encoding='utf-8')
    before = {p.relative_to(api): p.read_bytes() for p in api.rglob('*.json')}
    report = fresh.Workflow.audit_api(api)
    assert report['status'] == 'passed' and report['new_responses'] == 1680
    assert [row['model'] for row in report['runs']] == [models['deepseek']] * 2 + [models['qwen']] * 2
    assert {p.relative_to(api): p.read_bytes() for p in api.rglob('*.json')} == before
