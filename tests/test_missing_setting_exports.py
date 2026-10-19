"""Exports distinguish undefined paired gains from zero fallback gains."""
import csv
import json
import sys

from experiments.direct_reciprocity import cross_model_summary, export_paper_tables


def metric(value=.1, contexts=60, unavailable=False):
    return {'mean': None if unavailable else value,
            'ci95': None if unavailable else [value - .05, value + .05],
            'n_contexts': contexts, 'n_expected_contexts': 60,
            'missing_contexts': [] if contexts == 60 else ['missing-parent'],
            'estimable': not unavailable}


def test_sensitivity_tables_report_available_contexts_and_unestimable_cells(tmp_path, monkeypatch):
    def save(relative, payload):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding='utf-8')

    save('results/feedback_specificity_v2/manifest.json', {'arms': ['accurate', 'mismatched']})
    save('results/feedback_specificity_v2/ANALYSIS.json', {
        'primary': {'sign_swap_p': .5},
        'raw': {arm: {'metrics': {'noise01/score': metric(),
                                 'long/score': metric(contexts=57) if arm == 'accurate'
                                 else metric(contexts=0, unavailable=True)}}
                for arm in ('accurate', 'mismatched')}})
    save('results/feedback_specificity_v2/role_analysis/ANALYSIS.json', {
        'summaries': {'pooled/S3/' + setting: {'total': metric(contexts=n)}
                      for setting, n in [('noise01', 60), ('long', 57)]}})
    for mode in ('off', 'on'):
        save('docs/direct_reciprocity/mismatch_distance/mismatch_distance_thinking_' + mode + '.json', {
            'weak_mismatch_sensitivity': {'tau_raw_further_two_thirds': dict(metric(), n=40)}})
    output = tmp_path / 'tables'
    monkeypatch.setattr(sys, 'argv', ['tables', '--work', str(tmp_path), '--output', str(output)])
    export_paper_tables.main()
    with (output / 'tableS3_sensitivity.csv').open(newline='', encoding='utf-8') as stream:
        rows = list(csv.DictReader(stream))
    assert rows[0]['200-round parent contexts'] == '57/60'
    assert rows[1]['200 rounds'] == 'Not estimable'
    assert rows[1]['200-round parent contexts'] == '0/60'
    assert (output / 'SAMPLE_AVAILABILITY.json').exists()


def test_candidate_csv_preserves_null_gain_with_an_explicit_reason(tmp_path, monkeypatch):
    statistic = dict(metric(contexts=57), seed_ids=[200], seed_values=[.1], n_seeds=1,
                     n_observations=114)
    stats = {'raw': {'accurate': {'metrics': {'default/score': statistic}}},
             'selected': {'S1/accurate': {'metrics': {'default': statistic}},
                          'S2/accurate': {'metrics': {'default': statistic}},
                          'S3/accurate': {'metrics': {'default': statistic}}}}
    manifest = {'seeds': [200], 'arms': ['accurate'], 'jobs': [
        {'id': 'child', 'seed': 200, 'context': 'parent', 'arm': 'accurate', 'draw': 0}]}
    outcome = {'valid': True, 'fallback': {'default': False, 'noise01': False, 'long': None},
               'delta': {'default': {'score': .1}, 'noise01': {'score': .2}, 'long': {'score': None}},
               'missing_reasons': {'long': {'reason': 'parent_measurement_failed'}}}

    def fake_read(path, suffix=''):
        name = str(path).replace('\\', '/')
        if name.endswith('manifest.json'):
            return manifest
        if name.endswith('SELECTIONS_SEALED.json'):
            return {'rows': [{'context': 'parent', 'arm': 'accurate', 'rule': 'S3', 'winner': 'child'}]}
        if '/holdout/' in name:
            return outcome
        return stats

    monkeypatch.setattr(cross_model_summary, 'RESULT_FILES', {('DeepSeek', 'Off'): 'results/off/ANALYSIS.json'})
    monkeypatch.setattr(cross_model_summary, 'read', fake_read)
    cross_model_summary.export_csv(tmp_path)
    with (tmp_path / 'candidate_gains.csv').open(newline='', encoding='utf-8') as stream:
        rows = list(csv.DictReader(stream))
    assert rows[2]['gain_per_round'] == ''
    assert rows[2]['estimable_gain'] == 'False'
    assert 'parent_measurement_failed' in rows[2]['missing_reason']
    assert rows[0]['gain_per_round'] == '0.1'
