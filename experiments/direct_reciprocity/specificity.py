"""Paired report prompts, strategy generation, selection scores and holdout games."""
from dataclasses import asdict, replace
import json
from pathlib import Path
from statistics import mean

from tools.direct_reciprocity.records import read_json, write_json, population_root, require_holdout
from .core import Config, Policy, evaluate, match, seed_for, versus
from .baselines import TRAIN
from .report_assignment import derangement
from .prompts import build_prompt
from .run import Generator
from .specificity_assets import ARMS, RANKS, panel, probes, diagnostic_block, tokenizer

DEFAULT_ROOT = 'results/feedback_specificity_v2'


def cfg_for(seed):
    return Config(seed=seed)


def init_prompt(seed, slot):
    return build_prompt(cfg_for(seed)) + f'\nIndependent candidate {slot}; replicate {seed}.\n'


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
    return contexts
