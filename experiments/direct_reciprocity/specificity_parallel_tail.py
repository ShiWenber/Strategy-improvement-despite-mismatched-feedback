"""Additional local workers for the tail of a frozen evaluation queue.

No API access. Uses unchanged frozen measurement functions and input copies.
Publishes complete records atomically; any duplicate computations must agree.
All duplicated work is logged, never counted as additional statistical samples.
"""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import shutil
import time

from .core import digest
from .run import read_json, write_json
from .specificity import check_manifest, evaluation_job, holdout_job


def run(root, phase, count, workers):
    root = Path(root).resolve()
    manifest = check_manifest(root)
    if phase == 'holdout':
        read_json(root / 'H_RELEASED.json')
        for cid in {j['context'] for j in manifest['jobs']}:
            read_json(root / 'holdout' / (cid + '.json'))
    staging = root / ('parallel_' + phase)
    staging.mkdir(exist_ok=True)
    for directory in ('contexts', 'populations', 'candidates'):
        (staging / directory).mkdir(exist_ok=True)
        for path in (root / directory).glob('*.json'):
            destination = staging / directory / path.name
            if not destination.exists():
                shutil.copyfile(path, destination)
            if path.read_bytes() != destination.read_bytes():
                raise RuntimeError('Input copy differs')
    outdir = 'selection_scores' if phase == 'select' else 'holdout'
    if phase == 'holdout':
        shutil.copyfile(root / 'H_RELEASED.json', staging / 'H_RELEASED.json')
        (staging / 'holdout').mkdir(exist_ok=True)
        for cid in {j['context'] for j in manifest['jobs']}:
            shutil.copyfile(root / 'holdout' / (cid + '.json'), staging / 'holdout' / (cid + '.json'))
    jobs = [j for j in reversed(manifest['jobs']) if not (root / outdir / (j['id'] + '.json')).exists()][:count]
    fn = evaluation_job if phase == 'select' else holdout_job
    log = []
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fn, (str(staging), 'child', job['id'])): job for job in jobs}
        for future in as_completed(futures):
            job = futures[future]
            future.result()
            source = staging / outdir / (job['id'] + '.json')
            destination = root / outdir / (job['id'] + '.json')
            content = source.read_bytes()
            already = destination.exists()
            if already:
                if read_json(source) != read_json(destination):
                    raise RuntimeError('Deterministic parallel duplicate disagrees: ' + job['id'])
            else:
                # Distinct temp name cannot collide with the primary writer's .tmp.
                temp = destination.with_suffix('.parallel.tmp')
                temp.write_bytes(content)
                temp.replace(destination)
            log.append({'id': job['id'], 'already_completed_by_primary': already,
                        'record_hash': digest(content.decode('utf-8')), 'published_at': time.time()})
            write_json(staging / 'PUBLISH_LOG.json', {'phase': phase, 'scheduled': len(jobs), 'completed': len(log),
                                                      'workers': workers, 'records': log,
                                                      'note': 'Same frozen functions and streams; duplicates are extra compute, not extra samples.'})
            print({'phase': phase, 'parallel_completed': len(log), 'scheduled': len(jobs)}, flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=['select', 'holdout'])
    parser.add_argument('--root', default='results/feedback_specificity_v2')
    parser.add_argument('--count', type=int, default=300)
    parser.add_argument('--workers', type=int, default=24)
    args = parser.parse_args()
    run(args.root, args.phase, args.count, args.workers)
