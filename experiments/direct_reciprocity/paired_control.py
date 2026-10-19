"""Prepare and dispatch paired DeepSeek ON or Qwen OFF/ON follow-up batches."""
import argparse
from functools import partial
import json
import os
from pathlib import Path
import shutil
import time

from .records import (read_json, write_json, check_manifest,
                      population_root, release_holdout, complete, runner_lock)
from .specificity import evaluation_job, holdout_job, pool_run, seal_selections
from .specificity_assets import SCORE_ARMS, generation_arms
from .condition_generation import candidate_job, generate_conditions, jobs_for_arm, specification, write_arm_logs
from ..config.load_env import api_environment

SOURCE = Path('results/feedback_specificity_v2')


def settings(provider, root, *, model=None):
    if provider == 'deepseek':
        mode = 'on'
        protocol = Path('docs/direct_reciprocity/THINKING_384K_PROTOCOL.md')
        version = 'thinking-384k-v2'
    else:
        root = Path(root)
        mode = root.name
        if mode not in ('off', 'on') or root.parent.name != 'qwen3_8':
            raise ValueError('Use results/qwen3_8/off or results/qwen3_8/on')
        protocol = Path('results/qwen3_8/PROTOCOL.md')
    api = specification('', provider, mode, model=model)
    api.pop('prompt')
    if provider == 'qwen':
        version = api['model'] + '-v2'
    return mode, protocol, api, version


def prepare(root, source, provider):
    root, source = Path(root), Path(source)
    if (root / 'manifest.json').exists():
        return verify(root, provider)
    old = check_manifest(source)
    mode, protocol, api, version = settings(provider, root)
    if root.exists() and any(root.iterdir()):
        raise RuntimeError('Nonempty unsealed destination; inspect before preparing')
    root.mkdir(parents=True, exist_ok=True)
    populations = population_root(source, old)
    files = [(p, Path('contexts') / p.name) for p in sorted((source / 'contexts').glob('*.json'))]
    files += [(p, Path('populations') / p.name) for p in sorted((populations / 'populations').glob('*.json'))]
    files += [(source / 'selection_scores' / (cid + '.json'), Path('selection_scores') / (cid + '.json'))
              for cid in sorted({j['context'] for j in old['jobs']})]
    for src, relative in files:
        dst = root / relative
        dst.parent.mkdir(exist_ok=True)
        shutil.copyfile(src, dst)
    if protocol.is_file():
        shutil.copyfile(protocol, root / 'PROTOCOL.md')
    manifest = dict(version=version, source=str(source.resolve()),
                    jobs=old['jobs'], seeds=old['seeds'], arms=old['arms'],
                    ranks=old['ranks'], draws=old['draws'], config=old['config'],
                    frozen_at=time.time(), new_calls=len(old['jobs']),
                    reused_initial_calls=len(old['init_jobs']), api=api)
    manifest.update(generation_order=list(generation_arms(old['arms'])),
                    request_dispatch=old['request_dispatch'],
                    data_logs={arm: f'arm_logs/{arm}.jsonl' for arm in old['arms']})
    if provider == 'deepseek':
        manifest.update(historical_budget=6000, comparison='historical paired configuration comparison')
    else:
        manifest.update(mode=mode, comparison='same frozen populations and prompts; Qwen modes differ in thinking and supported output limits')
    write_json(root / 'manifest.json', manifest)
    write_arm_logs(root, manifest)
    return manifest


def verify(root, provider, *, check_model=True):
    root = Path(root)
    m = read_json(root / 'manifest.json')
    mode, _, api, version = settings(provider, root, **({} if check_model else {'model': m['api']['model']}))
    if m['version'] != version or m.get('mode', 'on') != mode:
        raise RuntimeError('Provider or mode identity changed')
    if m['api'] != api:
        raise RuntimeError('Request configuration changed')
    return m


def release_parents(root, source, manifest):
    root, source = Path(root), Path(source)
    seal_selections(root, manifest)
    parents = []
    for cid in sorted({j['context'] for j in manifest['jobs']}):
        context = read_json(root / 'contexts' / (cid + '.json'))
        original = read_json(source / 'contexts' / (cid + '.json'))
        if context['parent'] != original['parent'] or context['seed'] != original['seed']:
            raise RuntimeError('Source parent differs from paired run: ' + cid)
        src = source / 'holdout' / (cid + '.json')
        if not src.is_file():
            raise FileNotFoundError(src)
        parents.append(src)
    for src in parents:
        dst = root / 'holdout' / src.name
        dst.parent.mkdir(exist_ok=True)
        shutil.copyfile(src, dst)
    release_holdout(root, historical_test_panel=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=['prepare', 'first', 'generate', 'all', 'select', 'holdout'])
    parser.add_argument('--provider', choices=['deepseek', 'qwen'], required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--source', type=Path, default=SOURCE)
    parser.add_argument('--api-workers', type=int, default=12)
    parser.add_argument('--api-retries', type=int, default=3,
                        help='Retries for transport failures and saved api_error records.')
    parser.add_argument('--workers', type=int, default=24)
    parser.add_argument('--env-file', type=Path, default=Path(__file__).resolve().parents[2] / '.env')
    parser.add_argument('--arm', choices=SCORE_ARMS, help='Generate one condition; earlier condition batches must be complete.')
    args = parser.parse_args()
    if min(args.workers, args.api_workers) < 1 or args.api_retries < 0:
        parser.error('Workers must be positive and api-retries cannot be negative')
    if args.arm is not None and args.stage not in ('first', 'generate'):
        parser.error('--arm belongs to the first or generate stage')
    if args.stage in ('prepare', 'first', 'generate', 'all'):
        os.environ.update(api_environment(args.env_file))
    root = args.output
    if args.stage == 'prepare':
        manifest = prepare(root, args.source, args.provider)
        print(json.dumps({'prepared': str(root), 'requests': len(manifest['jobs']), 'api': manifest['api']}))
        return
    manifest = verify(root, args.provider, check_model=args.stage in ('first', 'generate', 'all'))
    generate_kwargs = {'provider': args.provider, 'mode': manifest.get('mode', 'on'),
                       'model': manifest['api']['model']}
    if args.api_retries != 3:
        generate_kwargs['api_retries'] = args.api_retries
    generate = partial(candidate_job, **generate_kwargs)
    with runner_lock(root, args.stage):
        if args.stage == 'first':
            arm = args.arm or generation_arms(manifest['arms'])[0]
            job = jobs_for_arm(root, manifest, arm)[0]
            try:
                result = generate((str(root), job))
            finally:
                write_arm_logs(root, manifest)
            print(json.dumps(result), flush=True)
            return
        if args.stage in ('all', 'generate'):
            generate_conditions(root, manifest, args.api_workers, generate, args.arm)
        if args.stage in ('all', 'select'):
            verify(root, args.provider, check_model=False)
            for j in manifest['jobs']:
                read_json(root / 'candidates' / (j['id'] + '.json'))
            pool_run(evaluation_job, [(str(root), 'child', j['id']) for j in manifest['jobs']], args.workers, root, 'select', True)
            seal_selections(root, manifest)
            write_arm_logs(root, manifest)
        if args.stage in ('all', 'holdout'):
            verify(root, args.provider, check_model=False)
            release_parents(root, args.source, manifest)
            pool_run(holdout_job, [(str(root), 'child', j['id']) for j in manifest['jobs']], args.workers, root, 'holdout', True)
            write_arm_logs(root, manifest)
            complete(root, candidates=len(manifest['jobs']), contexts=len({j['context'] for j in manifest['jobs']}),
                     new_initial_calls=0)


if __name__ == '__main__':
    main()
