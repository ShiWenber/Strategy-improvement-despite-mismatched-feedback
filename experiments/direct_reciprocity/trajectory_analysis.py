"""Observed evolution curves and request-budget aligned, paired-seed contrasts."""
import argparse
from pathlib import Path
from .run import read_json, write_json


def align_pair(left, right, metric):
    """Use the latest observed generation within shared budget support; no lookahead."""
    if not left or not right:
        return []
    low = max(min(r['requests'] for r in left), min(r['requests'] for r in right))
    high = min(max(r['requests'] for r in left), max(r['requests'] for r in right))
    budgets = sorted({r['requests'] for r in left+right if low <= r['requests'] <= high})
    rows = []
    for budget in budgets:
        a = max((r for r in left if r['requests'] <= budget), key=lambda r: (r['requests'], r['generation']))
        b = max((r for r in right if r['requests'] <= budget), key=lambda r: (r['requests'], r['generation']))
        rows.append({'budget': budget, 'left_generation': a['generation'], 'right_generation': b['generation'],
                     'left_requests': a['requests'], 'right_requests': b['requests'],
                     'difference': b[metric]-a[metric] if a[metric] is not None and b[metric] is not None else None})
    return rows


def analyze_trajectories(root):
    root = Path(root)
    plan = read_json(root/'matrix_plan.json')
    curves = {}
    for cell in plan['cells']:
        name = f"{cell['prompt']}__{cell['selection']}__seed{cell['seed']}"
        rows = []
        for path in sorted((root/name).glob('generation_*.json')):
            state = read_json(path)
            if state['status'] != 'complete':
                continue
            budget = state['budget_at_evaluation']
            row = {'generation': state['generation'], 'requests': budget['requests'],
                   'tokens': budget['total_tokens'], 'valid_requests': budget['valid'],
                   'train_fitness_per_round': max(r['fitness'] for r in state['assessment'])/plan['rounds'],
                   'code_diversity': state['code_diversity'],
                   'behavior_diversity': state['behavior_diagnostics']['distinct_valid_profiles']}
            for label, test in state['holdout'].items():
                rounds = state['test_configs'][label]['rounds']
                row[label+'_score'] = test['score']/rounds if test['score'] is not None else None
                row[label+'_cooperation'] = test['cooperation']
                row[label+'_worst_score'] = test['worst_score']/rounds if test['worst_score'] is not None else None
                row[label+'_failure'] = test.get('status') == 'runtime_failure'
            rows.append(row)
        curves[name] = rows
    contrasts = []
    seeds = sorted({cell['seed'] for cell in plan['cells']})
    for seed in seeds:
        pairs = []
        for selection in ('paper_truncation',):
            for prompt in ('score', 'full'):
                pairs.append((f'minimal__{selection}__seed{seed}', f'{prompt}__{selection}__seed{seed}'))
        for left, right in pairs:
            for metric in ('default_score', 'default_cooperation', 'train_fitness_per_round'):
                points = align_pair(curves.get(left, []), curves.get(right, []), metric)
                if points:
                    contrasts.append({'seed': seed, 'left': left, 'right': right,
                                      'metric': metric, 'points': points})
    output = {'curves': curves, 'budget_aligned_contrasts': contrasts,
              'note': 'Partial observed curves. Latest recorded generation at or below each request budget; only shared support, no interpolation or extrapolation. Right minus left; underlying actual request counts are retained. Equal budget ceilings do not imply identical calls, tokens, generations, or evaluation compute. Test failure is missing.'}
    write_json(root/'TRAJECTORIES.json', output)
    print({'observed_generations': sum(map(len, curves.values())), 'paired_curves': len(contrasts)})
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    analyze_trajectories(parser.parse_args().root)
