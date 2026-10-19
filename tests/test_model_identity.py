"""Model overrides must not relabel archived data or leak into offline audits."""
from pathlib import Path

import pytest

from experiments.direct_reciprocity import condition_generation as generation
from experiments.direct_reciprocity import paired_control, qwen_analysis, thinking_control_analysis
from experiments.direct_reciprocity.figures import plot_results_three_figures as plots
from experiments.direct_reciprocity.records import write_json


@pytest.mark.parametrize('provider,default,override', [
    ('qwen', 'qwen3.8-flash', 'qwen3.7-flash'),
    ('deepseek', 'deepseek-flash', 'deepseek-other'),
])
def test_model_resolution_preserves_defaults_and_accepts_frozen_identity(monkeypatch, provider, default, override):
    env_name = provider.upper() + '_MODEL'
    monkeypatch.delenv(env_name, raising=False)
    assert generation.specification('prompt', provider, 'off')['model'] == default
    monkeypatch.setenv(env_name, override)
    assert generation.specification('prompt', provider, 'off')['model'] == override
    assert generation.specification('prompt', provider, 'on', model=default)['model'] == default


def test_paired_manifest_version_tracks_requested_qwen_model(monkeypatch):
    monkeypatch.setenv('QWEN_MODEL', 'qwen3.7-flash')
    mode, _, api, version = paired_control.settings('qwen', Path('reproduction/qwen3_8/off'))
    assert (mode, api['model'], version) == ('off', 'qwen3.7-flash', 'qwen3.7-flash-v2')
    monkeypatch.delenv('QWEN_MODEL')
    assert paired_control.settings('qwen', Path('results/qwen3_8/on'))[-1] == 'qwen3.8-flash-v2'
    assert paired_control.settings('deepseek', Path('reproduction/thinking'))[-1] == 'thinking-384k-v2'


def write_audit_fixture(root, provider, mode, model):
    job = {'id': 'child', 'context': 'parent', 'arm': 'score'}
    manifest = {'jobs': [job], 'draws': 1, 'frozen_at': 1, 'mode': mode, 'api': {'model': model}}
    request = generation.specification('frozen prompt', provider, mode, model=model)
    request.update(status='valid', started_at=2, returned_model=model, finish_reason='stop',
                   reasoning_content='reasoning' if mode == 'on' else '', usage={'prompt_tokens': 10,
                       'completion_tokens': 20, 'total_tokens': 30})
    metrics = {setting: {metric: 0 for metric in ('score', 'cooperation', 'worst_score')}
               for setting in ('default', 'noise01', 'long')}
    write_json(root / 'COMPLETE.json', {})
    write_json(root / 'SELECTIONS_SEALED.json', {'rows': [{}, {}, {}]})
    write_json(root / 'contexts/parent.json', {'prompts': {'score': 'frozen prompt'}})
    write_json(root / 'requests_candidates/child.json', request)
    write_json(root / 'candidates/child.json', {'valid': True, 'child': None})
    write_json(root / 'holdout/parent.json', {'measured': metrics})
    write_json(root / 'holdout/child.json', {'deployed': metrics, 'delta': metrics,
                                          'fallback': {setting: False for setting in metrics}})
    return manifest


@pytest.mark.parametrize('provider,mode,model', [('qwen', 'off', 'qwen3.7-flash'),
                                               ('deepseek', 'on', 'deepseek-flash')])
def test_offline_audits_use_manifest_model_despite_environment(tmp_path, monkeypatch, provider, mode, model):
    manifest = write_audit_fixture(tmp_path, provider, mode, model)
    monkeypatch.setenv(provider.upper() + '_MODEL', 'unrelated-model')
    if provider == 'qwen':
        report = qwen_analysis.audit(tmp_path, manifest)
        assert report['reported_cost_cny_uncached_beijing'] is None
    else:
        monkeypatch.setattr(thinking_control_analysis, 'seal_selections', lambda *args, **kwargs: {'rows': [{}, {}, {}]})
        report = thinking_control_analysis.audit(tmp_path, manifest)
    assert report['issues'] == []
    assert report['requests'] == 1


def test_qwen_summary_records_manifest_model_and_rejects_mixed_pair(tmp_path, monkeypatch):
    for mode in ('off', 'on'):
        write_json(tmp_path / mode / 'manifest.json', {'api': {'model': 'qwen3.7-flash'}})
    monkeypatch.setattr(qwen_analysis, 'audit', lambda *args: {'issues': []})
    report = {'raw': {arm: {'metrics': {'default/score': {'seed_values': values}}}
                      for arm, values in [('accurate', [.1, .2]), ('mismatched', [.0, .0])]}}
    monkeypatch.setattr(qwen_analysis, 'aggregate', lambda *args: report)
    assert qwen_analysis.analyze(tmp_path)['model'] == 'qwen3.7-flash'
    write_json(tmp_path / 'on/manifest.json', {'api': {'model': 'qwen3.8-flash'}})
    with pytest.raises(ValueError, match='same model'):
        qwen_analysis.analyze(tmp_path)


def test_plot_labels_use_recorded_models_before_environment(monkeypatch):
    monkeypatch.setenv('QWEN_MODEL', 'environment-qwen')
    monkeypatch.setenv('DEEPSEEK_MODEL', 'environment-deepseek')
    manifests = {'deepseek_off': {'model': 'deepseek-flash'},
                 'deepseek_on': {'api': {'model': 'deepseek-flash'}},
                 'qwen_off': {'api': {'model': 'qwen3.7-flash'}},
                 'qwen_on': {'api': {'model': 'qwen3.7-flash'}}}
    assert plots.display_models(manifests) == {'DeepSeek': 'deepseek-flash', 'Qwen': 'qwen3.7-flash'}
    manifests['qwen_on']['api']['model'] = 'qwen3.8-flash'
    with pytest.raises(ValueError, match='same model'):
        plots.display_models(manifests)
    missing = {cell: {} for cell in manifests}
    assert plots.display_models(missing) == {'DeepSeek': 'environment-deepseek', 'Qwen': 'environment-qwen'}
    monkeypatch.delenv('QWEN_MODEL')
    monkeypatch.delenv('DEEPSEEK_MODEL')
    assert plots.display_models(missing) == plots.DEFAULT_DISPLAY_MODELS
