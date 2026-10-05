"""Seed-cluster summaries and a structural audit of feedback interventions."""
import argparse
from itertools import product
from pathlib import Path
import random
from statistics import mean

from .core import Config, Policy, digest
from .feedback import ARMS, MIXTURES, feedback_prompt
from .run import read_json, write_json


def interval(values):
    rng = random.Random(91826)
    n = len(values)
    if not n:
        return None
    samples = sorted(mean(rng.choices(values, k=n)) for _ in range(20000))
    return [samples[int(0.025 * len(samples))], samples[int(0.975 * len(samples))]]


def sign_flip_p(values):
    if not values:
        return None
    observed = abs(mean(values))
    permuted = [abs(mean(s * v for s, v in zip(signs, values)))
                for signs in product((-1, 1), repeat=len(values))]
    return sum(v >= observed - 1e-12 for v in permuted) / len(permuted)


def metric(row, name):
    setting, field = name.split('/', 1)
    if field.startswith('mixture:'):
        return row['delta'][setting]['mixtures'][field.split(':')[1]]
    return row['delta'][setting][field]


def analyze(root):
    root = Path(root)
    manifest = read_json(root / 'manifest.json')
    issues, missing, outcomes = [], [], []
    records = []
    for job in manifest['jobs']:
        path = root / 'outcomes' / (job['id'] + '.json')
        request = root / 'requests' / (job['id'] + '.json')
        if not path.exists():
            missing.append(job['id'])
            continue
        row = read_json(path)
        outcomes.append(row)
        if not request.exists():
            issues.append(job['id'] + ': missing request')
            continue
        record = read_json(request)
        records.append(record)
        c = read_json(root / 'contexts' / (job['context'] + '.json'))
        population = [Policy(**p) for p in c['population']]
        expected = feedback_prompt(Config(**c['cfg']), population, c['slot'], c['assessment'],
                                   job['arm'], job['mapping'], c['diagnostic'])
        if record['prompt'] != expected:
            issues.append(job['id'] + ': prompt mismatch')
        if row['parent_key'] != c['parent_key']:
            issues.append(job['id'] + ': wrong parent')
        if any(i == j for i, j in enumerate(job['mapping'])):
            issues.append(job['id'] + ': shuffle fixed point')
        if row['valid'] != (record['status'] == 'valid'):
            issues.append(job['id'] + ': validity mismatch')
        parent = read_json(root / 'parents' / (job['context'] + '.json'))
        for setting in row['delta']:
            expected_delta = row['deployed'][setting]['score'] - parent[setting]['score']
            if abs(expected_delta - row['delta'][setting]['score']) > 1e-10:
                issues.append(job['id'] + ': incorrect delta')
            if row['fallback'][setting] and row['delta'][setting]['score'] != 0:
                issues.append(job['id'] + ': fallback changed parent score')
    metrics = ['training/score', 'default/score', 'noise01/score', 'long/score', 'default/cooperation']
    metrics += ['default/mixture:' + m for m in MIXTURES]
    summaries = {}
    for arm in ARMS:
        rows = [r for r in outcomes if r['arm'] == arm]
        summaries[arm] = {'n': len(rows), 'valid': sum(r['valid'] for r in rows),
                          'fallback': {s: sum(r['fallback'][s] for r in rows)
                                       for s in ('training', 'default', 'noise01', 'long')},
                          'unchanged_source': sum(r['child'] is not None and Policy(**r['child']).key == r['parent_key'] for r in rows),
                          'metrics': {}}
        for name in metrics:
            seed_means = {str(seed): mean(metric(r, name) for r in rows if r['seed'] == seed)
                          for seed in range(5) if sum(r['seed'] == seed for r in rows) == 6}
            setting = name.split('/')[0]
            successful = [r for r in rows if not r['fallback'][setting]]
            summaries[arm]['metrics'][name] = {
                'seed_means': seed_means, 'mean': mean(seed_means.values()) if seed_means else None,
                'ci95': interval(list(seed_means.values())),
                'successful_only_mean': mean(metric(r, name) for r in successful) if successful else None,
                'successful_n': len(successful)}
    comparisons = []
    for left, right in [('true', 'shuffled'), ('true', 'hidden'), ('diagnostic', 'true')]:
        for name in metrics:
            a, b = summaries[left]['metrics'][name]['seed_means'], summaries[right]['metrics'][name]['seed_means']
            values = [a[s] - b[s] for s in sorted(a.keys() & b.keys())]
            comparisons.append({'comparison': left + '-' + right, 'metric': name, 'n_seeds': len(values),
                                'seed_differences': values, 'mean': mean(values) if values else None,
                                'ci95': interval(values), 'exact_sign_flip_p': sign_flip_p(values)})
    budget = {}
    for arm in ARMS:
        arm_records = [read_json(root / 'requests' / (j['id'] + '.json')) for j in manifest['jobs']
                       if j['arm'] == arm and (root / 'requests' / (j['id'] + '.json')).exists()]
        budget[arm] = {'requests': len(arm_records),
                       'status_counts': {s: sum(r['status'] == s for r in arm_records)
                                         for s in ('valid', 'invalid', 'api_error', 'requested')},
                       'total_tokens': sum((r.get('usage') or {}).get('total_tokens', 0) for r in arm_records),
                       'unknown_usage': sum(r.get('usage') is None for r in arm_records)}
    audit = {'issues': issues, 'missing': missing, 'complete': not issues and not missing,
             'outcomes': len(outcomes), 'expected': manifest['total_requests'],
             'changed_score_slots': sorted(set(j['changed_score_slots'] for j in manifest['jobs'])),
             'scope': 'structural and prompt audit, not full independent replay'}
    result = {'audit': audit, 'arms': summaries, 'comparisons': comparisons, 'budget': budget,
              'note': 'All intervals exploratory; five seed clusters; no equivalence claim or multiplicity correction.'}
    write_json(root / 'ANALYSIS.json', result)
    lines = ['# Feedback attribution: one-step results', '', f'Complete: {audit["complete"]}; {len(outcomes)}/120 outcomes; {len(issues)} audit issues.', '',
             '| Arm | Valid / total | Default fallback | Default score gain | Training gain | Tokens |',
             '| --- | ---: | ---: | ---: | ---: | ---: |']
    def fmt(value):
        return 'unavailable' if value is None else f'{value:+.5f}'
    for arm, s in summaries.items():
        lines.append(f'| {arm} | {s["valid"]}/{s["n"]} | {s["fallback"]["default"]} | {fmt(s["metrics"]["default/score"]["mean"])} | {fmt(s["metrics"]["training/score"]["mean"])} | {budget[arm]["total_tokens"]:,} |')
    lines += ['', '| Contrast | Metric | Mean difference | Bootstrap 95% | Exact paired sign-flip p |',
              '| --- | --- | ---: | --- | ---: |']
    for c in comparisons:
        ci = c['ci95']
        lines.append(f'| {c["comparison"]} | {c["metric"]} | {fmt(c["mean"])} | {str(ci)} | {c["exact_sign_flip_p"]} |')
    lines += ['', 'Score gains are offspring minus the same parent on fixed tests, with failed offspring retaining the parent.',
              'Unit of inference is the initialization seed, not candidate or match. Bootstrap intervals are exploratory.',
              'Matching requests does not match tokens. Diagnostic probes add 600 parent decisions per context (9,000 unique decisions).',
              'Mixtures reweight fixed opponent payoffs; they are not ecological evolution.',
              'Raw seed differences, successful-only summaries and all failures are in ANALYSIS.json.']
    (root / 'REPORT.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print({'complete': audit['complete'], 'outcomes': len(outcomes), 'issues': issues, 'missing': len(missing)})
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', nargs='?', default='results/feedback_attribution_v1')
    analyze(parser.parse_args().root)
