"""Audit budget-matched controls and report paired evolution-minus-sampling effects."""
import argparse
from collections import defaultdict
from pathlib import Path
from statistics import mean
from .analyze import interval
from .core import Policy
from .run import read_json, write_json


def summarize_controls(root):
    root = Path(root)
    plan = read_json(root/'matrix_plan.json')
    missing, issues, rows = [], [], []
    for cell in plan['cells']:
        name = f"{cell['prompt']}__{cell['selection']}__seed{cell['seed']}"
        folder = root/'independent_control'/f"seed{cell['seed']}"
        output = folder/(name+'.json')
        if not output.exists():
            missing.append(name)
            continue
        control = read_json(output)
        reference = root/name
        if not (reference/'complete.json').exists():
            issues.append(name+': reference is incomplete')
            continue
        state = read_json(reference/f"generation_{plan['generations']-1:03d}.json")
        if state['status'] != 'complete':
            issues.append(name+': reference endpoint is incomplete')
        if control['reference'] != name or control['seed'] != cell['seed']:
            issues.append(name+': control identity mismatch')
        if control['request_budget'] != state['budget_at_evaluation']['requests']:
            issues.append(name+': unequal request budgets')
        pool = read_json(folder/'pool.json')
        limit = len(pool['initial_keys'])+control['request_budget']-pool['shared_initial_requests']
        selection = read_json(folder/(name+'_selection.json'))
        if control['candidate_pool_size'] != limit or len(selection) != limit:
            issues.append(name+': selection prefix does not match budget')
        valid = [r for r in selection if r['fitness'] is not None]
        if not valid:
            issues.append(name+': no valid training selection')
            continue
        winner = min(valid, key=lambda r: (-r['fitness'], r['key'], r['ordinal']))
        champion = Policy(**control['champion'])
        if champion.key != winner['key'] or control['training_fitness'] != winner['fitness']:
            issues.append(name+': control champion differs from training-only selection')
        for ordinal, selected in enumerate(selection):
            raw = pool['policies'][ordinal] if ordinal < len(pool['policies']) else None
            key = Policy(**raw).key if raw else None
            if selected['ordinal'] != ordinal or selected['key'] != key:
                issues.append(name+': candidate prefix mismatch')
                break
        row = {**cell, 'request_budget': control['request_budget'], 'tests': {}}
        for label, evolved in state['holdout'].items():
            sampled = control['holdout'][label]
            rounds = state['test_configs'][label]['rounds']
            both = evolved['score'] is not None and sampled['score'] is not None
            row['tests'][label] = {
                'evolved_runtime_failure': evolved.get('status') == 'runtime_failure',
                'control_runtime_failure': sampled.get('status') == 'runtime_failure',
                'evolved_score': evolved['score']/rounds if evolved['score'] is not None else None,
                'control_score': sampled['score']/rounds if sampled['score'] is not None else None,
                'difference': (evolved['score']-sampled['score'])/rounds if both else None}
        rows.append(row)
    grouped = defaultdict(list)
    for row in rows:
        for label, test in row['tests'].items():
            grouped[row['prompt'], row['selection'], label].append((row['seed'], test))
    summaries = []
    for (prompt, selection, label), pairs in sorted(grouped.items()):
        valid = [(seed, test['difference']) for seed, test in pairs if test['difference'] is not None]
        differences = [value for _, value in valid]
        summaries.append({'prompt': prompt, 'selection': selection, 'test': label,
                          'n': len(pairs), 'paired_successes': len(valid),
                          'seeds': [seed for seed, _ in valid],
                          'evolved_failures': sum(test['evolved_runtime_failure'] for _, test in pairs),
                          'control_failures': sum(test['control_runtime_failure'] for _, test in pairs),
                          'mean_difference': mean(differences) if differences else None,
                          'bootstrap95': interval(differences)})
    result = {'all_controls_complete': not missing and not issues,
              'missing': missing, 'protocol_issues': issues, 'comparisons': rows,
              'summaries': summaries,
              'scope': 'Structural budget/selection audit, not independent payoff recomputation. Differences are evolution minus independent sampling, conditional on both tests succeeding. Equal request counts do not equal tokens or compute.'}
    write_json(root/'CONTROL_ANALYSIS.json', result)
    print({'controls': len(rows), 'missing': len(missing), 'issues': len(issues)})
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    summarize_controls(parser.parse_args().root)
