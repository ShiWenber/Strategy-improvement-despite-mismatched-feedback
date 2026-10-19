"""Frozen seed-cluster analysis, Holm family, and complete v2 record audit."""
import argparse
from collections import Counter
from pathlib import Path
import json
from statistics import mean

import numpy as np

from .core import Policy
from .records import read_json, write_json, population_root
from .specificity import DEFAULT_ROOT, init_prompt, seal_selections
from .specificity_assets import experiment_arms
from .holdout_metrics import (PAYOFF_SETTINGS, SETTINGS, audit_deltas, availability,
                              cluster_summary, delta_value, matched_contexts,
                              missing_details, parent_available)


def summarize(values):
    values = np.asarray(values, dtype=float)
    n = len(values)
    if not n:
        return {'n_seeds': 0, 'seed_values': [], 'mean': None, 'ci95': None,
                'estimable': False}
    if not np.isfinite(values).all():
        raise ValueError('Population summary contains missing or nonfinite values')
    rng = np.random.default_rng(2026091903)
    boot = values[rng.integers(0, n, size=(20000, n))].mean(axis=1)
    return {'n_seeds': n, 'seed_values': values.tolist(), 'mean': float(values.mean()),
            'ci95': np.quantile(boot, [.025, .975]).tolist()}


def sign_swap_p(values):
    values = np.asarray(values, dtype=float)
    n = len(values)
    if not n:
        return None
    observed = abs(values.sum())
    indices = np.arange(1 << n, dtype=np.uint32)
    permuted = np.zeros(len(indices))
    for j, value in enumerate(values):
        permuted += np.where((indices >> j) & 1, value, -value)
    return float(np.mean(np.abs(permuted) >= observed - 1e-12))


def contrast(values):
    return {**summarize(values), 'sign_swap_p': sign_swap_p(values)}


def holm(ps):
    ordered = sorted((key for key in ps if ps[key] is not None), key=lambda key: ps[key])
    adjusted, previous = {key: None for key in ps if ps[key] is None}, 0.
    for rank, key in enumerate(ordered):
        previous = max(previous, min(1., (len(ordered) - rank) * ps[key]))
        adjusted[key] = previous
    return adjusted


def audit(root, manifest):
    root = Path(root)
    issues, records = [], []
    skipped_holdouts = []
    populations = population_root(root, manifest)
    initial_frozen_at = read_json(populations / 'manifest.json')['frozen_at']
    prompt_seal = read_json(root / 'PROMPTS_SEALED.json')
    for job in manifest['init_jobs']:
        r = read_json(populations / 'requests_initial' / (job['id'] + '.json'))
        records.append(r)
        if r['prompt'] != init_prompt(job['seed'], job['slot']):
            issues.append(job['id'] + ': initial prompt mismatch')
        if r['started_at'] < initial_frozen_at:
            issues.append(job['id'] + ': initial request before freeze')
    for job in manifest['jobs']:
        r = read_json(root / 'requests_candidates' / (job['id'] + '.json'))
        records.append(r)
        c = read_json(root / 'contexts' / (job['context'] + '.json'))
        candidate = read_json(root / 'candidates' / (job['id'] + '.json'))
        outcome = read_json(root / 'holdout' / (job['id'] + '.json'))
        parent = read_json(root / 'holdout' / (job['context'] + '.json'))
        if r['prompt'] != c['prompts'][job['arm']]:
            issues.append(job['id'] + ': candidate prompt mismatch')
        if r['started_at'] < prompt_seal['sealed_at']:
            issues.append(job['id'] + ': request before prompt seal')
        if candidate['valid'] != (r['status'] == 'valid'):
            issues.append(job['id'] + ': validity mismatch')
        if outcome.get('status', 'complete') != 'complete':
            skipped_holdouts.append({'id': job['id'], 'status': outcome.get('status'),
                                     'context': job['context']})
        issues.extend(audit_deltas(outcome, parent, job['id']))
    selected = seal_selections(root, manifest, readonly=True)
    known = {j['id'] for j in manifest['jobs']}
    for r in selected['rows']:
        if r['winner'] is not None and r['winner'] not in known:
            issues.append('Unknown selected candidate')
    result = {'issues': issues, 'n_requests': len(records),
            'statuses': dict(Counter(r['status'] for r in records)),
            'returned_models': dict(Counter(r.get('returned_model', 'missing') for r in records)),
            'effective_mismatch_contexts': prompt_seal['effective_mismatch_contexts'],
            'skipped_holdouts': skipped_holdouts,
            'note': 'Record and arithmetic audit, not an independent replay of every game.'}
    if 'initial_source' in manifest:
        result.update(n_new_requests=len(records) - len(manifest['init_jobs']),
                      n_reused_initial_requests=len(manifest['init_jobs']))
    return result


def behavior_delta(row, parent):
    if not parent_available(parent, 'behavior') or row.get('deployed', {}).get('behavior') is None:
        return {}
    a = row['deployed']['behavior']['probes']
    b = parent['measured']['behavior']['probes']
    recovery = [k for k in a if 'TFT' in k or 'ALLC' in k]
    sustained = [k for k in a if 'sustained_D' in k]
    result = {}
    for mode in ('controlled', 'natural'):
        keys = [k for k in recovery if k.startswith(mode)]
        for metric in ('not_recovered', 'recovery_time_capped', 'mutual_cooperation_last5'):
            result[mode + '/' + metric] = mean(a[k]['mean'][metric] - b[k]['mean'][metric] for k in keys)
        keys = [k for k in sustained if k.startswith(mode)]
        for metric in ('own_cooperation_last5', 'unilateral_cooperation_last5', 'score'):
            result[mode + '/sustained_' + metric] = mean(a[k]['mean'][metric] - b[k]['mean'][metric] for k in keys)
    return result


def selected_seed_gains(winners, by_id, seeds, setting):
    """Include every selected-output slot, including retained parents at zero."""
    return [mean(by_id[row['winner']]['delta'][setting]['score'] if row['winner'] is not None else 0.
                 for row in winners if row['seed'] == seed)
            for seed in seeds]


def aggregate_holdouts(root, manifest, *, families=False, selection_metrics=False):
    """Summarize each setting on shared evaluable contexts, without zero imputation."""
    root = Path(root)
    seeds = manifest['seeds']
    rows = [read_json(root / 'holdout' / (job['id'] + '.json')) for job in manifest['jobs']]
    if any(row.get('status', 'complete') != 'complete' for row in rows):
        raise RuntimeError('Unrecovered holdouts remain; evaluate them before analysis')
    by_id = {row['id']: row for row in rows}
    parents = {cid: read_json(root / 'holdout' / (cid + '.json')) for cid in {row['context'] for row in rows}}
    selected = read_json(root / 'SELECTIONS_SEALED.json')['rows']
    eligible = {setting: matched_contexts(rows, setting) for setting in SETTINGS}
    missing = {setting: missing_details(rows, setting) for setting in SETTINGS}
    partial = any(len(contexts) != len(parents) for contexts in eligible.values())
    for row in rows:
        row['behavior_delta'] = behavior_delta(row, parents[row['context']])
    behavior_keys = sorted({key for row in rows for key in row['behavior_delta']})
    scores = ({identity: read_json(root / 'selection_scores' / (identity + '.json'))
               for identity in list(by_id) + list(parents)} if selection_metrics else {})
    raw, chosen = {}, {}
    for arm in experiment_arms(manifest['arms']):
        arm_rows = [row for row in rows if row['arm'] == arm]
        metrics = {}
        for setting in PAYOFF_SETTINGS:
            for metric in ('score', 'cooperation', 'worst_score'):
                metrics[setting + '/' + metric] = cluster_summary(
                    arm_rows, seeds, lambda row, s=setting, k=metric: delta_value(row, s, k), summarize,
                    contexts=eligible[setting], missing_reasons=missing[setting], include_metadata=partial)
            if families:
                for family in ('recovery', 'exploitation', 'random', 'memory'):
                    metrics[setting + '/family:' + family] = cluster_summary(
                        arm_rows, seeds, lambda row, s=setting, f=family:
                        row['deployed'][s]['families'][f] - parents[row['context']]['measured'][s]['families'][f],
                        summarize, contexts=eligible[setting], missing_reasons=missing[setting], include_metadata=partial)
        behavior = {metric: cluster_summary(
            arm_rows, seeds, lambda row, k=metric: row['behavior_delta'][k], summarize,
            contexts=eligible['behavior'], missing_reasons=missing['behavior'], include_metadata=partial) for metric in behavior_keys}
        if selection_metrics:
            for rule in ('S1', 'S2', 'S3'):
                def selection_gain(row):
                    cell = scores[row['id']]['metrics'][rule]
                    return (cell['score'] - scores[row['context']]['metrics'][rule]['score']
                            if cell['status'] == 'ok' else 0.)
                metrics['selection_metric/' + rule] = cluster_summary(arm_rows, seeds, selection_gain, summarize,
                                                                      include_metadata=partial)
        successful = [delta_value(row, 'default') for row in arm_rows
                      if row['fallback'].get('default') is False and delta_value(row, 'default') is not None]
        raw[arm] = {'n': len(arm_rows), 'valid': sum(row['valid'] for row in arm_rows),
                    'fallbacks': {s: sum(row['fallback'].get(s) is True for row in arm_rows) for s in SETTINGS},
                    'metrics': metrics, 'behavior': behavior}
        if families or selection_metrics:
            raw[arm].update(unchanged=sum(row['child'] is not None and Policy(**row['child']).key == row['parent_key'] for row in arm_rows),
                            successful_only_default_gain=mean(successful) if successful else None)
        for rule in ('S1', 'S2', 'S3'):
            choices = [row for row in selected if row['arm'] == arm and row['rule'] == rule]
            summaries = {}
            for setting in PAYOFF_SETTINGS:
                summaries[setting] = cluster_summary(
                    choices, seeds, lambda row, s=setting:
                    delta_value(by_id[row['winner']], s) if row['winner'] is not None else 0., summarize,
                    contexts=eligible[setting], missing_reasons=missing[setting], include_metadata=partial)
            chosen[rule + '/' + arm] = {
                'accepted': sum(row['accepted'] for row in choices), 'n': len(choices), 'metrics': summaries}
            if families or selection_metrics:
                chosen[rule + '/' + arm]['accepted_default_degrades'] = sum(row['winner'] is not None
                    and delta_value(by_id[row['winner']], 'default') is not None
                    and delta_value(by_id[row['winner']], 'default') < 0 for row in choices)
    report = {'raw': raw, 'selected': chosen}
    if partial:
        report['setting_availability'] = availability(rows, parents)
    return report


def analyze(root, output_suffix=""):
    root = Path(root)
    manifest = read_json(root / 'manifest.json')
    seeds = manifest['seeds']
    populations = population_root(root, manifest)
    all_rows = [read_json(root / 'holdout' / (j['id'] + '.json')) for j in manifest['jobs']]
    rows = all_rows
    parents = {cid: read_json(root / 'holdout' / (cid + '.json'))
                   for cid in {r['context'] for r in all_rows}}
    selected = read_json(root / 'SELECTIONS_SEALED.json')['rows']
    aggregate = aggregate_holdouts(root, manifest, families=True, selection_metrics=True)
    raw, chosen = aggregate['raw'], aggregate['selected']
    def raw_values(arm):
        return np.array(raw[arm]['metrics']['default/score']['seed_values'])
    def selected_values(rule, arm):
        return np.array(chosen[rule + '/' + arm]['metrics']['default']['seed_values'])
    primary = contrast(raw_values('accurate') - raw_values('mismatched'))
    # Continuous parent-feature associations are exploratory, not mediation evidence.
    associations = []
    for cid in sorted(parents):
        seed = next(r['seed'] for r in rows if r['context'] == cid)
        pop = read_json(populations / 'populations' / f's{seed}.json')
        context = read_json(root / 'contexts' / (cid + '.json'))
        f = pop['diagnostics'][context['slot']]
        deficit = 1 - mean(f[k]['mean']['mutual_cooperation_last5'] for k in ('one_D_TFT', 'four_D_TFT', 'four_D_ALLC'))
        vulnerability = f['sustained_D']['mean']['unilateral_cooperation_last5']
        accurate = [r for r in rows if r['context'] == cid and r['arm'] == 'accurate']
        mismatch = [r for r in rows if r['context'] == cid and r['arm'] == 'mismatched']
        if not accurate or not mismatch:
            continue
        associations.append({'context': cid, 'seed': seed, 'recovery_deficit': deficit,
                             'exploitation_vulnerability': vulnerability,
                             'accurate_minus_mismatched_default': mean(r['delta']['default']['score'] for r in accurate) - mean(r['delta']['default']['score'] for r in mismatch)})
    # The interaction coefficient is the slope of the within-parent arm effect
    # on a pre-generation parent feature. Resampling retains all parents in a seed.
    feature_effects = {}
    def slope(items, feature):
        x = np.array([r[feature] for r in items])
        y = np.array([r['accurate_minus_mismatched_default'] for r in items])
        denominator = float(np.sum((x - x.mean()) ** 2))
        return float(np.sum((x - x.mean()) * (y - y.mean())) / denominator) if denominator > 1e-12 else None
    for feature in ('recovery_deficit', 'exploitation_vulnerability'):
        rng = np.random.default_rng(2026091904)
        coefficients = []
        for _ in range(5000):
            sample = [r for seed in rng.choice(seeds, len(seeds), replace=True) for r in associations if r['seed'] == seed]
            value = slope(sample, feature)
            if value is not None:
                coefficients.append(value)
        feature_effects[feature] = {'interaction_slope': slope(associations, feature),
                                   'ci95': np.quantile(coefficients, [.025, .975]).tolist() if coefficients else None,
                                   'identified_bootstrap_samples': len(coefficients), 'exploratory': True}
    disagreements = {}
    for arm in experiment_arms(manifest['arms']):
        items = {(r['context'], r['rule']): r['winner'] for r in selected if r['arm'] == arm}
        disagreements[arm] = {a + '-' + b: sum(items[cid, a] != items[cid, b] for cid in parents)
                              for a, b in [('S1', 'S2'), ('S2', 'S3'), ('S1', 'S3')]}
    result = {'raw': raw, 'selected': chosen, 'primary': primary,
              'selection_disagreements': disagreements, 'parent_feature_associations_exploratory': associations,
              'parent_feature_interactions_exploratory': feature_effects,
              'note': f'{len(seeds)} independent population clusters. Original prespecified primary: Accurate versus Mismatched raw proposals. Selected outputs, behaviour and parent-feature associations are exploratory; CIs are unadjusted seed-bootstrap intervals.'}
    if 'setting_availability' in aggregate:
        result['setting_availability'] = aggregate['setting_availability']
    if len(seeds) == 1:
        result['note'] += ' Single-population API check: bootstrap intervals and sign-swap p-values are not evidence about the paper population.'
    write_json(root / f'ANALYSIS{output_suffix}.json', result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', nargs='?', default=DEFAULT_ROOT)
    parser.add_argument('--output-suffix', default='', help='Append to the generated analysis filename.')
    parser.add_argument('--audit-only', action='store_true', help='Run the optional record audit instead of analysis.')
    parser.add_argument('--audit-output', type=Path, help='Explicit destination for the optional audit JSON.')
    args = parser.parse_args()
    if args.audit_only:
        if args.audit_output is None:
            parser.error('--audit-only requires --audit-output')
        result = audit(args.root, read_json(Path(args.root) / 'manifest.json'))
        write_json(args.audit_output, result)
        print(json.dumps(result))
    else:
        if args.audit_output is not None:
            parser.error('--audit-output requires --audit-only')
        result = analyze(args.root, args.output_suffix)
        print(json.dumps({'primary': result['primary']}))
