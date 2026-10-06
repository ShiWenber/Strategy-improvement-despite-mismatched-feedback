"""Exploratory behaviour through proposal and adoption, using sealed records only.

No LLM requests, game replays, or changes to the frozen experiment. The unit of
aggregation is the original population seed. Stages are not generations.
"""
from __future__ import annotations

from collections import defaultdict
from hashlib import sha256
import argparse
import json
from pathlib import Path
from statistics import mean

REPO = Path(__file__).resolve().parents[2]
import numpy as np

ROOTS = {
    'non_thinking': 'results/feedback_specificity_v2',
    'thinking': 'results/feedback_specificity_thinking_384k_20260923',
}
LABELS = {'non_thinking': 'Thinking OFF', 'thinking': 'Thinking ON'}
ARMS = ('accurate', 'mismatched')
SEEDS = list(range(200, 220))
METRICS = ('defection_exposure', 'recovery_rounds', 'not_recovered', 'mutual_cooperation')
STAGES = ('parent', 'raw', 'S3')
INPUT_HASHES = {}

def read(path):
    raw = path.read_bytes()
    INPUT_HASHES[str(path.relative_to(REPO)).replace('\\', '/')] = sha256(raw).hexdigest()
    return json.loads(raw)


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
    rng = np.random.default_rng(2026092407)
    indices = rng.integers(0, len(a), size=(20000, len(a)))
    return {'mean': float(a.mean()), 'seed_values': a.tolist(),
            'ci95_exploratory': np.quantile(a[indices].mean(1), [.025, .975]).tolist(),
            'positive': int((a > 1e-12).sum()), 'negative': int((a < -1e-12).sum()),
            'zero': int((np.abs(a) <= 1e-12).sum())}


def analyze(config, root, analysis_suffix=""):
    manifest = read(root / 'manifest.json')
    seal = read(root / 'SELECTIONS_SEALED.json')
    frozen = read(root / f'ANALYSIS{analysis_suffix}.json')
    expected = frozen['thinking'] if config == 'thinking' else frozen
    selection = {(r['context'], r['arm']): r for r in seal['rows'] if r['rule'] == 'S3'}
    assert len(selection) == 120
    parent_ids = sorted({j['context'] for j in manifest['jobs']})
    parents = {cid: read(root / 'holdout' / f'{cid}.json') for cid in parent_ids}
    children = {j['id']: read(root / 'holdout' / (j['id'] + '.json')) for j in manifest['jobs']}
    jobs = defaultdict(list)
    for j in manifest['jobs']:
        jobs[(j['context'], j['arm'])].append(j)
    pool_rows = []
    for (context, arm), jj in sorted(jobs.items()):
        jj.sort(key=lambda j: j['draw'])
        assert len(jj) == 2
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
        for child in child_rows:
            candidate_path = root / 'candidates' / (child['id'] + '.json')
            # The frozen seal hashes read_text (universal newlines), not file bytes.
            assert seal['candidate_hashes'][child['id']] == sha256(candidate_path.read_text(encoding='utf-8').encode()).hexdigest()
    summaries = {}
    for mode in ('controlled', 'natural'):
        for arm in (*ARMS, 'pooled'):
            subset = [r for r in pool_rows if arm == 'pooled' or r['arm'] == arm]
            for metric in METRICS:
                key = f'{mode}/{arm}/{metric}'
                ss = {stage: summarize([mean(r['behavior'][mode][stage][metric] for r in subset if r['seed'] == s)
                                      for s in SEEDS]) for stage in STAGES}
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
    # Verify mean aggregation and adoption against the released analysis for every arm.
    for arm in ARMS:
        subset = [r for r in pool_rows if r['arm'] == arm]
        for stage, ref in [('raw', expected['raw'][arm]['metrics']['default/score']),
                           ('S3', expected['selected']['S3/' + arm]['metrics']['default'])]:
            values = [mean(r['H_score'][stage] - r['H_score']['parent'] for r in subset if r['seed'] == s) for s in SEEDS]
            assert np.allclose(values, ref['seed_values'], atol=1e-12, rtol=0), (config, arm, stage)
        for mode in ('controlled', 'natural'):
            for metric, oldmetric in [('defection_exposure', 'sustained_unilateral_cooperation_last5'),
                                     ('recovery_rounds', 'recovery_time_capped'),
                                     ('not_recovered', 'not_recovered'),
                                     ('mutual_cooperation', 'mutual_cooperation_last5')]:
                values = summaries[f'{mode}/{arm}/{metric}']['raw_minus_parent']['seed_values']
                ref = expected['raw'][arm]['behavior'][mode + '/' + oldmetric]['seed_values']
                assert np.allclose(values, ref, atol=1e-12, rtol=0), (config, arm, mode, metric)
    return {'summaries': summaries, 'matched_contrasts': contrasts, 'pool_rows': pool_rows,
            'n_seeds': len(SEEDS), 'n_parents': len(parents), 'n_slots': len(children),
            'S3_accepted': sum(r['winner'] is not None for r in pool_rows),
            'behavior_fallbacks': sum(c['fallback']['behavior'] for c in children.values()),
            'validation': 'All raw behaviour and raw/S3 payoff seed means match released results.'}


def main():
    global REPO
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, default=REPO)
    parser.add_argument('--analysis-suffix', default='')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    REPO = args.work.resolve()
    output = args.output or REPO / 'results/reciprocity_population_visuals_20260924/behavior/ANALYSIS.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    data = {config: analyze(config, REPO / root, args.analysis_suffix) for config, root in ROOTS.items()}
    for mode in ('controlled', 'natural'):
        for metric in METRICS:
            key = f'{mode}/pooled/{metric}'
            assert data['non_thinking']['summaries'][key]['parent'] == data['thinking']['summaries'][key]['parent']
    report = {'status': 'complete', 'analysis_status': 'post_hoc_exploratory',
              'seeds': SEEDS, 'independent_units': 20, 'arms': list(ARMS),
              'stage_definition': {'parent': '3 shared parents per population',
                                   'raw': '12 candidates per population across 2 report conditions',
                                   'S3': '6 sealed candidate-pool decisions per population'},
              'no_new_games_or_model_calls': True,
              'configs': data, 'input_sha256': INPUT_HASHES,
              'analysis_script_sha256': sha256(Path(__file__).read_bytes()).hexdigest()}
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print('Recomputed independent behaviour for two report conditions')


if __name__ == '__main__':
    main()
