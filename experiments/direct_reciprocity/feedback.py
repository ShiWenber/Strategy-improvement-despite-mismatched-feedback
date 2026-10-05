"""Frozen, paired one-step feedback interventions; no holdout-driven selection."""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, replace
import json
from pathlib import Path
import random
from statistics import mean

from .core import Config, Policy, RandomView, act, digest, ranking, seed_for, versus
from .baselines import TRAIN, TEST, policy
from .control import hypothetical_fitness
from .diagnostics import implementation_hash
from .prompts import build_prompt
from .run import Generator, read_json, write_json

ARMS = ('true', 'shuffled', 'hidden', 'diagnostic')
PARENT_RANKS = (0, 2, 5)
TRANSFER = [
    policy('Forgiving05', "return 'C' if not history or history[-1][1]=='C' or rng.random()<0.05 else 'D'"),
    policy('Forgiving25', "return 'C' if not history or history[-1][1]=='C' or rng.random()<0.25 else 'D'"),
    policy('RetaliateWindow2', "return 'D' if any(y=='D' for x,y in history[-2:]) else 'C'"),
    policy('RetaliateWindow5', "return 'D' if any(y=='D' for x,y in history[-5:]) else 'C'"),
    policy('Random35', "return 'C' if rng.random()<0.35 else 'D'"),
    policy('Random65', "return 'C' if rng.random()<0.65 else 'D'"),
    policy('MemoryOneA', "p = {('C','C'):0.9,('C','D'):0.05,('D','C'):0.8,('D','D'):0.05}\nreturn 'C' if not history or rng.random()<p[history[-1]] else 'D'"),
    policy('MemoryOneB', "p = {('C','C'):0.7,('C','D'):0.15,('D','C'):0.6,('D','D'):0.1}\nreturn 'C' if not history or rng.random()<p[history[-1]] else 'D'"),
]
# Equal within a family. Mixtures are payoff reweightings, not population simulations.
MIXTURES = {
    'forgiving': [0.30, 0.30, 0.05, 0.05, 0.075, 0.075, 0.075, 0.075],
    'retaliatory': [0.05, 0.05, 0.30, 0.30, 0.075, 0.075, 0.075, 0.075],
    'exploitative': [0.05, 0.05, 0.075, 0.075, 0.075, 0.075, 0.30, 0.30],
}


def source_hash():
    own = Path(__file__).read_text(encoding='utf-8')
    control = Path(__file__).with_name('control.py').read_text(encoding='utf-8')
    return digest(implementation_hash() + own + control)


def derangement(n, seed):
    if n < 2:
        raise ValueError('Derangement requires at least two slots')
    rng = random.Random(seed)
    order = list(range(n))
    while True:
        rng.shuffle(order)
        if all(i != j for i, j in enumerate(order)):
            return order


def score_table(population, assessment, arm, mapping):
    if arm == 'hidden':
        return None
    return [{'slot': i, 'fitness': round(assessment[mapping[i] if arm == 'shuffled' else i]['fitness'], 6)}
            for i in range(len(population))]


def feedback_prompt(cfg, population, parent_slot, assessment, arm, mapping, diagnostic=None):
    if arm not in ARMS:
        raise ValueError(arm)
    text = build_prompt(replace(cfg, prompt='minimal'), population[parent_slot])
    text += '\nPARENT SLOT: ' + str(parent_slot)
    text += '\nPOPULATION SOURCE (original slot order):\n' + json.dumps(
        [{'slot': i, 'code': p.code} for i, p in enumerate(population)], sort_keys=True)
    table = score_table(population, assessment, arm, mapping)
    if table is not None:
        text += '\nCUMULATIVE TRAINING FITNESS:\n' + json.dumps(table, sort_keys=True)
    if arm == 'diagnostic':
        if diagnostic is None:
            raise ValueError('Missing behavioral diagnostics')
        text += ('\nCONTROLLED PARENT BEHAVIOR: Each probe starts with ten externally supplied CC rounds. '
                 'Then the opponent defects for one or four rounds, and either copies your previous action '
                 'or returns to unconditional cooperation, as labeled. These are diagnostic histories, '
                 'not necessarily naturally reached histories. Numbers average ten independent streams. '
                 'Consider which behavior to retain or modify to maximize tournament fitness.\n')
        text += json.dumps(diagnostic, sort_keys=True)
    return text + '\nReturn only the new strategy source.\n'


def behavior_diagnostics(parent, cfg):
    """600 parent decisions; forced history is distinguished from natural play."""
    results = {}
    for label, defect_rounds, restore in [('one_D_then_TFT', 1, 'TFT'),
                                           ('four_D_then_TFT', 4, 'TFT'),
                                           ('four_D_then_ALLC', 4, 'ALLC')]:
        runs = []
        for repeat in range(10):
            rng = RandomView(seed_for('feedback-probe-v1', cfg.seed, label, repeat))
            fn = parent.compile(rng)
            history = [('C', 'C')] * 10
            actions = []
            for t in range(20):
                x = act(fn, history, rng)
                y = 'D' if t < defect_rounds else ('C' if restore == 'ALLC' else history[-1][0])
                history.append((x, y))
                actions.append((x, y))
            runs.append({'cooperation_first4': mean(x == 'C' for x, _ in actions[:4]),
                         'cooperation_after4': mean(x == 'C' for x, _ in actions[4:]),
                         'mutual_cooperation_last5': mean(x == y == 'C' for x, y in actions[-5:])})
        results[label] = {k: mean(r[k] for r in runs) for k in runs[0]}
    return results


def measure(candidate, population, slot, cfg):
    out = {}
    try:
        out['training'] = {'score': hypothetical_fitness(candidate, slot, population, TRAIN, cfg, 0) / cfg.rounds,
                           'status': 'ok'}
    except Exception as exc:
        out['training'] = {'status': 'failed', 'error_type': type(exc).__name__}
    for label, rounds, noise in [('default', 100, 0), ('noise01', 100, 0.01), ('long', 200, 0)]:
        try:
            result = versus(candidate, TRANSFER, replace(cfg, rounds=rounds, noise=noise), 'feedback-transfer-' + label)
            result.update(status='ok', rounds=rounds)
            result['score'] /= rounds
            result['worst_score'] /= rounds
            result['mixtures'] = {name: sum(w * row['score'] / rounds for w, row in zip(weights, result['opponents']))
                                  for name, weights in MIXTURES.items()}
            out[label] = result
        except Exception as exc:
            out[label] = {'status': 'failed', 'error_type': type(exc).__name__, 'rounds': rounds}
    return out


def prepare(source, root):
    source, root = Path(source), Path(root)
    path = root / 'manifest.json'
    if path.exists():
        manifest = read_json(path)
        if manifest['implementation_hash'] != source_hash():
            raise RuntimeError('Frozen implementation changed')
        return manifest
    old_keys = {p.key for p in TRAIN + TEST}
    assert not old_keys.intersection(p.key for p in TRANSFER)
    contexts, jobs = [], []
    for seed in range(5):
        reference = source / f'minimal__paper_truncation__seed{seed}'
        metadata = read_json(reference / 'config.json')
        state = read_json(reference / 'generation_000.json')
        cfg = Config(**metadata['config'])
        if metadata['implementation_hash'] != implementation_hash():
            raise RuntimeError('Original engine changed')
        population = [Policy(**p) for p in state['population']]
        order = ranking(population, state['assessment'])
        for rank in PARENT_RANKS:
            slot = order[rank]
            parent = population[slot]
            context_id = f'seed{seed}-rank{rank+1}'
            context = {'id': context_id, 'seed': seed, 'rank': rank + 1, 'slot': slot,
                       'cfg': asdict(cfg), 'population': state['population'], 'assessment': state['assessment'],
                       'source_generation_hash': digest((reference / 'generation_000.json').read_text(encoding='utf-8')),
                       'provider': metadata['provider'], 'model': metadata['model'],
                       'parent_key': parent.key, 'diagnostic': behavior_diagnostics(parent, cfg),
                       'diagnostic_parent_decisions': 600}
            write_json(root / 'contexts' / (context_id + '.json'), context)
            contexts.append(context_id)
            for draw in range(2):
                mapping = derangement(len(population), seed_for('feedback-shuffle-v1', seed, draw))
                true = score_table(population, state['assessment'], 'true', mapping)
                shuffled = score_table(population, state['assessment'], 'shuffled', mapping)
                for arm in ARMS:
                    jobs.append({'id': f'{context_id}-draw{draw}-{arm}', 'context': context_id,
                                 'seed': seed, 'rank': rank + 1, 'draw': draw, 'arm': arm, 'mapping': mapping,
                                 'changed_score_slots': sum(a['fitness'] != b['fitness'] for a, b in zip(true, shuffled))})
    random.Random(18437).shuffle(jobs)
    manifest = {'version': 'feedback-one-step-v1', 'implementation_hash': source_hash(),
                'source': str(source.resolve()), 'arms': list(ARMS), 'contexts': contexts,
                'jobs': jobs, 'total_requests': len(jobs), 'transfer': [asdict(p) for p in TRANSFER],
                'mixtures': MIXTURES, 'primary': 'seed_cluster_mean_offspring_minus_parent_default_score_true_minus_shuffled',
                'fallback': 'invalid_or_test_failure_retains_parent; API errors remain missing',
                'draft_sha256_before_generation': digest((Path('docs/direct_reciprocity/FEEDBACK_ATTRIBUTION_DRAFT.md')).read_text(encoding='utf-8'))}
    write_json(path, manifest)
    return manifest


def parent_job(arguments):
    root, context_id = arguments
    root = Path(root)
    output = root / 'parents' / (context_id + '.json')
    if output.exists():
        return context_id
    c = read_json(root / 'contexts' / (context_id + '.json'))
    population = [Policy(**p) for p in c['population']]
    result = measure(population[c['slot']], population, c['slot'], Config(**c['cfg']))
    if any(v['status'] != 'ok' for v in result.values()):
        raise RuntimeError('Parent measurement failed: ' + context_id)
    write_json(output, result)
    return context_id


def candidate_job(arguments):
    root, job, env_file = arguments
    if env_file:
        from dotenv import load_dotenv
        load_dotenv(env_file, override=False)
    root = Path(root)
    output = root / 'outcomes' / (job['id'] + '.json')
    if output.exists():
        return {'id': job['id'], 'status': 'cached'}
    c = read_json(root / 'contexts' / (job['context'] + '.json'))
    population = [Policy(**p) for p in c['population']]
    cfg = Config(**c['cfg'])
    prompt = feedback_prompt(cfg, population, c['slot'], c['assessment'], job['arm'], job['mapping'], c['diagnostic'])
    generator = Generator(root / 'requests', c['provider'], c['model'], cfg.temperature)
    child = generator.generate(job['id'], prompt, cfg)
    parent_result = read_json(root / 'parents' / (job['context'] + '.json'))
    measurements = measure(child, population, c['slot'], cfg) if child else {}
    result = {**job, 'parent_key': c['parent_key'], 'child': asdict(child) if child else None,
              'valid': child is not None, 'measurements': measurements, 'deployed': {}, 'delta': {}, 'fallback': {}}
    for setting, baseline in parent_result.items():
        measured = measurements.get(setting, {'status': 'invalid'})
        fallback = measured['status'] != 'ok'
        deployed = baseline if fallback else measured
        result['fallback'][setting] = fallback
        result['deployed'][setting] = deployed
        result['delta'][setting] = {'score': deployed['score'] - baseline['score']}
        if setting != 'training':
            result['delta'][setting]['cooperation'] = deployed['cooperation'] - baseline['cooperation']
            result['delta'][setting]['mixtures'] = {k: deployed['mixtures'][k] - baseline['mixtures'][k] for k in MIXTURES}
    write_json(output, result)
    return {'id': job['id'], 'valid': child is not None, 'default_delta': result['delta']['default']['score']}


def run_pool(fn, arguments, workers):
    errors = []
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fn, arg): arg for arg in arguments}
        for future in as_completed(futures):
            try:
                print(json.dumps(future.result(), ensure_ascii=False), flush=True)
            except Exception as exc:
                errors.append({'argument': str(futures[future]), 'type': type(exc).__name__, 'message': str(exc)})
                print(json.dumps({'error': type(exc).__name__, 'message': str(exc)}), flush=True)
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', default='results/direct_reciprocity_main_v2')
    parser.add_argument('--output', default='results/feedback_attribution_v1')
    parser.add_argument('--env-file', default='../../.env')
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--prepare-only', action='store_true')
    args = parser.parse_args()
    if args.workers < 1:
        parser.error('workers must be positive')
    root = Path(args.output)
    manifest = prepare(args.source, root)
    if args.prepare_only:
        print(json.dumps({'prepared_requests': len(manifest['jobs']), 'implementation_hash': source_hash()}))
        return
    errors = run_pool(parent_job, [(str(root), cid) for cid in manifest['contexts']], args.workers)
    if errors:
        write_json(root / 'parent_errors.json', errors)
        raise RuntimeError('Parent evaluation incomplete')
    errors = run_pool(candidate_job, [(str(root), job, args.env_file) for job in manifest['jobs']], args.workers)
    write_json(root / 'run_status.json', {'complete': not errors, 'errors': errors,
                                         'expected': len(manifest['jobs']),
                                         'observed': len(list((root / 'outcomes').glob('*.json')))})
    if errors:
        raise RuntimeError('Some candidate requests need attention; see run_status.json')


if __name__ == '__main__':
    main()
