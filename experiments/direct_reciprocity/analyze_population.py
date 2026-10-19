"""Descriptive population evidence from sealed records, with no new games/API calls.

Candidate distributions describe every recorded matching-condition output.
Population panels average draws, parents and arms within the manifest's seed clusters.
This is an exploratory visualization, not an extra family of significance tests.
"""
from pathlib import Path
import argparse
import json

ROOT = Path(__file__).resolve().parents[2]
import numpy as np

RUNS = {'Thinking OFF': 'feedback_specificity_v2',
        'Thinking ON': 'feedback_specificity_thinking_384k_20260923'}
ARMS = ('accurate', 'mismatched')
def read(path):
    return json.loads(path.read_text(encoding='utf-8'))

def count_quality(rows):
    values = [r['delta']['default']['score'] for r in rows if r['valid']]
    return {'better': sum(v > 1e-12 for v in values),
            'worse': sum(v < -1e-12 for v in values),
            'equal_valid': sum(abs(v) <= 1e-12 for v in values),
            'invalid': sum(not r['valid'] for r in rows)}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, default=ROOT)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    work = args.work.resolve()
    destination = args.output or work / 'results/reciprocity_population_visuals_20260924/population_summary.json'
    destination.parent.mkdir(parents=True, exist_ok=True)
    data = {}
    for label, run in RUNS.items():
        path = work / 'results' / run
        manifest = read(path / 'manifest.json')
        seeds = manifest['seeds']
        candidates = [read(path / 'candidates' / (job['id'] + '.json'))
                      for job in sorted(manifest['jobs'], key=lambda j: j['id']) if job['arm'] in ARMS]
        rows = [read(path/'holdout'/f'{c["id"]}.json') for c in candidates]
        if not rows or set(r['seed'] for r in rows) != set(seeds):
            raise ValueError('Population summaries require records for every population seed')
        byid = {r['id']: r for r in rows}
        sealed = [s for s in read(path/'SELECTIONS_SEALED.json')['rows'] if s['rule'] == 'S3' and s['arm'] in ARMS]
        pools = {(row['context'], row['arm']) for row in rows}
        if {(row['context'], row['arm']) for row in sealed} != pools or len(sealed) != len(pools):
            raise ValueError('Population summaries require one S3 decision per candidate pool')
        chosen = [{'seed': s['seed'], 'arm': s['arm'], 'accepted': s['accepted'],
                   'context': s['context'], 'winner': s['winner'],
                   'gain': byid[s['winner']]['delta']['default']['score'] if s['accepted'] else 0.0}
                  for s in sealed]
        raw = [float(np.mean([r['delta']['default']['score'] for r in rows if r['seed'] == s])) for s in seeds]
        selected = [float(np.mean([r['gain'] for r in chosen if r['seed'] == s])) for s in seeds]
        contrast = [float(np.mean([r['delta']['default']['score'] for r in rows if r['seed']==s and r['arm']=='accurate'])
                         - np.mean([r['delta']['default']['score'] for r in rows if r['seed']==s and r['arm']=='mismatched']))
                    for s in seeds]
        data[label] = {'n': len(rows), 'n_pools': len(pools), 'mode': label.split()[-1].lower(),
                       'quality': count_quality(rows), 'seed_ids': seeds,
                       'all_raw_gains': [r['delta']['default']['score'] for r in rows],
                       'raw_seed_means': raw, 's3_seed_means': selected, 'accurate_minus_mismatched': contrast,
                       'mean_raw': float(np.mean(raw)), 'mean_s3': float(np.mean(selected)),
                       's3_accepted': sum(c['accepted'] for c in chosen),
                       's3_accepted_test_worse': sum(c['accepted'] and c['gain'] < -1e-12 for c in chosen),
                       's3_accepted_test_equal': sum(c['accepted'] and abs(c['gain']) <= 1e-12 for c in chosen),
                       's3_accepted_test_better': sum(c['accepted'] and c['gain'] > 1e-12 for c in chosen),
                       's3_retained_parent': sum(not c['accepted'] for c in chosen),
                       'per_arm_quality': {a: count_quality([r for r in rows if r['arm']==a]) for a in ARMS}}

    report = {'configurations': data, 'new_games': 0, 'new_model_calls': 0}
    destination.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(f'Recomputed distributions and decisions for {sum(row["n"] for row in data.values())} candidates')


if __name__ == '__main__':
    main()
