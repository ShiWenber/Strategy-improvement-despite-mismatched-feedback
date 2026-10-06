"""Descriptive population evidence from sealed records, with no new games/API calls.

Candidate distributions describe all 240 candidate generation outputs in each configuration.
Population panels average draws, parents and arms within the SAME 20 seed clusters.
This is an exploratory visualization, not an extra family of significance tests.
"""
from pathlib import Path
from hashlib import sha256
import argparse
import json

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'results/reciprocity_population_visuals_20260924'
import numpy as np

RUNS = {'Off / 6k': 'feedback_specificity_v2',
        'On / 384k': 'feedback_specificity_thinking_384k_20260923'}
ARMS = ('accurate', 'mismatched')
SEEDS = list(range(200, 220))
COLORS = ['#0072B2', '#D55E00']
sources = {}

def read(path):
    sources[str(path.relative_to(ROOT)).replace('\\', '/')] = sha256(path.read_bytes()).hexdigest()
    return json.loads(path.read_text(encoding='utf-8'))

def count_quality(rows):
    values = [r['delta']['default']['score'] for r in rows if r['valid']]
    return {'better': sum(v > 1e-12 for v in values),
            'worse': sum(v < -1e-12 for v in values),
            'equal_valid': sum(abs(v) <= 1e-12 for v in values),
            'invalid': sum(not r['valid'] for r in rows)}

def main():
    global ROOT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, default=ROOT)
    parser.add_argument('--analysis-suffix', default='')
    parser.add_argument('--run-root', type=Path, help='Analyze one OFF experiment instead of the paper configurations.')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    ROOT = args.work.resolve()
    destination = args.output or ROOT / 'results/reciprocity_population_visuals_20260924/population_summary.json'
    destination.parent.mkdir(parents=True, exist_ok=True)
    data = {}
    runs = {'Off / 6k': args.run_root.resolve()} if args.run_root else {label: ROOT / 'results' / run for label, run in RUNS.items()}
    for label, path in runs.items():
        manifest = read(path / 'manifest.json')
        seeds = sorted(manifest['seeds'])
        candidates = [read(path / 'candidates' / (job['id'] + '.json')) for job in manifest['jobs']]
        rows = [read(path/'holdout'/f'{c["id"]}.json') for c in candidates]
        assert len(rows) == len(manifest['jobs']) and sorted(set(r['seed'] for r in rows)) == seeds
        byid = {r['id']: r for r in rows}
        sealed = [s for s in read(path/'SELECTIONS_SEALED.json')['rows'] if s['rule'] == 'S3']
        assert len(sealed) == len(seeds) * len(manifest['ranks']) * len(ARMS)
        chosen = [{'seed': s['seed'], 'arm': s['arm'], 'accepted': s['accepted'],
                   'context': s['context'], 'winner': s['winner'],
                   'gain': byid[s['winner']]['delta']['default']['score'] if s['accepted'] else 0.0}
                  for s in sealed]
        assert all(sum(r['seed'] == s for r in rows) == len(manifest['ranks']) * len(ARMS) * manifest['draws'] for s in seeds)
        raw = [float(np.mean([r['delta']['default']['score'] for r in rows if r['seed'] == s])) for s in seeds]
        selected = [float(np.mean([r['gain'] for r in chosen if r['seed'] == s])) for s in seeds]
        contrast = [float(np.mean([r['delta']['default']['score'] for r in rows if r['seed']==s and r['arm']=='accurate'])
                         - np.mean([r['delta']['default']['score'] for r in rows if r['seed']==s and r['arm']=='mismatched']))
                    for s in seeds]
        data[label] = {'n': len(rows), 'quality': count_quality(rows), 'seed_ids': seeds,
                       'all_raw_gains': [r['delta']['default']['score'] for r in rows],
                       'raw_seed_means': raw, 's3_seed_means': selected, 'accurate_minus_mismatched': contrast,
                       'mean_raw': float(np.mean(raw)), 'mean_s3': float(np.mean(selected)),
                       's3_accepted': sum(c['accepted'] for c in chosen),
                       's3_accepted_test_worse': sum(c['accepted'] and c['gain'] < -1e-12 for c in chosen),
                       's3_accepted_test_equal': sum(c['accepted'] and abs(c['gain']) <= 1e-12 for c in chosen),
                       's3_accepted_test_better': sum(c['accepted'] and c['gain'] > 1e-12 for c in chosen),
                       's3_retained_parent': sum(not c['accepted'] for c in chosen),
                       'per_arm_quality': {a: count_quality([r for r in rows if r['arm']==a]) for a in ARMS}}

        # Check the same experiment's released per-population summaries.
        check = read(path / f'ANALYSIS{args.analysis_suffix}.json')
        if label == 'On / 384k':
            check = check['thinking']
        for output, key, metric in [('raw_seed_means','raw','default/score'), ('s3_seed_means','selected','default')]:
            expected = np.mean([check[key][a if key=='raw' else 'S3/'+a]['metrics'][metric]['seed_values'] for a in ARMS],axis=0)
            assert np.allclose(data[label][output], expected, atol=1e-12, rtol=0)

    report = {'configurations': data, 'new_games': 0, 'new_model_calls': 0, 'sources_sha256': sources}
    destination.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(f"Recomputed distributions and decisions for {sum(row['n'] for row in data.values())} candidates")


if __name__ == '__main__':
    main()
