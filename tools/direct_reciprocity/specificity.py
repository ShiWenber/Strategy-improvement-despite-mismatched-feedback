"""Freeze, seal and dispatch the paired direct-reciprocity experiment."""
import argparse
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, wait, FIRST_COMPLETED
from dataclasses import asdict
import json
import os
from pathlib import Path
import random
import time

from experiments.direct_reciprocity import specificity as experiment
from experiments.direct_reciprocity.core import seed_for
from experiments.direct_reciprocity.specificity import cfg_for, choose, DEFAULT_ROOT
from experiments.direct_reciprocity.specificity_assets import ARMS, SEEDS, RANKS, tokenizer, panel, probe_specs
from .records import (digest, implementation_hash, read_json, write_json,
                      check_manifest, population_root, release_holdout, complete, runner_lock)


def assets_record():
    return {'panels': {split: [{'family': family, **asdict(p)} for family, p in panel(split)]
                       for split in ('V', 'H')},
            'probes': {split: probe_specs(split) for split in ('F', 'H')},
            'tokenizer': 'tiktoken cl100k_base; proxy tokenizer, not provider billing tokenizer',
            'families_disjoint_from_training': False}



def freeze(root, seeds=None, ranks=None, source=None):
    root = Path(root)
    if (root / 'manifest.json').exists():
        return check_manifest(root)
    seeds = tuple(seeds) if seeds is not None else SEEDS
    ranks = tuple(ranks) if ranks is not None else RANKS
    if not seeds or len(seeds) > 20 or len(set(seeds)) != len(seeds):
        raise ValueError('Require 1 to 20 distinct population seeds')
    if not ranks or len(set(ranks)) != len(ranks) or any(rank not in RANKS for rank in ranks):
        raise ValueError('Parent ranks must be a distinct subset of 1, 3, 6')
    init_jobs = [{'id': f'init-s{seed}-slot{slot}', 'seed': seed, 'slot': slot}
                 for seed in seeds for slot in range(12)]
    jobs, permutations = [], {}
    for seed in seeds:
        # One random arm-to-request-position permutation per independent cluster.
        order = list(ARMS)
        random.Random(seed_for('specificity-arm-assignment', seed)).shuffle(order)
        permutations[str(seed)] = order
        for rank in ranks:
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
    manifest = {'version': 'specificity-v2', 'implementation_hash': implementation_hash(),
                'engine_hash': implementation_hash(), 'provider': 'deepseek', 'model': 'deepseek-flash',
                'config': asdict(cfg_for(seeds[0])), 'seeds': list(seeds), 'arms': list(ARMS),
                'ranks': list(ranks), 'draws': 2, 'init_jobs': init_jobs, 'jobs': jobs,
                'arm_position_permutations': permutations, 'assets': assets_record(),
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
        if origin['arms'] != list(ARMS) or origin['draws'] != 2:
            raise ValueError('Source report conditions or candidate budget differ')
        files = ['manifest.json'] + [f'populations/s{seed}.json' for seed in seeds]
        files += [f"{folder}/{job['id']}.json" for folder in ('initial', 'requests_initial') for job in init_jobs]
        manifest['initial_source'] = Path(os.path.relpath(source, root.resolve())).as_posix()
        manifest['initial_source_hashes'] = {relative: digest((source / relative).read_text(encoding='utf-8')) for relative in files}
        manifest['requested_calls'] = {'initial': 0, 'candidates': len(jobs), 'total': len(jobs)}
        manifest['independent_unit'] = f'{len(seeds)} reused population clusters; new candidate responses'
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


def seal_selections(root, manifest, *, readonly=False):
    root = Path(root)
    rows = []
    for seed in manifest['seeds']:
        for rank in manifest['ranks']:
            cid = f's{seed}-rank{rank}'
            parent = read_json(root / 'selection_scores' / (cid + '.json'))
            for arm in ARMS:
                jobs = sorted([j for j in manifest['jobs'] if j['context'] == cid and j['arm'] == arm], key=lambda j: j['draw'])
                children = [(read_json(root / 'candidates' / (j['id'] + '.json')),
                             read_json(root / 'selection_scores' / (j['id'] + '.json'))) for j in jobs]
                for rule in ('S1', 'S2', 'S3'):
                    rows.append({'context': cid, 'seed': seed, 'arm': arm, 'rule': rule, **choose(parent, children, rule)})
    result = {'rows': rows, 'implementation_hash': manifest['implementation_hash'] if readonly else implementation_hash(),
              'candidate_hashes': {j['id']: digest((root / 'candidates' / (j['id'] + '.json')).read_text(encoding='utf-8')) for j in manifest['jobs']}}
    path = root / 'SELECTIONS_SEALED.json'
    if path.exists() and any(read_json(path)[key] != value for key, value in result.items()):
        raise RuntimeError('Selections changed after sealing')
    if not readonly:
        write_json(path, result)
    return result


def make_prompts(root, manifest):
    root = Path(root)
    enc = tokenizer()
    contexts = experiment.make_contexts(root, manifest)
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
    args = parser.parse_args()
    if min(args.workers, args.api_workers) < 1:
        parser.error('Worker counts must be positive')
    root = Path(args.output)
    root.mkdir(parents=True, exist_ok=True)
    if args.stage == 'freeze':
        manifest = freeze(root, args.seeds, args.ranks, args.source)
        print(json.dumps({'frozen': manifest['implementation_hash'], 'requests': manifest['requested_calls']['total']}))
        return
    if args.seeds is not None or args.ranks is not None or args.source is not None:
        parser.error('--seeds, --ranks and --source belong to the freeze stage')
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
                pool_run(experiment.initial_job, [(str(root), job) for job in manifest['init_jobs']], args.api_workers, root, phase)
            elif phase == 'prepare':
                populations = population_root(root, manifest)
                initial = [read_json(populations / 'initial' / (j['id'] + '.json')) for j in manifest['init_jobs']]
                if sum(r['fallback'] is not None for r in initial) > manifest['init_quality_pause_above_invalid']:
                    raise RuntimeError('Initialization fallback exceeds 10%; pause entire batch for audit')
                if 'initial_source' not in manifest:
                    pool_run(experiment.prepare_seed, [(str(root), seed) for seed in manifest['seeds']], args.workers, root, phase, True)
                make_prompts(root, manifest)
            elif phase == 'generate':
                seal = make_prompts(root, manifest)
                if not seal['rows']:
                    raise RuntimeError('Missing prompt seal')
                pool_run(experiment.candidate_job, [(str(root), job) for job in manifest['jobs']], args.api_workers, root, phase)
            elif phase == 'select':
                for job in manifest['jobs']:
                    read_json(root / 'candidates' / (job['id'] + '.json'))
                identities = [('parent', f's{seed}-rank{rank}') for seed in manifest['seeds'] for rank in manifest['ranks']]
                identities += [('child', job['id']) for job in manifest['jobs']]
                pool_run(experiment.evaluation_job, [(str(root), kind, identity) for kind, identity in identities], args.workers, root, phase, True)
                seal_selections(root, manifest)
            elif phase == 'holdout':
                seal_selections(root, manifest)
                release_holdout(root)
                pool_run(experiment.holdout_job, [(str(root), 'parent', f's{seed}-rank{rank}') for seed in manifest['seeds'] for rank in manifest['ranks']], args.workers, root, 'holdout_parents', True)
                pool_run(experiment.holdout_job, [(str(root), 'child', job['id']) for job in manifest['jobs']], args.workers, root, 'holdout_children', True)
                complete(root, initial=len(manifest['init_jobs']), candidates=len(manifest['jobs']),
                         contexts=len(manifest['seeds']) * len(manifest['ranks']))


if __name__ == '__main__':
    main()
