"""Delivery audit and conservative local-work accounting; no model calls."""
import argparse
from collections import Counter
from pathlib import Path

from .core import digest
from .run import read_json, write_json
from .specificity import check_manifest


def completion(root):
    root = Path(root)
    manifest = check_manifest(root)
    read_json(root / 'COMPLETE.json')
    analysis = read_json(root / 'ANALYSIS.json')
    supplement = read_json(root / 'SUPPLEMENT.json')
    issues = list(analysis['audit']['issues'])
    contexts = sorted({j['context'] for j in manifest['jobs']})
    candidates = [j['id'] for j in manifest['jobs']]
    initial = [j['id'] for j in manifest['init_jobs']]
    expected = {'initial': initial, 'requests_initial': initial,
                'requests_candidates': candidates, 'candidates': candidates,
                'contexts': contexts, 'selection_scores': contexts + candidates,
                'holdout': contexts + candidates}
    counts = {}
    for directory, identities in expected.items():
        actual = {p.stem for p in (root / directory).glob('*.json')}
        counts[directory] = len(actual)
        if actual != set(identities):
            issues.append(directory + ': identity set mismatch')
    selections = read_json(root / 'SELECTIONS_SEALED.json')
    if len(selections['rows']) != 900:
        issues.append('Expected 900 parent/arm/selector decisions')
    score_rows = [read_json(root / 'selection_scores' / (identity + '.json')) for identity in contexts + candidates]
    holdout_rows = [read_json(root / 'holdout' / (identity + '.json')) for identity in contexts + candidates]
    selection_status = {rule: dict(Counter(r['metrics'][rule]['status'] for r in score_rows))
                        for rule in ('S1', 'S2', 'S3')}
    holdout_status = {setting: dict(Counter(r['measured'].get(setting, {}).get('status', 'invalid') for r in holdout_rows))
                      for setting in ('default', 'noise01', 'long', 'behavior')}
    # Only completed recorded measurements are counted. Partial failed work,
    # validation smoke games, and duplicate scheduling are not guessed.
    training_games = sum(r['metrics'].get('training_game_count', 0) for r in score_rows)
    validation_games = sum(r['metrics']['S3'].get('games', 0) for r in score_rows)
    test_games = {setting: 240 * sum(r['measured'].get(setting, {}).get('status') == 'ok' for r in holdout_rows)
                  for setting in ('default', 'noise01', 'long')}
    behavior_episodes = sum(sum(len(probe['runs']) for probe in r['measured']['behavior']['probes'].values())
                            for r in holdout_rows if r['measured'].get('behavior', {}).get('status') == 'ok')
    population_rows = [read_json(root / 'populations' / f's{seed}.json') for seed in range(200, 220)]
    population_games = sum((len(r['population']) * (len(r['population']) - 1) // 2 +
                            sum(len(item['archive']['opponents']) for item in r['assessment'])) * r['cfg']['repeats']
                           for r in population_rows)
    feedback_episodes = sum(sum(len(probe['runs']) for probe in diagnostic.values())
                            for row in population_rows for diagnostic in row['diagnostics'])
    replay_games = sum(r.get('games_replayed', 0) for r in supplement['deterministic_replay'])
    if any(r['status'] == 'mismatch' for r in supplement['deterministic_replay']):
        issues.append('Replay mismatch')
    if any(r['mismatches'] for r in supplement['parallel_record_audit'].values()):
        issues.append('Parallel publication mismatch')
    figure_provenance = read_json(root / 'figures' / 'PROVENANCE.json')
    if figure_provenance['analysis_hash'] != digest((root / 'ANALYSIS.json').read_text(encoding='utf-8')):
        issues.append('Figures do not use the current analysis')
    for filename in figure_provenance['files']:
        if not Path(filename).is_file():
            issues.append('Missing figure: ' + filename)
    initial_probe_successes = sum(read_json(root / 'initial' / (identity + '.json'))['fallback'] is None for identity in initial)
    result = {'issues': issues, 'implementation_hash': manifest['implementation_hash'],
              'record_counts': counts, 'selection_decisions': len(selections['rows']),
              'selection_statuses': selection_status, 'holdout_statuses': holdout_status,
              'requests': analysis['audit']['n_requests'], 'reported_tokens': analysis['audit']['total_tokens'],
              'local_completed_work': {
                  'population_ranking_games': population_games,
                  'selection_training_games_S1_nested_in_S2': training_games,
                  'selection_validation_games': validation_games,
                  'holdout_games': test_games,
                  'unique_protocol_games_total': population_games + training_games + validation_games + sum(test_games.values()),
                  'initial_validation_feedback_probe_episodes': initial_probe_successes * 50,
                  'population_feedback_probe_episodes': feedback_episodes,
                  'holdout_behavior_probe_episodes': behavior_episodes,
                  'audit_replay_games': replay_games,
                  'note': 'Completed canonical measurements, not total machine work. S1 reuses S2 games. '
                          'Probe episodes are listed separately. Excludes partial failed measurements, '
                          'generation validator smoke games, offline old-data pilot, and parallel duplicate work. '
                          'Duplicate records and mtime indicators are in SUPPLEMENT; no exact total attempt counter was installed.'},
              'gate': analysis['gate'], 'figure_files': figure_provenance['files'],
              'script_hash': digest(Path(__file__).read_text(encoding='utf-8')),
              'note': 'Reporting audit added during evaluation; it does not change frozen inference or selection.'}
    write_json(root / 'COMPLETION_AUDIT.json', result)
    if issues:
        raise RuntimeError('Delivery audit failed: ' + repr(issues))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', nargs='?', default='results/feedback_specificity_v2')
    args = parser.parse_args()
    result = completion(args.root)
    print({'issues': result['issues'], 'local_work': result['local_completed_work'], 'gate': result['gate']})
