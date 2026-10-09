"""Paired report experiment: prompts, generation, selection, holdout and staged execution."""
import argparse
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, wait, FIRST_COMPLETED
from dataclasses import asdict, replace
import json
import os
from pathlib import Path
import random
from statistics import mean
import time

from .records import (read_json, write_json, population_root, require_holdout, digest,
                      implementation_hash, check_manifest, release_holdout, complete, runner_lock)
from .core import Config, Policy, evaluate, match, seed_for, versus
from .baselines import TRAIN
from .report_assignment import derangement
from .prompts import build_prompt
from .run import Generator
from .specificity_assets import (ARMS, SCORE_ARMS, experiment_arms, SEEDS, RANKS, panel, probes, diagnostic_block,
                                 tokenizer, probe_specs, generation_arms, information_prompt)
from .condition_generation import candidate_job, generate_conditions, write_arm_logs

DEFAULT_ROOT = 'results/feedback_specificity_v2'



def cfg_for(seed):
    return Config(seed=seed)



def init_prompt(seed, slot):
    return build_prompt(cfg_for(seed)) + f'\nIndependent candidate {slot}; replicate {seed}.\n'



def assets_record():
    return {'panels': {split: [{'family': family, **asdict(p)} for family, p in panel(split)]
                       for split in ('V', 'H')},
            'probes': {split: probe_specs(split) for split in ('F', 'H')},
            'tokenizer': 'tiktoken cl100k_base; proxy tokenizer, not provider billing tokenizer',
            'families_disjoint_from_training': False}



def freeze(root, seeds=None, ranks=None, source=None, arms=None):
    root = Path(root)
    if (root / 'manifest.json').exists():
        manifest = check_manifest(root)
        if arms is not None and list(experiment_arms(arms)) != manifest['arms']:
            raise ValueError('Existing frozen report conditions differ')
        return manifest
    arms = experiment_arms(arms)
    seeds = tuple(seeds) if seeds is not None else SEEDS
    ranks = tuple(ranks) if ranks is not None else RANKS
    if not seeds or len(seeds) > 20 or len(set(seeds)) != len(seeds):
        raise ValueError('Require 1 to 20 distinct population seeds')
    if not ranks or len(set(ranks)) != len(ranks) or any(rank not in RANKS for rank in ranks):
        raise ValueError('Parent ranks must be a distinct subset of 1, 3, 6')
    init_jobs = [{'id': f'init-s{seed}-slot{slot}', 'seed': seed, 'slot': slot}
                 for seed in seeds for slot in range(12)]
    order = generation_arms(arms)
    parents = [(seed, rank, draw) for seed in seeds for rank in ranks for draw in range(2)]
    random.Random(2026091901).shuffle(parents)
    jobs = []
    for position, arm in enumerate(order):
        for seed, rank, draw in parents:
            cid = f's{seed}-rank{rank}'
            jobs.append({'id': f'{cid}-d{draw}-pos{position}', 'context': cid,
                         'seed': seed, 'rank': rank, 'draw': draw, 'position': position, 'arm': arm})
    random.Random(2026091902).shuffle(init_jobs)
    manifest = {'version': 'specificity-v3', 'implementation_hash': implementation_hash(),
                'engine_hash': implementation_hash(), 'provider': 'deepseek', 'model': 'deepseek-flash',
                'config': asdict(cfg_for(seeds[0])), 'seeds': list(seeds), 'arms': list(arms),
                'ranks': list(ranks), 'draws': 2, 'init_jobs': init_jobs, 'jobs': jobs,
                'generation_order': list(order), 'arm_positions': {arm: i for i, arm in enumerate(order)},
                'request_dispatch': 'Complete each condition before starting the next; concurrent requests within condition.',
                'data_logs': {arm: f'arm_logs/{arm}.jsonl' for arm in arms}, 'assets': assets_record(),
                'primary': 'raw_H_default_gain_accurate_minus_mismatched',
                'independent_unit': f'{len(seeds)} population clusters', 'delta': .05,
                'selection_repeats': {'S1': 5, 'S2': 20, 'S3': 20}, 'holdout_repeats': 20,
                'training_selection_generation_namespace': 19001,
                'fallback': 'invalid candidate/setting runtime failure retains parent; API failures remain missing',
                'init_fallback': 'ALLD when generation invalid or feedback probe execution fails; no replacement calls',
                'init_quality_pause_above_invalid': len(init_jobs) // 10,
                'requested_calls': {'initial': len(init_jobs), 'candidates': len(jobs), 'total': len(init_jobs) + len(jobs)},
                'frozen_at': time.time(),
                'inference': 'seed-cluster bootstrap CI; exact cluster sign swaps for arm contrasts under paired exchangeability; parent contrast additionally assumes symmetric cluster effects',
                'length_control': 'cl100k_base +/-5% for Accurate and Mismatched reports; not DeepSeek token equality'}
    if source is not None:
        source = Path(source).resolve()
        origin = read_json(source / 'manifest.json')
        if not set(seeds) <= set(origin['seeds']) or not set(ranks) <= set(origin['ranks']):
            raise ValueError('Requested populations/parents are absent from the source')
        expected_config = dict(manifest['config'])
        expected_config['seed'] = origin['config']['seed']
        if origin['config'] != expected_config:
            raise ValueError('Source initialization configuration differs')
        files = ['manifest.json'] + [f'populations/s{seed}.json' for seed in seeds]
        files += [f"{folder}/{job['id']}.json" for folder in ('initial', 'requests_initial') for job in init_jobs]
        manifest['initial_source'] = Path(os.path.relpath(source, root.resolve())).as_posix()
        manifest['initial_source_hashes'] = {relative: digest((source / relative).read_text(encoding='utf-8')) for relative in files}
        manifest['requested_calls'] = {'initial': 0, 'candidates': len(jobs), 'total': len(jobs)}
        manifest['independent_unit'] = f'{len(seeds)} reused population clusters; new candidate responses'
    write_json(root / 'manifest.json', manifest)
    write_arm_logs(root, manifest)
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



def make_contexts(root, manifest):
    root = Path(root)
    enc = tokenizer()
    contexts = {}
    populations = population_root(root, manifest)
    for seed in manifest['seeds']:
        data = read_json(populations / 'populations' / f's{seed}.json')
        pop = [Policy(**p) for p in data['population']]
        for rank in manifest['ranks']:
            slot = data['selected_slots'][str(rank)]
            donor = data['mapping'][slot]
            correct = diagnostic_block(data['diagnostics'][slot])
            wrong = diagnostic_block(data['diagnostics'][donor])
            count = len(enc.encode(correct))
            arms = experiment_arms(manifest['arms'])
            blocks = {arm: {'accurate': correct, 'mismatched': wrong, 'score': ''}[arm] for arm in arms}
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
                 'prompts': {arm: information_prompt(base, arm, blocks) for arm in arms}}
            write_json(root / 'contexts' / (cid + '.json'), c)
            contexts[cid] = c
    return contexts



def make_prompts(root, manifest):
    root = Path(root)
    enc = tokenizer()
    contexts = make_contexts(root, manifest)
    rows = []
    for job in manifest['jobs']:
        prompt = contexts[job['context']]['prompts'][job['arm']]
        rows.append({'id': job['id'], 'prompt_hash': digest(prompt), 'tokens_proxy': len(enc.encode(prompt))})
    sealed = {'implementation_hash': implementation_hash(), 'rows': rows,
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
    data = read_json(population_root(root) / 'populations' / f"s{c['seed']}.json")
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
    for seed in manifest['seeds']:
        for rank in manifest['ranks']:
            cid = f's{seed}-rank{rank}'
            parent = read_json(root / 'selection_scores' / (cid + '.json'))
            for arm in experiment_arms(manifest['arms']):
                jobs = sorted([j for j in manifest['jobs'] if j['context'] == cid and j['arm'] == arm], key=lambda j: j['draw'])
                children = [(read_json(root / 'candidates' / (j['id'] + '.json')),
                             read_json(root / 'selection_scores' / (j['id'] + '.json'))) for j in jobs]
                for rule in ('S1', 'S2', 'S3'):
                    rows.append({'context': cid, 'seed': seed, 'arm': arm, 'rule': rule, **choose(parent, children, rule)})
    result = {'rows': rows, 'implementation_hash': manifest['implementation_hash'] if readonly else implementation_hash(),
              'candidate_hashes': {j['id']: digest((root / 'candidates' / (j['id'] + '.json')).read_text(encoding='utf-8')) for j in manifest['jobs']}}
    path = root / 'SELECTIONS_SEALED.json'
    if path.exists():
        previous = read_json(path)
        if previous['rows'] != result['rows'] or previous['candidate_hashes'] != result['candidate_hashes']:
            raise RuntimeError('Selections changed after sealing')
        return previous
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
    require_holdout(root)
    path = root / 'holdout' / (identity + '.json')
    if path.exists():
        cached = read_json(path)
        if not (kind == 'child' and cached.get('status') == 'skipped' and
                cached.get('skip_reason') == 'parent_holdout_failed'):
            return {'id': identity, 'cached': True}
    record = read_json(root / ('contexts' if kind == 'parent' else 'candidates') / (identity + '.json'))
    cid = identity if kind == 'parent' else record['context']
    c = read_json(root / 'contexts' / (cid + '.json'))
    item = c['parent'] if kind == 'parent' else record['child']
    measured = holdout_measure(Policy(**item), cfg_for(c['seed'])) if item else {}
    if kind == 'parent':
        failed = [s for s in ('default', 'noise01', 'long', 'behavior')
                  if measured[s]['status'] != 'ok']
        result = {'id': identity, 'context': cid, 'status': 'runtime_failure' if failed else 'complete',
                  'failed_settings': failed, 'measured': measured, 'deployed': measured}
    else:
        parent_holdout = read_json(root / 'holdout' / (cid + '.json'))
        if parent_holdout.get('status', 'complete') != 'complete':
            result = {**record, 'status': 'skipped',
                      'skip_reason': 'parent_holdout_failed',
                      'parent_holdout_status': parent_holdout.get('status')}
            write_json(path, result)
            return {'id': identity, 'skipped': True, 'reason': result['skip_reason']}
        baseline = parent_holdout['measured']
        fallbacks = {s: measured.get(s, {}).get('status') != 'ok' for s in baseline}
        deployed = {s: baseline[s] if fallbacks[s] else measured[s] for s in baseline}
        result = {**record, 'status': 'complete', 'measured': measured, 'deployed': deployed, 'fallback': fallbacks,
                  'delta': {s: {key: deployed[s][key] - baseline[s][key] for key in ('score', 'cooperation', 'worst_score')}
                            for s in ('default', 'noise01', 'long')}}
    write_json(path, result)
    return {'id': identity, 'completed': True, 'status': result['status']}



def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=['freeze', 'initialize', 'prepare', 'generate', 'select', 'holdout', 'all'])
    parser.add_argument('--output', default=DEFAULT_ROOT)
    parser.add_argument('--workers', type=int, default=12)
    parser.add_argument('--api-workers', type=int, default=8)
    parser.add_argument('--env-file', default='../../.env')
    parser.add_argument('--seeds', nargs='+', type=int, help='Population seeds to freeze; defaults to the paper batch.')
    parser.add_argument('--ranks', nargs='+', type=int, choices=RANKS, help='Parent ranks to freeze; defaults to 1, 3, 6.')
    parser.add_argument('--source', type=Path, help='Reuse recorded initial populations in place; only candidate generation calls the API.')
    parser.add_argument('--arms', nargs='+', choices=SCORE_ARMS, help='Experiment information conditions; defaults to score accurate mismatched. Accurate and mismatched are required for the paper contrast.')
    parser.add_argument('--arm', choices=SCORE_ARMS, help='Generate one condition; earlier condition batches must be complete.')
    args = parser.parse_args()
    if min(args.workers, args.api_workers) < 1:
        parser.error('Worker counts must be positive')
    root = Path(args.output)
    root.mkdir(parents=True, exist_ok=True)
    if args.arm is not None and args.stage != 'generate':
        parser.error('--arm belongs to the generate stage')
    if args.stage == 'freeze':
        manifest = freeze(root, args.seeds, args.ranks, args.source, args.arms)
        print(json.dumps({'frozen': manifest['implementation_hash'], 'requests': manifest['requested_calls']['total']}))
        return
    if args.seeds is not None or args.ranks is not None or args.source is not None or args.arms is not None:
        parser.error('--seeds, --ranks, --source and --arms belong to the freeze stage')
    manifest = check_manifest(root)
    from dotenv import load_dotenv
    load_dotenv(args.env_file, override=False)
    phases = ['initialize', 'prepare', 'generate', 'select', 'holdout'] if args.stage == 'all' else [args.stage]
    with runner_lock(root, args.stage):
        for phase in phases:
            check_manifest(root)
            if phase == 'initialize' and 'initial_source' in manifest:
                print(json.dumps({'stage': phase, 'reused_initial_requests': len(manifest['init_jobs']), 'new_api_calls': 0}), flush=True)
            elif phase == 'initialize':
                pool_run(initial_job, [(str(root), job) for job in manifest['init_jobs']], args.api_workers, root, phase)
            elif phase == 'prepare':
                populations = population_root(root, manifest)
                initial = [read_json(populations / 'initial' / (j['id'] + '.json')) for j in manifest['init_jobs']]
                if sum(r['fallback'] is not None for r in initial) > manifest['init_quality_pause_above_invalid']:
                    raise RuntimeError('Initialization fallback exceeds 10%; pause entire batch for audit')
                if 'initial_source' not in manifest:
                    pool_run(prepare_seed, [(str(root), seed) for seed in manifest['seeds']], args.workers, root, phase, True)
                make_prompts(root, manifest)
            elif phase == 'generate':
                seal = make_prompts(root, manifest)
                if not seal['rows']:
                    raise RuntimeError('Missing prompt seal')
                generate_conditions(root, manifest, args.api_workers, candidate_job, args.arm)
            elif phase == 'select':
                for job in manifest['jobs']:
                    read_json(root / 'candidates' / (job['id'] + '.json'))
                identities = [('parent', f's{seed}-rank{rank}') for seed in manifest['seeds'] for rank in manifest['ranks']]
                identities += [('child', job['id']) for job in manifest['jobs']]
                pool_run(evaluation_job, [(str(root), kind, identity) for kind, identity in identities], args.workers, root, phase, True)
                seal_selections(root, manifest)
                write_arm_logs(root, manifest)
            elif phase == 'holdout':
                seal_selections(root, manifest)
                release_holdout(root)
                pool_run(holdout_job, [(str(root), 'parent', f's{seed}-rank{rank}') for seed in manifest['seeds'] for rank in manifest['ranks']], args.workers, root, 'holdout_parents', True)
                pool_run(holdout_job, [(str(root), 'child', job['id']) for job in manifest['jobs']], args.workers, root, 'holdout_children', True)
                write_arm_logs(root, manifest)
                complete(root, initial=len(manifest['init_jobs']), candidates=len(manifest['jobs']),
                         contexts=len(manifest['seeds']) * len(manifest['ranks']))



if __name__ == '__main__':
    main()
