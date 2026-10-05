"""Frozen seed-cluster analysis, Holm family, and complete v2 record audit."""
import argparse
from collections import Counter
from pathlib import Path
import json
from statistics import mean

import numpy as np

from .core import Policy, digest
from .run import read_json, write_json
from .specificity import (DEFAULT_ROOT, check_manifest, init_prompt, choose, seal_selections)
from .specificity_assets import ARMS, SEEDS, RANKS


def summarize(values):
    values = np.asarray(values, dtype=float)
    n = len(values)
    if not n:
        raise ValueError('No independent clusters')
    rng = np.random.default_rng(2026091903)
    boot = values[rng.integers(0, n, size=(20000, n))].mean(axis=1)
    return {'n_seeds': n, 'seed_values': values.tolist(), 'mean': float(values.mean()),
            'ci95': np.quantile(boot, [.025, .975]).tolist()}


def sign_swap_p(values):
    values = np.asarray(values, dtype=float)
    n = len(values)
    observed = abs(values.sum())
    indices = np.arange(1 << n, dtype=np.uint32)
    permuted = np.zeros(len(indices))
    for j, value in enumerate(values):
        permuted += np.where((indices >> j) & 1, value, -value)
    return float(np.mean(np.abs(permuted) >= observed - 1e-12))


def contrast(values):
    return {**summarize(values), 'sign_swap_p': sign_swap_p(values)}


def holm(ps):
    ordered = sorted(ps, key=lambda key: ps[key])
    adjusted, previous = {}, 0.
    for rank, key in enumerate(ordered):
        previous = max(previous, min(1., (len(ordered) - rank) * ps[key]))
        adjusted[key] = previous
    return adjusted


def audit(root, manifest):
    root = Path(root)
    issues, records = [], []
    prompt_seal = read_json(root / 'PROMPTS_SEALED.json')
    prompt_hash = {r['id']: r['prompt_hash'] for r in prompt_seal['rows']}
    for job in manifest['init_jobs']:
        r = read_json(root / 'requests_initial' / (job['id'] + '.json'))
        records.append(r)
        if r['prompt'] != init_prompt(job['seed'], job['slot']):
            issues.append(job['id'] + ': initial prompt mismatch')
        if r['started_at'] < manifest['frozen_at']:
            issues.append(job['id'] + ': initial request before freeze')
    for job in manifest['jobs']:
        r = read_json(root / 'requests_candidates' / (job['id'] + '.json'))
        records.append(r)
        c = read_json(root / 'contexts' / (job['context'] + '.json'))
        candidate = read_json(root / 'candidates' / (job['id'] + '.json'))
        outcome = read_json(root / 'holdout' / (job['id'] + '.json'))
        parent = read_json(root / 'holdout' / (job['context'] + '.json'))
        if digest(r['prompt']) != prompt_hash[job['id']] or r['prompt'] != c['prompts'][job['arm']]:
            issues.append(job['id'] + ': candidate prompt mismatch')
        if digest(json.dumps(c, sort_keys=True)) != prompt_seal['contexts'][job['context']]:
            issues.append(job['id'] + ': context changed')
        if r['started_at'] < prompt_seal['sealed_at']:
            issues.append(job['id'] + ': request before prompt seal')
        if candidate['valid'] != (r['status'] == 'valid'):
            issues.append(job['id'] + ': validity mismatch')
        if candidate['child'] and Policy(**candidate['child']).key != r['code_hash']:
            issues.append(job['id'] + ': response/source mismatch')
        for setting in ('default', 'noise01', 'long'):
            for metric in ('score', 'cooperation', 'worst_score'):
                delta = outcome['deployed'][setting][metric] - parent['measured'][setting][metric]
                if abs(delta - outcome['delta'][setting][metric]) > 1e-10:
                    issues.append(job['id'] + ': delta mismatch')
                if outcome['fallback'][setting] and abs(delta) > 1e-10:
                    issues.append(job['id'] + ': fallback mismatch')
    selected = seal_selections(root, manifest)
    release = read_json(root / 'H_RELEASED.json')
    if release['selection_digest'] != digest((root / 'SELECTIONS_SEALED.json').read_text(encoding='utf-8')):
        issues.append('Selection seal does not match holdout release')
    known = {j['id'] for j in manifest['jobs']}
    for r in selected['rows']:
        if r['winner'] is not None and r['winner'] not in known:
            issues.append('Unknown selected candidate')
    for j in manifest['jobs']:
        path = root / 'candidates' / (j['id'] + '.json')
        if selected['candidate_hashes'][j['id']] != digest(path.read_text(encoding='utf-8')):
            issues.append(j['id'] + ': candidate changed after selection')
    return {'issues': issues, 'n_requests': len(records),
            'statuses': dict(Counter(r['status'] for r in records)),
            'returned_models': dict(Counter(r.get('returned_model', 'missing') for r in records)),
            'usage_missing': sum(r.get('usage') is None for r in records),
            'total_tokens': sum((r.get('usage') or {}).get('total_tokens', 0) for r in records),
            'prompt_tokens': sum((r.get('usage') or {}).get('prompt_tokens', 0) for r in records),
            'completion_tokens': sum((r.get('usage') or {}).get('completion_tokens', 0) for r in records),
            'effective_mismatch_contexts': prompt_seal['effective_mismatch_contexts'],
            'note': 'Record/hash/arithmetic audit, not an independent replay of every game.'}


def behavior_delta(row, parent):
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


def analyze(root):
    root = Path(root)
    manifest = check_manifest(root)
    read_json(root / 'COMPLETE.json')
    audit_result = audit(root, manifest)
    write_json(root / 'AUDIT.json', audit_result)
    if audit_result['issues']:
        raise RuntimeError('Audit failed; do not interpret incomplete or inconsistent results')
    rows = [read_json(root / 'holdout' / (j['id'] + '.json')) for j in manifest['jobs']]
    by_id = {r['id']: r for r in rows}
    parents = {cid: read_json(root / 'holdout' / (cid + '.json')) for cid in {r['context'] for r in rows}}
    selected = read_json(root / 'SELECTIONS_SEALED.json')['rows']
    selection_scores = {identity: read_json(root / 'selection_scores' / (identity + '.json'))
                        for identity in list(by_id) + list(parents)}
    for row in rows:
        row['behavior_delta'] = behavior_delta(row, parents[row['context']])
    raw, chosen = {}, {}
    for arm in ARMS:
        arm_rows = [r for r in rows if r['arm'] == arm]
        metrics = {}
        for setting in ('default', 'noise01', 'long'):
            for metric in ('score', 'cooperation', 'worst_score'):
                values = [mean(r['delta'][setting][metric] for r in arm_rows if r['seed'] == seed) for seed in SEEDS]
                metrics[setting + '/' + metric] = summarize(values)
            for family in ('recovery', 'exploitation', 'random', 'memory'):
                values = [mean(r['deployed'][setting]['families'][family] - parents[r['context']]['measured'][setting]['families'][family]
                               for r in arm_rows if r['seed'] == seed) for seed in SEEDS]
                metrics[setting + '/family:' + family] = summarize(values)
        behavior = {metric: summarize([mean(r['behavior_delta'][metric] for r in arm_rows if r['seed'] == seed) for seed in SEEDS])
                    for metric in arm_rows[0]['behavior_delta']}
        for rule in ('S1', 'S2', 'S3'):
            values = []
            for seed in SEEDS:
                gains = []
                for r in arm_rows:
                    if r['seed'] != seed:
                        continue
                    item = selection_scores[r['id']]['metrics'][rule]
                    baseline = selection_scores[r['context']]['metrics'][rule]['score']
                    gains.append(item['score'] - baseline if item['status'] == 'ok' else 0.)
                values.append(mean(gains))
            metrics['selection_metric/' + rule] = summarize(values)
        raw[arm] = {'n': len(arm_rows), 'valid': sum(r['valid'] for r in arm_rows),
                    'unchanged': sum(r['child'] is not None and Policy(**r['child']).key == r['parent_key'] for r in arm_rows),
                    'fallbacks': {s: sum(r['fallback'][s] for r in arm_rows) for s in ('default', 'noise01', 'long', 'behavior')},
                    'metrics': metrics, 'behavior': behavior,
                    'successful_only_default_gain': mean(r['delta']['default']['score'] for r in arm_rows if not r['fallback']['default'])
                    if any(not r['fallback']['default'] for r in arm_rows) else None}
        for rule in ('S1', 'S2', 'S3'):
            winners = [r for r in selected if r['arm'] == arm and r['rule'] == rule]
            sm = {}
            for setting in ('default', 'noise01', 'long'):
                values = [mean(by_id[r['winner']]['delta'][setting]['score'] if r['winner'] else 0.
                               for r in winners if r['seed'] == seed) for seed in SEEDS]
                sm[setting] = summarize(values)
            chosen[rule + '/' + arm] = {'accepted': sum(r['accepted'] for r in winners), 'n': len(winners), 'metrics': sm,
                                       'accepted_default_degrades': sum(r['winner'] is not None and by_id[r['winner']]['delta']['default']['score'] < 0 for r in winners)}
    def raw_values(arm):
        return np.array(raw[arm]['metrics']['default/score']['seed_values'])
    def selected_values(rule, arm):
        return np.array(chosen[rule + '/' + arm]['metrics']['default']['seed_values'])
    primary = contrast(raw_values('accurate') - raw_values('mismatched'))
    secondary = {'raw_accurate-' + arm: contrast(raw_values('accurate') - raw_values(arm))
                 for arm in ('score', 'background', 'cooperation')}
    secondary['S3_accurate-score'] = contrast(selected_values('S3', 'accurate') - selected_values('S3', 'score'))
    secondary['S3_accurate-parent'] = contrast(selected_values('S3', 'accurate'))
    secondary['selection_interaction'] = contrast((selected_values('S3', 'accurate') - selected_values('S3', 'score')) -
                                                  (selected_values('S2', 'accurate') - selected_values('S2', 'score')))
    adjusted = holm({key: value['sign_swap_p'] for key, value in secondary.items()})
    for key in secondary:
        secondary[key]['holm_p'] = adjusted[key]
    # Continuous parent-feature associations are exploratory, not mediation evidence.
    associations = []
    for cid in sorted(parents):
        seed = next(r['seed'] for r in rows if r['context'] == cid)
        pop = read_json(root / 'populations' / f's{seed}.json')
        context = read_json(root / 'contexts' / (cid + '.json'))
        f = pop['diagnostics'][context['slot']]
        deficit = 1 - mean(f[k]['mean']['mutual_cooperation_last5'] for k in ('one_D_TFT', 'four_D_TFT', 'four_D_ALLC'))
        vulnerability = f['sustained_D']['mean']['unilateral_cooperation_last5']
        accurate = [r for r in rows if r['context'] == cid and r['arm'] == 'accurate']
        mismatch = [r for r in rows if r['context'] == cid and r['arm'] == 'mismatched']
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
            sample = [r for seed in rng.choice(SEEDS, len(SEEDS), replace=True) for r in associations if r['seed'] == seed]
            value = slope(sample, feature)
            if value is not None:
                coefficients.append(value)
        feature_effects[feature] = {'interaction_slope': slope(associations, feature),
                                   'ci95': np.quantile(coefficients, [.025, .975]).tolist() if coefficients else None,
                                   'identified_bootstrap_samples': len(coefficients), 'exploratory': True}
    quantitative_gate = primary['ci95'][0] > 0 and primary['mean'] >= .05 and all(
        secondary[key]['mean'] > 0 and secondary[key]['holm_p'] < .05
        for key in ('raw_accurate-score', 'raw_accurate-background', 'raw_accurate-cooperation', 'S3_accurate-parent'))
    disagreements = {}
    for arm in ARMS:
        items = {(r['context'], r['rule']): r['winner'] for r in selected if r['arm'] == arm}
        disagreements[arm] = {a + '-' + b: sum(items[cid, a] != items[cid, b] for cid in parents)
                              for a, b in [('S1', 'S2'), ('S2', 'S3'), ('S1', 'S3')]}
    result = {'audit': audit_result, 'raw': raw, 'selected': chosen, 'primary': primary, 'secondary': secondary,
              'selection_disagreements': disagreements, 'parent_feature_associations_exploratory': associations,
              'parent_feature_interactions_exploratory': feature_effects,
              'gate': {'quantitative_pass': quantitative_gate, 'behavior_review_required_if_pass': quantitative_gate,
                       'multigeneration_authorized_by_evidence': False,
                       'reason': 'Quantitative gate failed; do not start phase D.' if not quantitative_gate else 'Review independent directional behavior before any phase D dispatch.'},
              'note': '20 independent population clusters. Primary is accurate vs mismatched raw proposals. Six secondary tests Holm-adjusted. Other endpoints exploratory. CIs are unadjusted seed-bootstrap intervals; a parent sign-swap test requires symmetry and is not a randomized parent assignment.'}
    write_json(root / 'ANALYSIS.json', result)
    lines = ['# 诊断针对性实验 v2：冻结协议结果', '', f"完成 {audit_result['n_requests']} 次请求；报告 tokens {audit_result['total_tokens']:,}；审计问题 {len(audit_result['issues'])}。", '',
             '| 组别 | 有效候选 | 原始默认增量 | S1 后增量 | S2 后增量 | S3 后增量 |', '| --- | ---: | ---: | ---: | ---: | ---: |']
    for arm in ARMS:
        lines.append(f"| {arm} | {raw[arm]['valid']}/120 | {raw[arm]['metrics']['default/score']['mean']:+.6f} | " +
                     ' | '.join(f"{chosen[r + '/' + arm]['metrics']['default']['mean']:+.6f}" for r in ('S1', 'S2', 'S3')) + ' |')
    lines += ['', f"主比较 accurate−mismatched：{primary['mean']:+.6f}，95% 区间 {primary['ci95']}，配对符号交换 p={primary['sign_swap_p']:.6f}。", '',
              '| 预定次比较 | 差值 | 未校正 95% 区间 | Holm p |', '| --- | ---: | --- | ---: |']
    for key, value in secondary.items():
        lines.append(f"| {key} | {value['mean']:+.6f} | {value['ci95']} | {value['holm_p']:.6f} |")
    lines += ['', '量化推进门槛：' + ('通过，仍需独立行为审查。' if quantitative_gate else '未通过，不启动多代扩展。'), '', result['note'], '']
    (root / 'REPORT.md').write_text('\n'.join(lines), encoding='utf-8')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', nargs='?', default=DEFAULT_ROOT)
    args = parser.parse_args()
    result = analyze(args.root)
    print(json.dumps({'primary': result['primary'], 'gate': result['gate'], 'audit': result['audit']}))
