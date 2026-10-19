"""Post-hoc exact policy contrasts on sealed candidate pools; no API or game calls."""
import argparse
from .specificity_assets import ARMS
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
from .holdout_metrics import (cluster_summary, delta_value, matched_contexts,
                              missing_details, PAYOFF_SETTINGS)


def policies(gains, scores, parent_score, valid):
    """R=random child; G=random then gate; U=random eligible; B=best eligible."""
    eligible = [i for i in range(2) if valid[i] and scores[i] > parent_score]
    winner = max(eligible, key=lambda i: (scores[i], -i)) if eligible else None
    r = sum(gains) / 2
    g = sum(gains[i] for i in eligible) / 2
    u = sum(gains[i] for i in eligible) / len(eligible) if eligible else 0.0
    b = gains[winner] if winner is not None else 0.0
    return dict(R=r, G=g, U=u, B=b, gate=g-r, opportunity=u-g,
                ranking=b-u, total=b-r, winner=winner, eligible=len(eligible))


def run(root, output_suffix=""):
    root = Path(root)
    def read(name):
        raw = (root/name).read_bytes()
        return json.loads(raw)

    manifest = read('manifest.json')
    jobs = defaultdict(list)
    for j in manifest['jobs']:
        jobs[(j['context'], j['arm'])].append(j)
    children = {j['id']: read(f"holdout/{j['id']}.json") for j in manifest['jobs']}
    if any(c.get('status', 'complete') != 'complete' for c in children.values()):
        raise RuntimeError('Unrecovered holdouts remain; evaluate them before policy analysis')
    eligible_contexts = {setting: matched_contexts(children.values(), setting) for setting in PAYOFF_SETTINGS}
    missing = {setting: missing_details(children.values(), setting) for setting in PAYOFF_SETTINGS}
    n_contexts = len({job['context'] for job in manifest['jobs']})
    partial = any(len(contexts) != n_contexts for contexts in eligible_contexts.values())
    records = []
    counts = defaultdict(lambda: dict(candidates=0, better=0, worse=0, equal=0, pools=0,
                                    pools_with_better=0, both_better=0, skipped_pools=0))
    metrics = ('R', 'G', 'U', 'B', 'gate', 'opportunity', 'ranking', 'total')
    for (context, arm), jj in sorted(jobs.items()):
        jj.sort(key=lambda x: x['draw'])
        if len(jj) != 2:
            raise ValueError('Policy contrasts require two candidates per parent and condition')
        child = [children[j['id']] for j in jj]
        cs = [read(f"selection_scores/{j['id']}.json") for j in jj]
        ps = read(f'selection_scores/{context}.json')
        count = counts[arm]
        count['pools'] += 1
        if context not in eligible_contexts['default']:
            count['skipped_pools'] += 1
        else:
            gains = [c['delta']['default']['score'] for c in child]
            count['candidates'] += 2
            better = sum(v > 1e-12 for v in gains)
            count['better'] += better
            count['worse'] += sum(v < -1e-12 for v in gains)
            count['equal'] += sum(abs(v) <= 1e-12 for v in gains)
            count['pools_with_better'] += int(better > 0)
            count['both_better'] += int(better == 2)
        for rule in ('S1', 'S2', 'S3'):
            valid = [c['valid'] and s['metrics'][rule]['status'] == 'ok' for c, s in zip(child, cs)]
            scores = [s['metrics'][rule].get('score', float('-inf')) for s in cs]
            parent_score = ps['metrics'][rule]['score']
            for setting in PAYOFF_SETTINGS:
                if context in eligible_contexts[setting]:
                    gains = [delta_value(c, setting) for c in child]
                    p = policies(gains, scores, parent_score, valid)
                else:
                    eligible = [i for i in range(2) if valid[i] and scores[i] > parent_score]
                    p = dict.fromkeys(metrics)
                    p.update(winner=max(eligible, key=lambda i: (scores[i], -i)) if eligible else None,
                             eligible=len(eligible), estimable=False,
                             missing_reason=missing[setting].get(context,
                                 {'reason': 'excluded_to_preserve_matched_contexts'}))
                records.append(dict(context=context, seed=jj[0]['seed'], arm=arm, rule=rule,
                                    setting=setting, **p))
    seeds = sorted(manifest['seeds'])
    def summarize(values):
        x = np.asarray(values, dtype=float)
        if not len(x):
            return dict(mean=None, ci95=None, seed_values=[])
        indices = np.random.default_rng(20260920).integers(0, len(x), size=(20000, len(x)))
        lo, hi = np.quantile(x[indices].mean(axis=1), [.025, .975])
        return dict(mean=float(x.mean()), ci95=[float(lo), float(hi)], seed_values=x.tolist())

    summaries = {}
    for arm in list(manifest['arms']) + ['pooled']:
        for rule in ('S1', 'S2', 'S3'):
            for setting in ('default', 'noise01', 'long'):
                rows = [r for r in records if (r['arm'] in ARMS if arm == 'pooled' else r['arm'] == arm)
                        and r['rule'] == rule and r['setting'] == setting]
                result = {}
                for metric in metrics:
                    result[metric] = cluster_summary(
                        rows, seeds, lambda row, key=metric: row[key], summarize,
                        contexts=eligible_contexts[setting], missing_reasons=missing[setting], include_metadata=partial)
                evaluated = [row for row in rows if row['context'] in eligible_contexts[setting]]
                result['eligible_pool_counts'] = {str(n): sum(r['eligible'] == n for r in evaluated) for n in range(3)}
                result['accepted_test_degrades'] = sum(r['winner'] is not None and r['B'] < -1e-12 for r in evaluated)
                if partial:
                    result['n_evaluable_pools'] = len(evaluated)
                    result['n_unavailable_pools'] = len(rows) - len(evaluated)
                summaries[f'{arm}/{rule}/{setting}'] = result
    out = root/'role_analysis'
    out.mkdir(exist_ok=True)
    result = dict(status='complete', design='post_hoc_fixed_pool_exact_expectations',
                  note='Exploratory unadjusted population-bootstrap intervals. No new model requests or games.',
                  bootstrap_seed=20260920, bootstrap_replicates=20000, independent_clusters=len(seeds),
                  counts=dict(counts), summaries=summaries, rows=records,
                  pooled_arms=list(ARMS))
    (out/f'ANALYSIS{output_suffix}.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return out


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', nargs='?', default='results/feedback_specificity_v2')
    parser.add_argument('--output-suffix', default='')
    args = parser.parse_args()
    print(run(args.root, args.output_suffix))
