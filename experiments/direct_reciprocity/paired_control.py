"""Prepare and dispatch paired DeepSeek ON or Qwen OFF/ON follow-up batches."""
import argparse
import json
from pathlib import Path
import shutil
import time

from experiments.direct_reciprocity import thinking_control, qwen38_control
from .records import (read_json, write_json, digest, filehash, implementation_hash, check_manifest,
                      population_root, release_holdout, complete, runner_lock)
from .specificity import evaluation_job, holdout_job, pool_run, seal_selections
from .specificity_assets import SCORE_ARMS, generation_arms
from .condition_generation import generate_conditions, first_job, write_arm_logs

SOURCE = Path('results/feedback_specificity_v2')


def settings(provider, root):
    if provider == 'deepseek':
        module = thinking_control
        mode = 'on'
        protocol = module.PROTOCOL
        api = module.specification('')
        version = 'thinking-384k-v2'
    else:
        module = qwen38_control
        mode = module.mode_for(root)
        protocol = module.DEFAULT_ROOT / 'PROTOCOL.md'
        api = module.specification('', mode)
        version = 'qwen3.8-flash-v2'
    return module, mode, protocol, {k: v for k, v in api.items() if k != 'prompt'}, version


def prepare(root, source, provider):
    root, source = Path(root), Path(source)
    old = check_manifest(source)
    read_json(source / 'COMPLETE.json')
    module, mode, protocol, api, version = settings(provider, root)
    if (root / 'manifest.json').exists():
        return verify(root, source, provider)
    if root.exists() and any(root.iterdir()):
        raise RuntimeError('Nonempty unsealed destination; inspect before preparing')
    root.mkdir(parents=True, exist_ok=True)
    copied = {}
    populations = population_root(source, old)
    files = [(p, Path('contexts') / p.name) for p in sorted((source / 'contexts').glob('*.json'))]
    files += [(p, Path('populations') / p.name) for p in sorted((populations / 'populations').glob('*.json'))]
    files += [(source / 'selection_scores' / (cid + '.json'), Path('selection_scores') / (cid + '.json'))
              for cid in sorted({j['context'] for j in old['jobs']})]
    for src, relative in files:
        dst = root / relative
        dst.parent.mkdir(exist_ok=True)
        shutil.copyfile(src, dst)
        copied[relative.as_posix()] = filehash(src)
    shutil.copyfile(protocol, root / 'PROTOCOL.md')
    manifest = dict(version=version, source=str(source.resolve()),
                    source_manifest_hash=filehash(source / 'manifest.json'),
                    implementation_hash=implementation_hash(), runner_hash=filehash(__file__),
                    protocol_hash=filehash(root / 'PROTOCOL.md'), reused_file_hashes=copied,
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
    manifest['prompt_hashes'] = {
        job['id']: digest(read_json(root / 'contexts' / (job['context'] + '.json'))['prompts'][job['arm']])
        for job in manifest['jobs']}
    write_json(root / 'manifest.json', manifest)
    write_arm_logs(root, manifest)
    return manifest


def verify(root, source, provider):
    root, source = Path(root), Path(source)
    m = read_json(root / 'manifest.json')
    _, mode, _, api, version = settings(provider, root)
    if m['version'] != version or m.get('mode', 'on') != mode:
        raise RuntimeError('Provider or mode identity changed')
    if m['implementation_hash'] != implementation_hash() or m['runner_hash'] != filehash(__file__):
        raise RuntimeError('Frozen implementation changed')
    if source.resolve() != Path(m['source']).resolve() or filehash(source / 'manifest.json') != m['source_manifest_hash']:
        raise RuntimeError('Source manifest changed')
    if filehash(root / 'PROTOCOL.md') != m['protocol_hash']:
        raise RuntimeError('Frozen protocol changed')
    for rel, expected in m['reused_file_hashes'].items():
        if filehash(root / rel) != expected:
            raise RuntimeError('Reused input changed: ' + rel)
    if m['api'] != api:
        raise RuntimeError('Request configuration changed')
    return m


def release_parents(root, source, manifest):
    root, source = Path(root), Path(source)
    seal_selections(root, manifest)
    release_holdout(root, historical_test_panel=True)
    copied = {}
    for cid in sorted({j['context'] for j in manifest['jobs']}):
        src = source / 'holdout' / (cid + '.json')
        dst = root / 'holdout' / src.name
        dst.parent.mkdir(exist_ok=True)
        if dst.exists() and filehash(dst) != filehash(src):
            raise RuntimeError('Parent test record changed')
        shutil.copyfile(src, dst)
        copied[cid] = filehash(src)
    write_json(root / 'REUSED_PARENT_H.json', copied)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=['prepare', 'first', 'generate', 'all', 'select', 'holdout'])
    parser.add_argument('--provider', choices=['deepseek', 'qwen'], required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--source', type=Path, default=SOURCE)
    parser.add_argument('--api-workers', type=int, default=12)
    parser.add_argument('--workers', type=int, default=24)
    parser.add_argument('--env-file', default='.env')
    parser.add_argument('--arm', choices=SCORE_ARMS, help='Generate one condition; earlier condition batches must be complete.')
    args = parser.parse_args()
    if min(args.workers, args.api_workers) < 1:
        parser.error('Worker counts must be positive')
    if args.arm is not None and args.stage not in ('first', 'generate'):
        parser.error('--arm belongs to the first or generate stage')
    from dotenv import load_dotenv
    load_dotenv(args.env_file, override=False)
    root = args.output
    if args.stage == 'prepare':
        manifest = prepare(root, args.source, args.provider)
        print(json.dumps({'prepared': str(root), 'requests': len(manifest['jobs']), 'api': manifest['api']}))
        return
    manifest = verify(root, args.source, args.provider)
    module = settings(args.provider, root)[0]
    with runner_lock(root, args.stage):
        if args.stage == 'first':
            job = first_job(root, manifest, args.arm)
            try:
                result = module.generate_one((str(root), job))
            finally:
                write_arm_logs(root, manifest)
            write_json(root / 'FIRST_REQUEST_CHECK.json', {'completed': True, 'result': result})
            print(json.dumps(result), flush=True)
            return
        if args.stage in ('all', 'generate'):
            read_json(root / 'FIRST_REQUEST_CHECK.json')
            generate_conditions(root, manifest, args.api_workers, module.generate_one, args.arm)
        if args.stage in ('all', 'select'):
            verify(root, args.source, args.provider)
            for j in manifest['jobs']:
                read_json(root / 'candidates' / (j['id'] + '.json'))
            pool_run(evaluation_job, [(str(root), 'child', j['id']) for j in manifest['jobs']], args.workers, root, 'select', True)
            seal_selections(root, manifest)
            write_arm_logs(root, manifest)
        if args.stage in ('all', 'holdout'):
            verify(root, args.source, args.provider)
            release_parents(root, args.source, manifest)
            pool_run(holdout_job, [(str(root), 'child', j['id']) for j in manifest['jobs']], args.workers, root, 'holdout', True)
            write_arm_logs(root, manifest)
            complete(root, candidates=len(manifest['jobs']), contexts=len({j['context'] for j in manifest['jobs']}),
                     new_initial_calls=0)


if __name__ == '__main__':
    main()
