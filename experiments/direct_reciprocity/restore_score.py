"""Restore historical Score records after validating the complete source projection."""
import argparse
from collections import Counter
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
import shutil
import tempfile

from .core import Policy
from .records import digest, filehash, read_json, write_json
from .specificity import seal_selections
from .specificity_assets import ARMS, SCORE_ARMS

RUNS = ('feedback_specificity_v2', 'feedback_specificity_thinking_384k_20260923',
        'qwen3_8/off', 'qwen3_8/on')
FOLDERS = ('requests_candidates', 'candidates', 'selection_scores', 'holdout')
ROOT = Path(__file__).resolve().parents[2]


def verify_restoration(root):
    """Verify the receipt and byte identities without the original private checkout."""
    root = Path(root)
    manifest = read_json(root / 'manifest.json')
    expected = manifest.get('archive_projection', {}).get('restore_receipt_sha256')
    if expected is None:
        return
    if filehash(root / 'SCORE_RESTORE.json') != expected:
        raise RuntimeError('Score restoration receipt changed')
    receipt = read_json(root / 'SCORE_RESTORE.json')
    for relative, expected_hash in receipt['record_sha256'].items():
        path = (root / relative).resolve()
        if not path.is_relative_to(root.resolve()) or filehash(path) != expected_hash:
            raise RuntimeError('Restored archive record changed: ' + relative)


def copy_record(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)


def project_run(source, current, staged, source_parent):
    old = read_json(source / 'manifest.json')
    existing = read_json(current / 'manifest.json')
    original_hash = filehash(source / 'manifest.json')
    if existing.get('archive_projection', {}).get('source_manifest_sha256') != original_hash:
        raise RuntimeError('Source manifest is not the recorded historical origin: ' + str(source))
    for key in ('seeds', 'ranks', 'draws', 'config'):
        if old[key] != existing[key]:
            raise RuntimeError('Historical pairing differs: ' + key)
    if existing['arms'] != list(ARMS):
        raise RuntimeError('Destination must contain the two matching conditions')
    jobs = [j for j in old['jobs'] if j['arm'] in SCORE_ARMS]
    if [j for j in jobs if j['arm'] in ARMS] != existing['jobs']:
        raise RuntimeError('Matching task identities differ from historical source')
    contexts = sorted({j['context'] for j in jobs})
    counts = Counter((j['context'], j['arm']) for j in jobs)
    if len(jobs) != len(contexts) * len(SCORE_ARMS) * old['draws'] or any(
            counts[cid, arm] != old['draws'] for cid in contexts for arm in SCORE_ARMS):
        raise RuntimeError('Incomplete or duplicate historical Score pools')
    seal = read_json(source / 'SELECTIONS_SEALED.json')
    if read_json(source / 'H_RELEASED.json')['selection_digest'] != digest(
            (source / 'SELECTIONS_SEALED.json').read_text(encoding='utf-8')):
        raise RuntimeError('Historical holdout release does not match selection seal')
    records, imported = {}, []
    known = {j['id'] for j in existing['jobs']}
    for folder in FOLDERS:
        permitted = known | (set(contexts) if folder in ('selection_scores', 'holdout') else set())
        if {p.stem for p in (current / folder).glob('*.json')} != permitted:
            raise RuntimeError('Unexpected or missing destination records: ' + folder)
        for job in jobs:
            relative = f"{folder}/{job['id']}.json"
            path = source / relative
            sha = filehash(path)
            if job['arm'] in ARMS and filehash(current / relative) != sha:
                raise RuntimeError('Matching record differs: ' + relative)
            records[relative] = sha
            if job['arm'] == 'score':
                imported.append(relative)
            copy_record(path, staged / relative)
    shared = [f'populations/s{seed}.json' for seed in old['seeds']]
    shared += [f'{folder}/{cid}.json' for folder in ('selection_scores', 'holdout') for cid in contexts]
    shared += [f"{folder}/{j['id']}.json" for folder in ('initial', 'requests_initial') for j in old.get('init_jobs', [])]
    for relative in shared:
        sha = filehash(source / relative)
        if filehash(current / relative) != sha:
            raise RuntimeError('Shared population or parent differs: ' + relative)
        records[relative] = sha
        copy_record(current / relative, staged / relative)
    for cid in contexts:
        c = read_json(source / 'contexts' / (cid + '.json'))
        before = read_json(current / 'contexts' / (cid + '.json'))
        for key, value in before.items():
            if key in ('prompts', 'block_tokens'):
                if any(c[key][arm] != value[arm] for arm in ARMS):
                    raise RuntimeError('Matching prompt differs: ' + cid)
            elif c[key] != value:
                raise RuntimeError('Parent context differs: ' + cid)
        c['prompts'] = {arm: c['prompts'][arm] for arm in SCORE_ARMS}
        c['block_tokens'] = {arm: c['block_tokens'][arm] for arm in SCORE_ARMS}
        if c['block_tokens']['score'] != 0:
            raise RuntimeError('Historical Score has a nonempty report block')
        write_json(staged / 'contexts' / (cid + '.json'), c)
    for job in jobs:
        request = read_json(staged / 'requests_candidates' / (job['id'] + '.json'))
        child = read_json(staged / 'candidates' / (job['id'] + '.json'))
        context = read_json(staged / 'contexts' / (job['context'] + '.json'))
        outcome = read_json(staged / 'holdout' / (job['id'] + '.json'))
        parent = read_json(staged / 'holdout' / (job['context'] + '.json'))
        if request['prompt'] != context['prompts'][job['arm']] or child['valid'] != (request['status'] == 'valid'):
            raise RuntimeError('Prompt or validity mismatch: ' + job['id'])
        if child['parent_key'] != Policy(**context['parent']).key:
            raise RuntimeError('Parent code identity mismatch: ' + job['id'])
        if child['child'] and Policy(**child['child']).key != request['code_hash']:
            raise RuntimeError('Response code identity mismatch: ' + job['id'])
        if seal['candidate_hashes'][job['id']] != digest((staged / 'candidates' / (job['id'] + '.json')).read_text(encoding='utf-8')):
            raise RuntimeError('Historical candidate seal mismatch: ' + job['id'])
        for setting in ('default', 'noise01', 'long'):
            for metric in ('score', 'cooperation', 'worst_score'):
                delta = outcome['deployed'][setting][metric] - parent['measured'][setting][metric]
                if abs(delta - outcome['delta'][setting][metric]) > 1e-10 or (
                        outcome['fallback'][setting] and abs(delta) > 1e-10):
                    raise RuntimeError('Outcome or fallback arithmetic mismatch: ' + job['id'])
    stamp = datetime.now(timezone(timedelta(hours=8))).isoformat()
    receipt = {'restored_at': stamp, 'source_manifest_sha256': original_hash,
               'original_implementation_hash': old['implementation_hash'],
               'imported_score_records': imported, 'record_sha256': records,
               'new_model_calls': 0, 'new_games': 0}
    write_json(staged / 'SCORE_RESTORE.json', receipt)
    manifest = dict(existing, arms=list(SCORE_ARMS), jobs=jobs)
    manifest['archive_projection'] = dict(existing['archive_projection'],
        restored_at=stamp, restored_conditions=list(SCORE_ARMS),
        restore_receipt_sha256=filehash(staged / 'SCORE_RESTORE.json'),
        scope='Historical matching and Score records; original IDs, positions, times and implementation provenance. Container hashes describe the restored projection.')
    if 'arm_position_permutations' in old:
        manifest['arm_position_permutations'] = {s: [a for a in aa if a in SCORE_ARMS]
                                                 for s, aa in old['arm_position_permutations'].items()}
    if 'retained_calls' in manifest:
        manifest['retained_calls'] = {'initial': len(old['init_jobs']), 'candidates': len(jobs), 'total': len(old['init_jobs']) + len(jobs)}
    else:
        manifest['retained_candidate_calls'] = len(jobs)
        manifest['source_manifest_hash'] = filehash(source_parent / 'manifest.json')
        manifest['reused_file_hashes'] = {rel: filehash(staged / rel) for rel in existing['reused_file_hashes']}
        manifest['prompt_hashes'] = {j['id']: digest(read_json(staged / 'contexts' / (j['context'] + '.json'))['prompts'][j['arm']]) for j in jobs}
    write_json(staged / 'manifest.json', manifest)
    selected = seal_selections(staged, manifest, readonly=True)
    old_rows = {(r['context'], r['arm'], r['rule']): r for r in seal['rows']}
    if any(r != old_rows[r['context'], r['arm'], r['rule']] for r in selected['rows']):
        raise RuntimeError('Reconstructed selection differs from historical decision')
    selected['archive_projection'] = {'source_sha256': filehash(source / 'SELECTIONS_SEALED.json'), 'restored_at': stamp}
    write_json(staged / 'SELECTIONS_SEALED.json', selected)
    release = read_json(current / 'H_RELEASED.json')
    release['selection_digest'] = digest((staged / 'SELECTIONS_SEALED.json').read_text(encoding='utf-8'))
    write_json(staged / 'H_RELEASED.json', release)
    completion = read_json(current / 'COMPLETE.json')
    completion.update(candidates=len(jobs), contexts=len(contexts))
    write_json(staged / 'COMPLETE.json', completion)
    if (current / 'PROMPTS_SEALED.json').exists():
        prompt_seal = read_json(source / 'PROMPTS_SEALED.json')
        prompt_seal['rows'] = [r for r in prompt_seal['rows'] if r['id'] in {j['id'] for j in jobs}]
        prompt_seal['contexts'] = {cid: digest(json.dumps(read_json(staged / 'contexts' / (cid + '.json')), sort_keys=True)) for cid in contexts}
        prompt_seal['archive_projection'] = {'source_sha256': filehash(source / 'PROMPTS_SEALED.json'), 'restored_at': stamp}
        write_json(staged / 'PROMPTS_SEALED.json', prompt_seal)
    verify_restoration(staged)
    changed = imported + [f'contexts/{cid}.json' for cid in contexts]
    changed += ['manifest.json', 'SCORE_RESTORE.json', 'SELECTIONS_SEALED.json', 'H_RELEASED.json', 'COMPLETE.json']
    if (staged / 'PROMPTS_SEALED.json').exists():
        changed.append('PROMPTS_SEALED.json')
    return {'contexts': len(contexts), 'score_candidates': sum(j['arm'] == 'score' for j in jobs),
            'candidates': len(jobs), 'selection_decisions': len(selected['rows']), 'changed': changed}


def restore(source, work=ROOT, apply=False):
    source, work = Path(source).resolve(), Path(work).resolve()
    if source == work or source.is_relative_to(work) or work.is_relative_to(source):
        raise ValueError('Source and destination checkouts must be separate')
    already = [(work / 'results' / run / 'SCORE_RESTORE.json').exists() for run in RUNS]
    if any(already):
        if not all(already):
            raise RuntimeError('Partial restore; inspect the recorded backup before continuing')
        for run in RUNS:
            target = work / 'results' / run
            verify_restoration(target)
            if read_json(target / 'SCORE_RESTORE.json')['source_manifest_sha256'] != filehash(source / 'results' / run / 'manifest.json'):
                raise RuntimeError('Historical source changed after restoration')
        return {'status': 'already_restored', 'new_model_calls': 0, 'new_games': 0}
    temp_root = work / 'tmp'
    temp_root.mkdir(exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='score_restore_', dir=temp_root))
    summaries = {}
    for run in RUNS:
        summaries[run] = project_run(source / 'results' / run, work / 'results' / run,
                                     stage / 'results' / run, stage / 'results' / RUNS[0])
    report = {'status': 'validated', 'source': str(source), 'backup': str(stage / 'before'),
              'runs': summaries, 'new_model_calls': 0, 'new_games': 0}
    if not apply:
        return report
    installed = []
    try:
        for run, summary in summaries.items():
            for relative in summary['changed']:
                target = work / 'results' / run / relative
                backup = stage / 'before' / run / relative
                exists = target.exists()
                if exists:
                    copy_record(target, backup)
                installed.append((target, backup, exists))
                copy_record(stage / 'results' / run / relative, target)
        for run in RUNS:
            verify_restoration(work / 'results' / run)
    except Exception:
        for target, backup, exists in reversed(installed):
            if exists:
                copy_record(backup, target)
            elif target.exists():
                target.unlink()
        raise
    report['status'] = 'restored'
    write_json(work / 'results/reproduction/SCORE_RESTORE.json', report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True, help='Original checkout; always read-only')
    parser.add_argument('--work', type=Path, default=ROOT)
    parser.add_argument('--apply', action='store_true', help='Install after validating all four configurations')
    args = parser.parse_args()
    result = restore(args.source, args.work, args.apply)
    print(json.dumps({k: v for k, v in result.items() if k != 'runs'}))


if __name__ == '__main__':
    main()
