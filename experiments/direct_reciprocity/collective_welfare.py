"""Local, fixed-code collective-welfare experiment. No model or network calls."""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed, TimeoutError
from dataclasses import asdict
from itertools import combinations_with_replacement
import json
import os
from pathlib import Path
import random
import time

from .core import Config, Policy, RandomView, act, match, seed_for
from .baselines import TRAIN

ROOT = Path('results/collective_welfare_20260927')
ARMS = ['score', 'accurate', 'mismatched', 'background', 'cooperation']
SOURCES = {'OFF': Path('results/feedback_specificity_v2'),
           'ON': Path('results/feedback_specificity_thinking_384k_20260923')}
CFG = Config(rounds=100, repeats=5)


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(path)


def observed_match(a, b, cfg, seed):
    """Mirror core.match, adding actor-specific errors and joint cooperation."""
    rngs = [RandomView(seed_for(seed, 'left')), RandomView(seed_for(seed, 'right'))]
    fns = []
    for k, policy in enumerate((a, b)):
        try:
            fns.append(policy.compile(rngs[k]))
        except Exception as exc:
            return {'failed_side': k, 'error': type(exc).__name__ + ': ' + str(exc)[:180]}
    noise = [random.Random(seed_for(seed, 'noise-left')),
             random.Random(seed_for(seed, 'noise-right'))]
    histories = [[], []]
    scores, coop, joint = [0., 0.], [0, 0], 0
    payoffs = {('C', 'C'): (cfg.reward, cfg.reward), ('C', 'D'): (cfg.sucker, cfg.temptation),
               ('D', 'C'): (cfg.temptation, cfg.sucker), ('D', 'D'): (cfg.punishment, cfg.punishment)}
    for _ in range(cfg.rounds):
        actions = []
        for k in range(2):
            try:
                actions.append(act(fns[k], histories[k], rngs[k]))
            except Exception as exc:
                return {'failed_side': k, 'error': type(exc).__name__ + ': ' + str(exc)[:180]}
        for k in range(2):
            if noise[k].random() < cfg.noise:
                actions[k] = 'D' if actions[k] == 'C' else 'C'
        x, y = actions
        rewards = payoffs[x, y]
        for k in range(2):
            scores[k] += rewards[k]
            coop[k] += actions[k] == 'C'
        joint += x == y == 'C'
        histories[0].append((x, y)); histories[1].append((y, x))
    return {'scores': scores, 'cooperation': [v / cfg.rounds for v in coop],
            'joint_cooperation': joint / cfg.rounds}


def prepare(root=ROOT):
    if (root / 'manifest.json').exists():
        raise RuntimeError('Experiment manifest already exists; use pairs to resume stored jobs.')
    specifications = []
    for seed in range(200, 220):
        base = read(SOURCES['OFF'] / 'populations' / f's{seed}.json')
        codes, code_map, entities = [], {}, {}
        def register(identity, policy, parent=None):
            code = policy['code']
            if code not in code_map:
                code_map[code] = len(codes); codes.append(policy)
            entities[identity] = {'code_index': code_map[code], 'parent': parent}
            return identity
        register('fallback_alld', asdict(TRAIN[1]))
        initial = [register(f'p{i}', policy, 'fallback_alld')
                   for i, policy in enumerate(base['population'])]
        groups, pairs = [], set()
        for mode, source in SOURCES.items():
            other = read(source / 'populations' / f's{seed}.json')
            assert other['population'] == base['population']
            manifest = read(source / 'manifest.json')
            sealed = read(source / 'SELECTIONS_SEALED.json')['rows']
            for arm in ARMS:
                children, selected = {}, {}
                for rank in (1, 3, 6):
                    slot = base['selected_slots'][str(rank)]
                    jobs = sorted([j for j in manifest['jobs'] if j['seed'] == seed
                                   and j['rank'] == rank and j['arm'] == arm], key=lambda j: j['draw'])
                    children[str(slot)] = []
                    for job in jobs:
                        child = read(source / 'candidates' / (job['id'] + '.json'))
                        identity = mode + ':' + job['id']
                        register(identity, child['child'] if child['valid'] else base['population'][slot], f'p{slot}')
                        entities[identity]['generation_valid'] = child['valid']
                        children[str(slot)].append(identity)
                    for rule in ('S1', 'S2', 'S3'):
                        row = next(r for r in sealed if r['context'] == f's{seed}-rank{rank}'
                                   and r['arm'] == arm and r['rule'] == rule)
                        selected.setdefault(rule, {})[str(slot)] = mode + ':' + row['winner'] if row['winner'] else f'p{slot}'
                local = initial + [i for ids in children.values() for i in ids]
                idx = sorted({entities[i]['code_index'] for i in local})
                pairs.update(combinations_with_replacement(idx, 2))
                groups.append({'mode': mode, 'arm': arm, 'local_entities': local,
                               'children': children, 'selected': selected})
        # Any test-specific failing initial strategy can fall back consistently.
        fallback = entities['fallback_alld']['code_index']
        pairs.update(tuple(sorted((fallback, i))) for i in range(len(codes)))
        specifications.append({'seed': seed, 'codes': codes, 'entities': entities,
                               'initial': initial, 'groups': groups, 'pairs': sorted(pairs)})
    data = {'created_at': time.time(), 'config': asdict(CFG), 'arms': ARMS,
            'sources': {k: str(v) for k, v in SOURCES.items()},
            'population_units': 20, 'initial_slots': 240, 'candidate_slots': 1200,
            'dynamics': {'size': 180, 'replicates': 30, 'generations': 2000,
                         'beta': [0, 1, 5], 'mutation': 0.0025, 'record_every': 10},
            'specifications': specifications}
    write(root / 'manifest.json', data)
    print(json.dumps({'prepared': True, 'pairs': sum(len(s['pairs']) for s in specifications),
                      'games_planned': 5 * sum(len(s['pairs']) for s in specifications)}), flush=True)


def pair_job(job):
    root, seed, i, j, left, right = job
    path = Path(root) / 'pairs' / f's{seed}' / f'{i:03d}_{j:03d}.json'
    if path.exists():
        return read(path).get('failures', [])
    result = {'seed': seed, 'i': i, 'j': j, 'games': [], 'failures': []}
    a, b = Policy(**left), Policy(**right)
    for rep in range(CFG.repeats):
        sd = seed_for(seed, 'collective-welfare-new-pairs', i, j, rep)
        flip = random.Random(seed_for(sd, 'orientation')).random() < .5
        game = observed_match(b if flip else a, a if flip else b, CFG, sd)
        if 'failed_side' in game:
            original_side = 1 - game['failed_side'] if flip else game['failed_side']
            result['failures'].append({'code_index': (i, j)[original_side], 'repeat': rep,
                                       'error': game['error']})
            # Deterministic failure isn't retried; remaining repeats of this pair aren't needed.
            break
        if flip:
            game['scores'].reverse(); game['cooperation'].reverse()
        result['games'].append(game)
    write(path, result)
    return result['failures']


def run_pairs(root, workers):
    data = read(root / 'manifest.json')
    jobs = []
    for s in data['specifications']:
        for i, j in s['pairs']:
            if not (root / 'pairs' / f"s{s['seed']}" / f'{i:03d}_{j:03d}.json').exists():
                jobs.append((str(root), s['seed'], i, j, s['codes'][i], s['codes'][j]))
    start = time.monotonic(); errors = 0
    print(json.dumps({'phase': 'pairs', 'pending': len(jobs), 'workers': workers}), flush=True)
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(pair_job, j) for j in jobs]
        try:
            for count, future in enumerate(as_completed(futures, timeout=2700), 1):
                errors += len(future.result())
                if count % 100 == 0 or count == len(jobs):
                    status = {'phase': 'pairs', 'completed': count, 'scheduled': len(jobs),
                              'execution_failures': errors, 'elapsed_seconds': round(time.monotonic()-start, 1)}
                    write(root / 'PROGRESS.json', status); print(json.dumps(status), flush=True)
        except TimeoutError:
            write(root / 'TIMEOUT.json', {'seconds': time.monotonic()-start})
            print('Hard 45-minute time limit reached; terminating experiment workers.', flush=True)
            for process in pool._processes.values():
                process.terminate()
            raise
    write(root / 'PAIRS_COMPLETE.json', {'seconds': time.monotonic()-start, 'jobs': len(jobs)})


def verify_engine():
    cases = []
    for ia, ib, noise in [(0, 0, 0), (0, 1, 0), (1, 1, 0), (2, 2, 0),
                          (2, 5, 0), (5, 8, .01), (9, 10, 0), (11, 12, 0)]:
        cfg = Config(noise=noise)
        for seed in (197, 198):
            original = match(TRAIN[ia], TRAIN[ib], cfg, seed)
            new = observed_match(TRAIN[ia], TRAIN[ib], cfg, seed)
            assert {k: new[k] for k in original} == original
            welfare = sum(new['scores']) / (2 * cfg.rounds)
            cooperation = sum(new['cooperation']) / 2
            assert abs(welfare - (1 + 3 * cooperation - new['joint_cooperation'])) < 1e-10
            cases.append([ia, ib, noise, seed])
    faulty = Policy('faulty', "def strategy(history, rng):\n    return 1\n")
    assert observed_match(TRAIN[0], faulty, Config(), 1)['failed_side'] == 1
    for a, b, score in [(0, 0, [300., 300.]), (0, 1, [0., 500.]), (1, 1, [100., 100.])]:
        assert observed_match(TRAIN[a], TRAIN[b], Config(), 1)['scores'] == score
    return {'exact_engine_comparisons': len(cases), 'payoff_identity': True,
            'known_classical_games': True, 'failure_attribution': True}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('phase', choices=['prepare', 'verify', 'pairs'])
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--workers', type=int, default=24)
    args = parser.parse_args()
    if args.phase == 'prepare':
        prepare(args.root)
    elif args.phase == 'verify':
        result = verify_engine(); write(args.root / 'ENGINE_CHECK.json', result); print(result)
    else:
        run_pairs(args.root, args.workers)


if __name__ == '__main__':
    main()
