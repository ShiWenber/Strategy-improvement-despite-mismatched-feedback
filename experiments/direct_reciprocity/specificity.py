"""Durable staged v2 experiment: freeze -> initialize -> generate -> select -> H.

No API retries; H is inaccessible through this runner until every selection is
sealed. Each stage is independently resumable and checks frozen source hashes.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, wait, FIRST_COMPLETED
from dataclasses import asdict, replace
import json
from pathlib import Path
import random
from statistics import mean
import time

from .core import Config, Policy, digest, evaluate, match, seed_for, versus
from .baselines import TRAIN
from .diagnostics import implementation_hash
from .report_assignment import derangement
from .prompts import build_prompt
from .run import Generator, read_json, write_json
from .specificity_assets import (ARMS, SEEDS, RANKS, REPEATS, panel, probes,
                                diagnostic_block, tokenizer, assets_record)

DEFAULT_ROOT = 'results/feedback_specificity_v2'
MODULES = ('specificity.py', 'specificity_assets.py', 'specificity_analysis.py')


def source_hash():
    return digest(implementation_hash() + '\n' + '\n'.join(
        name + ':' + digest(Path(__file__).with_name(name).read_text(encoding='utf-8')) for name in MODULES))


def cfg_for(seed):
    return Config(seed=seed)


def init_prompt(seed, slot):
    return build_prompt(cfg_for(seed)) + f'\nIndependent candidate {slot}; replicate {seed}.\n'


def check_manifest(root):
    manifest = read_json(Path(root) / 'manifest.json')
    if manifest['implementation_hash'] != source_hash():
        raise RuntimeError('Frozen v2 implementation changed; do not mix versions')
    return manifest


def freeze(root):
    root = Path(root)
    if (root / 'manifest.json').exists():
        return check_manifest(root)
    init_jobs = [{'id': f'init-s{seed}-slot{slot}', 'seed': seed, 'slot': slot}
                 for seed in SEEDS for slot in range(12)]
    jobs, permutations = [], {}
    for seed in SEEDS:
        # One random arm-to-request-position permutation per independent cluster.
        order = list(ARMS)
        random.Random(seed_for('specificity-arm-assignment', seed)).shuffle(order)
        permutations[str(seed)] = order
        for rank in RANKS:
            for draw in range(2):
                for position, arm in enumerate(order):
                    cid = f's{seed}-rank{rank}'
                    jobs.append({'id': f'{cid}-d{draw}-pos{position}', 'context': cid,
                                 'seed': seed, 'rank': rank, 'draw': draw, 'position': position, 'arm': arm})
    # Shuffle complete parent/draw blocks, preserving randomized positions within blocks.
    blocks = [jobs[i:i + len(ARMS)] for i in range(0, len(jobs), len(ARMS))]
    random.Random(2026091901).shuffle(blocks)
    jobs = [job for block in blocks for job in block]
    random.Random(2026091902).shuffle(init_jobs)
    manifest = {'version': 'specificity-v2', 'implementation_hash': source_hash(),
                'engine_hash': implementation_hash(), 'provider': 'deepseek', 'model': 'deepseek-flash',
                'config': asdict(cfg_for(SEEDS[0])), 'seeds': list(SEEDS), 'arms': list(ARMS),
                'ranks': list(RANKS), 'draws': 2, 'init_jobs': init_jobs, 'jobs': jobs,
                'arm_position_permutations': permutations, 'assets': assets_record(),
                'primary': 'raw_H_default_gain_accurate_minus_mismatched',
                'independent_unit': '20 new initial populations', 'delta': .05,
                'selection_repeats': {'S1': 5, 'S2': 20, 'S3': 20}, 'holdout_repeats': 20,
                'training_selection_generation_namespace': 19001,
                'fallback': 'invalid candidate/setting runtime failure retains parent; API failures remain missing',
                'init_fallback': 'ALLD when generation invalid or feedback probe execution fails; no replacement calls',
                'init_quality_pause_above_invalid': 24,
                'requested_calls': {'initial': len(init_jobs), 'candidates': len(jobs), 'total': len(init_jobs) + len(jobs)},
                'frozen_at': time.time(),
                'inference': 'seed-cluster bootstrap CI; exact cluster sign swaps for arm contrasts under paired exchangeability; parent contrast additionally assumes symmetric cluster effects',
                'length_control': 'cl100k_base +/-5% for Accurate and Mismatched reports; not DeepSeek token equality'}
    write_json(root / 'manifest.json', manifest)
    return manifest


def pool_run(fn, arguments, workers, root, stage, process=False):
    """Bounded dispatch stops issuing tasks on error; active calls finish durably."""
    root = Path(root)
    started = time.time()
    items = iter(arguments)
    done, errors, active = 0, [], {}
    executor_type = ProcessPoolExecutor if process else ThreadPoolExecutor
    with executor_type(max_workers=workers) as executor:
        def submit():
            try:
                item = next(items)
            except StopIteration:
                return False
            active[executor.submit(fn, item)] = item
            return True
        for _ in range(workers):
            if not submit():
                break
        while active:
            ready, _ = wait(active, return_when=FIRST_COMPLETED)
            for future in ready:
                item = active.pop(future)
                try:
                    result = future.result()
                    done += 1
                    print(json.dumps({'stage': stage, 'done': done, 'total': len(arguments), 'result': result}), flush=True)
                except Exception as exc:
                    errors.append({'task': str(item)[:500], 'type': type(exc).__name__, 'message': str(exc)[:1000]})
                write_json(root / 'EXECUTION_STATUS.json', {'stage': stage, 'completed': done,
                           'total': len(arguments), 'errors': errors, 'started_at': started, 'updated_at': time.time()})
            if not errors:
                while len(active) < workers and submit():
                    pass
    if errors:
        write_json(root / (stage + '_errors.json'), errors)
        raise RuntimeError(f'{stage} stopped after errors; no automatic request retries')


def initial_job(arg):
    root, job = arg
    root = Path(root)
    output = root / 'initial' / (job['id'] + '.json')
    if output.exists():
        return {'id': job['id'], 'cached': True}
    cfg = cfg_for(job['seed'])
    gen = Generator(root / 'requests_initial', 'deepseek', 'deepseek-flash', cfg.temperature)
    candidate = gen.generate(job['id'], init_prompt(job['seed'], job['slot']), cfg)
    reason = None
    if candidate is None:
        reason = 'invalid_generation'
    else:
        try:
            probes(candidate, cfg, 'F')
        except Exception as exc:
            reason = 'feedback_probe_' + type(exc).__name__
    selected = candidate if reason is None else Policy(job['id'] + '-fallback', TRAIN[1].code)
    write_json(output, {**job, 'policy': asdict(selected), 'fallback': reason,
                        'generated': asdict(candidate) if candidate else None})
    return {'id': job['id'], 'fallback': reason}


def prepare_seed(arg):
    root, seed = arg
    root = Path(root)
    path = root / 'populations' / f's{seed}.json'
    if path.exists():
        return {'seed': seed, 'cached': True}
    records = [read_json(root / 'initial' / f'init-s{seed}-slot{slot}.json') for slot in range(12)]
    pop = [Policy(**r['policy']) for r in records]
    cfg = cfg_for(seed)
    assessment = evaluate(pop, TRAIN, cfg, 0)
    diagnostics = [probes(p, cfg, 'F') for p in pop]
    order = sorted(range(12), key=lambda slot: (-assessment[slot]['fitness'], slot))
    mapping = derangement(12, seed_for('specificity-diagnostic-mapping', seed))
    write_json(path, {'seed': seed, 'cfg': asdict(cfg), 'population': [asdict(p) for p in pop],
                     'assessment': assessment, 'diagnostics': diagnostics, 'mapping': mapping,
                     'selected_slots': {str(rank): order[rank - 1] for rank in RANKS},
                     'init_fallbacks': sum(r['fallback'] is not None for r in records)})
    return {'seed': seed, 'prepared': True}


def make_prompts(root, manifest):
    root = Path(root)
    enc = tokenizer()
    contexts = {}
    for seed in SEEDS:
        data = read_json(root / 'populations' / f's{seed}.json')
        pop = [Policy(**p) for p in data['population']]
        for rank in RANKS:
            slot = data['selected_slots'][str(rank)]
            donor = data['mapping'][slot]
            correct = diagnostic_block(data['diagnostics'][slot])
            wrong = diagnostic_block(data['diagnostics'][donor])
            count = len(enc.encode(correct))
            blocks = {'accurate': correct, 'mismatched': wrong}
            lengths = {arm: len(enc.encode(block)) for arm, block in blocks.items()}
            if any(not .95 <= lengths[a] / count <= 1.05 for a in ARMS):
                raise RuntimeError('Length control failed before candidate generation')
            base = build_prompt(cfg_for(seed), pop[slot]) + '\nPARENT SLOT: ' + str(slot)
            base += '\nPOPULATION SOURCE (original slot order):\n' + json.dumps(
                [{'slot': i, 'code': p.code} for i, p in enumerate(pop)], sort_keys=True)
            base += '\nCUMULATIVE TRAINING FITNESS:\n' + json.dumps(
                [{'slot': i, 'fitness': round(a['fitness'], 6)} for i, a in enumerate(data['assessment'])], sort_keys=True)
            cid = f's{seed}-rank{rank}'
            c = {'id': cid, 'seed': seed, 'rank': rank, 'slot': slot, 'donor': donor,
                 'parent': asdict(pop[slot]), 'block_tokens': lengths,
                 'effective_mismatch': correct != wrong,
                 'prompts': {arm: base + '\n' + blocks[arm] + '\nReturn only the new strategy source.\n' for arm in ARMS}}
            write_json(root / 'contexts' / (cid + '.json'), c)
            contexts[cid] = c
    rows = []
    for job in manifest['jobs']:
        prompt = contexts[job['context']]['prompts'][job['arm']]
        rows.append({'id': job['id'], 'prompt_hash': digest(prompt), 'tokens_proxy': len(enc.encode(prompt))})
    sealed = {'implementation_hash': source_hash(), 'rows': rows,
              'contexts': {cid: digest(json.dumps(c, sort_keys=True)) for cid, c in contexts.items()},
              'effective_mismatch_contexts': sum(c['effective_mismatch'] for c in contexts.values()),
              'n_contexts': len(contexts), 'sealed_at': time.time()}
    path = root / 'PROMPTS_SEALED.json'
    if path.exists():
        previous = read_json(path)
        if previous['rows'] != rows or previous['contexts'] != sealed['contexts']:
            raise RuntimeError('Frozen prompts changed')
    else:
        write_json(path, sealed)
    return sealed


def candidate_job(arg):
    root, job = arg
    root = Path(root)
    path = root / 'candidates' / (job['id'] + '.json')
    if path.exists():
        return {'id': job['id'], 'cached': True}
    c = read_json(root / 'contexts' / (job['context'] + '.json'))
    cfg = cfg_for(job['seed'])
    gen = Generator(root / 'requests_candidates', 'deepseek', 'deepseek-flash', cfg.temperature)
    child = gen.generate(job['id'], c['prompts'][job['arm']], cfg)
    write_json(path, {**job, 'child': asdict(child) if child else None,
                     'parent_key': Policy(**c['parent']).key, 'valid': child is not None})
    return {'id': job['id'], 'valid': child is not None}


def training_scores(candidate, pop, slot, cfg, repeats=20):
    """Nested repeats: S1's first five games are a strict subset of S2."""
    peer, archive = [], []
    calls = 0
    for j, opponent in enumerate(pop):
        if j == slot:
            continue
        scores = []
        i, k = sorted((slot, j))
        for rep in range(repeats):
            sd = seed_for(cfg.seed, 'peer', 19001, i, k, rep)
            game = match(candidate, opponent, cfg, sd) if slot < j else match(opponent, candidate, cfg, sd)
            scores.append(game['scores'][0 if slot < j else 1] / cfg.rounds)
            calls += 1
        peer.append(scores)
    for j, opponent in enumerate(TRAIN):
        scores = []
        for rep in range(repeats):
            scores.append(match(candidate, opponent, cfg, seed_for(cfg.seed, 'archive', 19001, j, rep))['scores'][0] / cfg.rounds)
            calls += 1
        archive.append(scores)
    def score(n):
        return cfg.peer_weight * mean(mean(r[:n]) for r in peer) + (1 - cfg.peer_weight) * mean(mean(r[:n]) for r in archive)
    return {'S1': score(min(5, repeats)), 'S2': score(repeats), 'games': calls,
            'peer_replicates': peer, 'archive_replicates': archive}


def measured_selection(candidate, pop, slot, cfg):
    out = {}
    try:
        values = training_scores(candidate, pop, slot, cfg)
        for name in ('S1', 'S2'):
            out[name] = {'status': 'ok', 'score': values[name]}
        out['training_game_count'] = values['games']
    except Exception as exc:
        for name in ('S1', 'S2'):
            out[name] = {'status': 'failed', 'error_type': type(exc).__name__}
    try:
        value = versus(candidate, [p for _, p in panel('V')], replace(cfg, repeats=20), 'specificity-V')
        out['S3'] = {'status': 'ok', 'score': value['score'] / cfg.rounds,
                     'games': len(panel('V')) * 20, 'detail': value}
    except Exception as exc:
        out['S3'] = {'status': 'failed', 'error_type': type(exc).__name__}
    return out


def evaluation_job(arg):
    root, kind, identity = arg
    root = Path(root)
    path = root / 'selection_scores' / (identity + '.json')
    if path.exists():
        return {'id': identity, 'cached': True}
    record = read_json(root / ('contexts' if kind == 'parent' else 'candidates') / (identity + '.json'))
    cid = identity if kind == 'parent' else record['context']
    c = read_json(root / 'contexts' / (cid + '.json'))
    data = read_json(root / 'populations' / f"s{c['seed']}.json")
    item = c['parent'] if kind == 'parent' else record['child']
    out = measured_selection(Policy(**item), [Policy(**p) for p in data['population']], c['slot'], cfg_for(c['seed'])) if item else {
        s: {'status': 'invalid'} for s in ('S1', 'S2', 'S3')}
    if kind == 'parent' and any(out[s]['status'] != 'ok' for s in ('S1', 'S2', 'S3')):
        raise RuntimeError('Parent evaluation failed: ' + identity)
    write_json(path, {'id': identity, 'context': cid, 'kind': kind, 'metrics': out})
    return {'id': identity, 'status': {s: out[s]['status'] for s in ('S1', 'S2', 'S3')}}


def choose(parent, children, rule):
    best, value = None, parent['metrics'][rule]['score']
    for child, scores in children:
        item = scores['metrics'][rule]
        if child['valid'] and item['status'] == 'ok' and item['score'] > value:
            best, value = child['id'], item['score']
    return {'winner': best, 'score': value, 'accepted': best is not None}


def seal_selections(root, manifest, *, readonly=False):
    root = Path(root)
    rows = []
    for seed in SEEDS:
        for rank in RANKS:
            cid = f's{seed}-rank{rank}'
            parent = read_json(root / 'selection_scores' / (cid + '.json'))
            for arm in ARMS:
                jobs = sorted([j for j in manifest['jobs'] if j['context'] == cid and j['arm'] == arm], key=lambda j: j['draw'])
                children = [(read_json(root / 'candidates' / (j['id'] + '.json')),
                             read_json(root / 'selection_scores' / (j['id'] + '.json'))) for j in jobs]
                for rule in ('S1', 'S2', 'S3'):
                    rows.append({'context': cid, 'seed': seed, 'arm': arm, 'rule': rule, **choose(parent, children, rule)})
    result = {'rows': rows, 'implementation_hash': manifest['implementation_hash'] if readonly else source_hash(),
              'candidate_hashes': {j['id']: digest((root / 'candidates' / (j['id'] + '.json')).read_text(encoding='utf-8')) for j in manifest['jobs']}}
    path = root / 'SELECTIONS_SEALED.json'
    if path.exists() and any(read_json(path)[key] != value for key, value in result.items()):
        raise RuntimeError('Selections changed after sealing')
    if not readonly:
        write_json(path, result)
    return result


def holdout_measure(candidate, cfg):
    out = {}
    h = panel('H')
    for name, rounds, noise in [('default', 100, 0), ('noise01', 100, .01), ('long', 200, 0)]:
        try:
            value = versus(candidate, [p for _, p in h], replace(cfg, rounds=rounds, noise=noise, repeats=20), 'specificity-H-' + name)
            out[name] = {'status': 'ok', 'score': value['score'] / rounds,
                         'cooperation': value['cooperation'], 'worst_score': value['worst_score'] / rounds,
                         'families': {f: mean(row['score'] / rounds for (fam, _), row in zip(h, value['opponents']) if fam == f)
                                      for f in ('recovery', 'exploitation', 'random', 'memory')}, 'detail': value}
        except Exception as exc:
            out[name] = {'status': 'failed', 'error_type': type(exc).__name__}
    try:
        out['behavior'] = {'status': 'ok', 'probes': probes(candidate, cfg, 'H')}
    except Exception as exc:
        out['behavior'] = {'status': 'failed', 'error_type': type(exc).__name__}
    return out


def holdout_job(arg):
    root, kind, identity = arg
    root = Path(root)
    if not (root / 'H_RELEASED.json').exists():
        raise RuntimeError('Holdout not released')
    path = root / 'holdout' / (identity + '.json')
    if path.exists():
        return {'id': identity, 'cached': True}
    record = read_json(root / ('contexts' if kind == 'parent' else 'candidates') / (identity + '.json'))
    cid = identity if kind == 'parent' else record['context']
    c = read_json(root / 'contexts' / (cid + '.json'))
    item = c['parent'] if kind == 'parent' else record['child']
    measured = holdout_measure(Policy(**item), cfg_for(c['seed'])) if item else {}
    if kind == 'parent':
        if any(measured[s]['status'] != 'ok' for s in ('default', 'noise01', 'long', 'behavior')):
            raise RuntimeError('Parent holdout failed: ' + identity)
        result = {'id': identity, 'context': cid, 'measured': measured, 'deployed': measured}
    else:
        baseline = read_json(root / 'holdout' / (cid + '.json'))['measured']
        fallbacks = {s: measured.get(s, {}).get('status') != 'ok' for s in baseline}
        deployed = {s: baseline[s] if fallbacks[s] else measured[s] for s in baseline}
        result = {**record, 'measured': measured, 'deployed': deployed, 'fallback': fallbacks,
                  'delta': {s: {key: deployed[s][key] - baseline[s][key] for key in ('score', 'cooperation', 'worst_score')}
                            for s in ('default', 'noise01', 'long')}}
    write_json(path, result)
    return {'id': identity, 'completed': True}



def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=['freeze', 'initialize', 'prepare', 'generate', 'select', 'holdout', 'all'])
    parser.add_argument('--output', default=DEFAULT_ROOT)
    parser.add_argument('--workers', type=int, default=12)
    parser.add_argument('--api-workers', type=int, default=8)
    parser.add_argument('--env-file', default='../../.env')
    args = parser.parse_args()
    if min(args.workers, args.api_workers) < 1:
        parser.error('Worker counts must be positive')
    root = Path(args.output)
    root.mkdir(parents=True, exist_ok=True)
    if args.stage == 'freeze':
        print(json.dumps({'frozen': freeze(root)['implementation_hash'], 'requests': 480}))
        return
    manifest = check_manifest(root)
    from dotenv import load_dotenv
    load_dotenv(args.env_file, override=False)
    phases = ['initialize', 'prepare', 'generate', 'select', 'holdout'] if args.stage == 'all' else [args.stage]
    for phase in phases:
        check_manifest(root)
        if phase == 'initialize':
            pool_run(initial_job, [(str(root), job) for job in manifest['init_jobs']], args.api_workers, root, phase)
        elif phase == 'prepare':
            initial = [read_json(root / 'initial' / (j['id'] + '.json')) for j in manifest['init_jobs']]
            if sum(r['fallback'] is not None for r in initial) > manifest['init_quality_pause_above_invalid']:
                raise RuntimeError('Initialization fallback exceeds 10%; pause entire batch for audit')
            pool_run(prepare_seed, [(str(root), seed) for seed in SEEDS], args.workers, root, phase, True)
            make_prompts(root, manifest)
        elif phase == 'generate':
            seal = make_prompts(root, manifest)
            if not seal['rows']:
                raise RuntimeError('Missing prompt seal')
            pool_run(candidate_job, [(str(root), job) for job in manifest['jobs']], args.api_workers, root, phase)
        elif phase == 'select':
            for job in manifest['jobs']:
                read_json(root / 'candidates' / (job['id'] + '.json'))
            identities = [('parent', f's{seed}-rank{rank}') for seed in SEEDS for rank in RANKS]
            identities += [('child', job['id']) for job in manifest['jobs']]
            pool_run(evaluation_job, [(str(root), kind, identity) for kind, identity in identities], args.workers, root, phase, True)
            seal_selections(root, manifest)
        elif phase == 'holdout':
            seal_selections(root, manifest)
            selections = root / 'SELECTIONS_SEALED.json'
            write_json(root / 'H_RELEASED.json', {'selection_digest': digest(selections.read_text(encoding='utf-8')), 'released_at': time.time()})
            pool_run(holdout_job, [(str(root), 'parent', f's{seed}-rank{rank}') for seed in SEEDS for rank in RANKS], args.workers, root, 'holdout_parents', True)
            pool_run(holdout_job, [(str(root), 'child', job['id']) for job in manifest['jobs']], args.workers, root, 'holdout_children', True)
            write_json(root / 'COMPLETE.json', {'implementation_hash': source_hash(), 'completed_at': time.time(),
                                               'initial': len(manifest['init_jobs']), 'candidates': len(manifest['jobs']), 'contexts': len(SEEDS) * len(RANKS)})


if __name__ == '__main__':
    main()
