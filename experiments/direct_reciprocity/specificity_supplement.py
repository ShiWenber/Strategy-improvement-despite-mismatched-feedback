"""Reporting-only v2 diagnostics; never changes frozen inference or gates.

Written during initialization, before any v2 candidates or holdout outcomes.
Adds planned effective-mismatch sensitivity, execution budget accounting, and
deterministic replay of a pre-outcome-selected record sample.
"""
import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from pathlib import Path
from statistics import mean

from .core import Policy, digest, versus
from .run import read_json, write_json
from .specificity import check_manifest, cfg_for
from .specificity_assets import ARMS, SEEDS, panel
from .specificity_analysis import summarize, sign_swap_p


def budget(records):
    return {'n': len(records), 'statuses': dict(Counter(r['status'] for r in records)),
            'returned_models': dict(Counter(r.get('returned_model', 'missing') for r in records)),
            'unknown_usage': sum(r.get('usage') is None for r in records),
            'total_tokens': sum((r.get('usage') or {}).get('total_tokens', 0) for r in records),
            'prompt_tokens': sum((r.get('usage') or {}).get('prompt_tokens', 0) for r in records),
            'completion_tokens': sum((r.get('usage') or {}).get('completion_tokens', 0) for r in records)}


def replay_job(arg):
    root, kind, identity = arg
    root = Path(root)
    row = read_json(root / ('contexts' if kind == 'parent' else 'candidates') / (identity + '.json'))
    c = row if kind == 'parent' else read_json(root / 'contexts' / (row['context'] + '.json'))
    item = c['parent'] if kind == 'parent' else row['child']
    saved = read_json(root / 'holdout' / (identity + '.json'))
    if item is None:
        return {'id': identity, 'kind': kind, 'status': 'invalid_candidate_no_game_replay'}
    try:
        actual = versus(Policy(**item), [p for _, p in panel('H')], replace(cfg_for(c['seed']), repeats=20), 'specificity-H-default')
    except Exception as exc:
        expected = saved['measured']['default']
        return {'id': identity, 'kind': kind, 'status': 'failure_reproduced' if expected['status'] == 'failed' and expected['error_type'] == type(exc).__name__ else 'mismatch',
                'error_type': type(exc).__name__}
    expected = saved['measured']['default']
    errors = {'score': abs(actual['score'] / 100 - expected['score']),
              'cooperation': abs(actual['cooperation'] - expected['cooperation']),
              'worst_score': abs(actual['worst_score'] / 100 - expected['worst_score'])}
    return {'id': identity, 'kind': kind, 'status': 'ok' if max(errors.values()) <= 1e-12 else 'mismatch',
            'errors': errors, 'games_replayed': 240}


def supplement(root, workers=6):
    root = Path(root)
    manifest = check_manifest(root)
    read_json(root / 'COMPLETE.json')
    contexts = {cid: read_json(root / 'contexts' / (cid + '.json')) for cid in {j['context'] for j in manifest['jobs']}}
    rows = [read_json(root / 'holdout' / (j['id'] + '.json')) for j in manifest['jobs']]
    eligible = {cid for cid, c in contexts.items() if c['effective_mismatch']}
    differences, included = [], []
    for seed in SEEDS:
        x = [r for r in rows if r['seed'] == seed and r['context'] in eligible and r['arm'] == 'accurate']
        y = [r for r in rows if r['seed'] == seed and r['context'] in eligible and r['arm'] == 'mismatched']
        if x and y:
            differences.append(mean(r['delta']['default']['score'] for r in x) - mean(r['delta']['default']['score'] for r in y))
            included.append(seed)
    sensitivity = {**summarize(differences), 'sign_swap_p': sign_swap_p(differences)} if differences else None
    initial = [read_json(root / 'initial' / (j['id'] + '.json')) for j in manifest['init_jobs']]
    initial_requests = [read_json(root / 'requests_initial' / (j['id'] + '.json')) for j in manifest['init_jobs']]
    offspring_budget = {arm: budget([read_json(root / 'requests_candidates' / (j['id'] + '.json'))
                                    for j in manifest['jobs'] if j['arm'] == arm]) for arm in ARMS}
    ratios = {arm: [c['block_tokens'][arm] / c['block_tokens']['accurate'] for c in contexts.values()]
              for arm in ARMS if arm != 'score'}
    # Identity-only selection, independent of validity, scores, or effect direction.
    replay_tasks = [(str(root), 'parent', sorted(contexts)[0])]
    replay_tasks += [(str(root), 'child', sorted(j['id'] for j in manifest['jobs'] if j['arm'] == arm)[0]) for arm in ARMS]
    replay_path = root / 'DETERMINISTIC_REPLAY.json'
    if replay_path.exists():
        replays = read_json(replay_path)
    else:
        with ProcessPoolExecutor(max_workers=workers) as executor:
            replays = list(executor.map(replay_job, replay_tasks))
        write_json(replay_path, replays)
    parallel_audit = {}
    for phase, directory in [('select', 'selection_scores'), ('holdout', 'holdout')]:
        log_path = root / ('parallel_' + phase) / 'PUBLISH_LOG.json'
        if not log_path.exists():
            continue
        log = read_json(log_path)
        mismatches = []
        overwritten_after_publish = 0
        for item in log['records']:
            filename = item['id'] + '.json'
            staged = root / ('parallel_' + phase) / directory / filename
            published = root / directory / filename
            if read_json(staged) != read_json(published):
                mismatches.append(item['id'])
            overwritten_after_publish += published.stat().st_mtime > item['published_at'] + .00001
        parallel_audit[phase] = {'scheduled': log['scheduled'], 'completed': log['completed'],
                                 'records_equal': len(log['records']) - len(mismatches), 'mismatches': mismatches,
                                 'already_complete_when_published': sum(x['already_completed_by_primary'] for x in log['records']),
                                 'rewritten_after_publish_by_mtime': overwritten_after_publish,
                                 'note': 'mtime is a descriptive duplicate-work indicator, not an exact game-call counter.'}
        if mismatches:
            raise RuntimeError('Parallel records disagree with final records')
    result = {'script_hash': digest(Path(__file__).read_text(encoding='utf-8')),
              'initial_budget': budget(initial_requests), 'offspring_budget': offspring_budget,
              'initial_fallbacks': [{'id': r['id'], 'reason': r['fallback']} for r in initial if r['fallback']],
              'initial_unique_deployed_source': len({Policy(**r['policy']).key for r in initial}),
              'parent_unique_source': len({Policy(**c['parent']).key for c in contexts.values()}),
              'effective_mismatch_contexts': len(eligible), 'total_contexts': len(contexts),
              'effective_mismatch_sensitivity': sensitivity, 'sensitivity_seed_ids': included,
              'length_ratios_cl100k': {arm: {'min': min(x), 'mean': mean(x), 'max': max(x)} for arm, x in ratios.items()},
              'deterministic_replay': replays, 'parallel_record_audit': parallel_audit,
              'note': 'Sensitivity excludes unchanged diagnostic mappings using only pre-generation diagnostics; frozen intention-to-treat primary and gates remain unchanged. cl100k length is not provider billing length. Replay uses the same frozen simulator, not an independent implementation.'}
    write_json(root / 'SUPPLEMENT.json', result)
    if any(r['status'] == 'mismatch' for r in replays):
        raise RuntimeError('Deterministic replay mismatch')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', nargs='?', default='results/feedback_specificity_v2')
    parser.add_argument('--workers', type=int, default=6)
    args = parser.parse_args()
    result = supplement(args.root, args.workers)
    print({'mismatch_contexts': result['effective_mismatch_contexts'], 'replay': result['deterministic_replay']})
