"""Exploratory behaviour through proposal and adoption, using sealed records only.

No LLM requests, game replays, or changes to the frozen experiment. The unit of
aggregation is the original population seed. Stages are not generations.
"""
from __future__ import annotations

from collections import defaultdict
import argparse
import json
from pathlib import Path
from statistics import mean

import numpy as np

ARMS = ('accurate', 'mismatched')
METRICS = ('defection_exposure', 'recovery_rounds', 'not_recovered', 'mutual_cooperation')
STAGES = ('parent', 'raw', 'S3')
def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def measure(record, mode):
    p = record['behavior']['probes']
    r = [p[f'{mode}_{s}']['mean'] for s in ('two_D_TFT', 'five_D_GTFT', 'three_D_ALLC')]
    return {
        'defection_exposure': p[f'{mode}_sustained_D']['mean']['unilateral_cooperation_last5'],
        'recovery_rounds': mean(v['recovery_time_capped'] for v in r),
        'not_recovered': mean(v['not_recovered'] for v in r),
        'mutual_cooperation': mean(v['mutual_cooperation_last5'] for v in r),
    }


def summarize(v):
    a = np.asarray(v, dtype=float)
    if not len(a) or not np.isfinite(a).all():
        raise ValueError('Behavior summaries require finite population values')
    rng = np.random.default_rng(2026092407)
    indices = rng.integers(0, len(a), size=(20000, len(a)))
    return {'mean': float(a.mean()), 'seed_values': a.tolist(),
            'ci95_exploratory': np.quantile(a[indices].mean(1), [.025, .975]).tolist(),
            'positive': int((a > 1e-12).sum()), 'negative': int((a < -1e-12).sum()),
            'zero': int((np.abs(a) <= 1e-12).sum())}


def analyze(config, root):
    manifest = read(root / 'manifest.json')
    seeds = manifest['seeds']
    seal = read(root / 'SELECTIONS_SEALED.json')
    selection = {(r['context'], r['arm']): r for r in seal['rows'] if r['rule'] == 'S3' and r['arm'] in ARMS}
    parent_ids = sorted({j['context'] for j in manifest['jobs']})
    parents = {cid: read(root / 'holdout' / f'{cid}.json') for cid in parent_ids}
    matching_jobs = [j for j in manifest['jobs'] if j['arm'] in ARMS]
    if set(selection) != {(job['context'], job['arm']) for job in matching_jobs}:
        raise ValueError('Behavior summaries require an S3 decision for every candidate pool')
    children = {j['id']: read(root / 'holdout' / (j['id'] + '.json')) for j in matching_jobs}
    jobs = defaultdict(list)
    for j in matching_jobs:
        jobs[(j['context'], j['arm'])].append(j)
    pool_rows = []
    for (context, arm), jj in sorted(jobs.items()):
        jj.sort(key=lambda j: j['draw'])
        if len(jj) != manifest['draws']:
            raise ValueError('Behavior summary candidate pool differs from the manifest draw count')
        p = parents[context]['measured']
        child_rows = [children[j['id']] for j in jj]
        winner = selection[(context, arm)]['winner']
        adopted = children[winner]['deployed'] if winner else p
        row = {'config': config, 'context': context, 'seed': jj[0]['seed'], 'arm': arm,
               'winner': winner, 'H_score': {'parent': p['default']['score'],
               'raw': mean(c['deployed']['default']['score'] for c in child_rows),
               'S3': adopted['default']['score']}, 'behavior': {}}
        for mode in ('controlled', 'natural'):
            baseline = measure(p, mode)
            cr = [measure(c['deployed'], mode) for c in child_rows]
            row['behavior'][mode] = {
                'parent': baseline,
                'raw': {m: mean(c[m] for c in cr) for m in METRICS},
                'S3': measure(adopted, mode),
            }
        pool_rows.append(row)
    summaries = {}
    for mode in ('controlled', 'natural'):
        for arm in (*ARMS, 'pooled'):
            subset = [r for r in pool_rows if arm == 'pooled' or r['arm'] == arm]
            for metric in METRICS:
                key = f'{mode}/{arm}/{metric}'
                ss = {stage: summarize([mean(r['behavior'][mode][stage][metric] for r in subset if r['seed'] == s)
                                      for s in seeds]) for stage in STAGES}
                for a, b in (('raw', 'parent'), ('S3', 'parent'), ('S3', 'raw')):
                    ss[f'{a}_minus_{b}'] = summarize(np.asarray(ss[a]['seed_values']) - ss[b]['seed_values'])
                summaries[key] = ss
    contrasts = {}
    for mode in ('controlled', 'natural'):
        for metric in METRICS:
            for stage in ('raw', 'S3'):
                a = np.array(summaries[f'{mode}/accurate/{metric}'][stage]['seed_values'])
                b = np.array(summaries[f'{mode}/mismatched/{metric}'][stage]['seed_values'])
                contrasts[f'{mode}/{stage}/{metric}/accurate_minus_mismatched'] = summarize(a - b)
    return {'summaries': summaries, 'matched_contrasts': contrasts, 'pool_rows': pool_rows,
            'n_seeds': len(seeds), 'seed_ids': seeds, 'n_parents': len(parents), 'n_slots': len(children),
            'S3_accepted': sum(r['winner'] is not None for r in pool_rows),
            'behavior_fallbacks': sum(c['fallback']['behavior'] for c in children.values())}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--off-root', type=Path, required=True)
    parser.add_argument('--on-root', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    data = {
        'non_thinking': analyze('non_thinking', args.off_root.resolve()),
        'thinking': analyze('thinking', args.on_root.resolve()),
    }
    seeds = data['non_thinking']['seed_ids']
    if not seeds or data['thinking']['seed_ids'] != seeds:
        raise ValueError('Behavior summaries require matching nonempty population seed orders')
    report = {'status': 'complete', 'analysis_status': 'post_hoc_exploratory',
              'seeds': seeds, 'independent_units': len(seeds), 'arms': list(ARMS),
              'stage_definition': {'parent': 'Shared parents within each population',
                                   'raw': 'All candidate outputs in the matching report conditions',
                                   'S3': 'One sealed decision per parent and report condition'},
              'no_new_games_or_model_calls': True,
              'configs': data}
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print('Recomputed independent behaviour for two report conditions')


if __name__ == '__main__':
    main()
