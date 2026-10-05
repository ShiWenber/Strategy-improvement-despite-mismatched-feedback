"""Deployment counterfactuals and fixed-library cultural evolution."""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed, TimeoutError
from itertools import product
import json
from pathlib import Path
import time

import numpy as np

from .collective_welfare import ROOT, ARMS, read, write
from .core import seed_for


def load_matrices(root, spec):
    size = len(spec['codes'])
    A, C, CC = [np.full((size, size), np.nan) for _ in range(3)]
    failures, games = [], 0
    for i, j in spec['pairs']:
        record = read(root / 'pairs' / f"s{spec['seed']}" / f'{i:03d}_{j:03d}.json')
        failures.extend(record['failures']); games += len(record['games'])
        if record['failures']:
            continue
        assert len(record['games']) == 5
        scores = np.mean([g['scores'] for g in record['games']], axis=0) / 100
        cooperation = np.mean([g['cooperation'] for g in record['games']], axis=0)
        joint = np.mean([g['joint_cooperation'] for g in record['games']])
        if i == j:
            A[i, i], C[i, i] = scores.mean(), cooperation.mean()
        else:
            A[i, j], A[j, i] = scores
            C[i, j], C[j, i] = cooperation
        CC[i, j] = CC[j, i] = joint
    bad = {f['code_index'] for f in failures}
    entities = spec['entities']
    fallback = entities['fallback_alld']['code_index']
    assert fallback not in bad
    def resolve(identity):
        item = entities[identity]
        return resolve(item['parent']) if item['code_index'] in bad else item['code_index']
    resolved = {identity: resolve(identity) for identity in entities}
    audit = {'seed': spec['seed'], 'successful_games': games,
             'failed_pairs': len(failures), 'failing_code_indices': sorted(bad),
             'affected_entities': [i for i, e in entities.items() if e['code_index'] in bad],
             'failure_records': failures}
    return (A, C, CC), resolved, audit


def state_metrics(matrices, ids):
    idx = np.asarray(ids)
    n = len(idx)
    mask = ~np.eye(n, dtype=bool)
    values = [m[np.ix_(idx, idx)][mask].mean() for m in matrices]
    assert all(np.isfinite(values))
    assert abs(values[0] - (1 + 3 * values[1] - values[2])) < 1e-10
    assert 1 - 1e-10 <= values[0] <= 3 + 1e-10
    return dict(zip(['welfare', 'cooperation', 'mutual_cooperation'], map(float, values)))


def deployment(spec, matrices, resolved):
    original = [resolved[i] for i in spec['initial']]
    baseline = state_metrics(matrices, original)
    A = matrices[0]
    rows = []
    for group in spec['groups']:
        slots = [int(i) for i in group['children']]
        assignments = {'R': [dict(zip(slots, choices)) for choices in product(*group['children'].values())]}
        for rule, chosen in group['selected'].items():
            assignments[rule] = [{int(k): v for k, v in chosen.items()}]
        for policy, alternatives in assignments.items():
            measurements = []
            for assign in alternatives:
                current = list(original)
                private, external = [], []
                for slot, entity in assign.items():
                    child, parent = resolved[entity], original[slot]
                    opponents = original[:slot] + original[slot+1:]
                    private.append(float(np.mean(A[child, opponents] - A[parent, opponents])))
                    external.append(float(np.mean(A[opponents, child] - A[opponents, parent])))
                    current[slot] = child
                current_m = state_metrics(matrices, current)
                measurements.append({**current_m,
                    'private_gain': np.mean(private), 'opponent_gain': np.mean(external),
                    'changed_slots': sum(a != b for a, b in zip(current, original)),
                    'sum_isolated_welfare_gain': sum(p+e for p, e in zip(private, external))/12})
            result = {k: float(np.mean([m[k] for m in measurements])) for k in measurements[0]}
            result.update(seed=spec['seed'], mode=group['mode'], arm=group['arm'], policy=policy)
            for k, value in baseline.items():
                result['baseline_'+k] = value
                result['delta_'+k] = result[k] - value
            result['interaction_residual'] = result['delta_welfare'] - result['sum_isolated_welfare_gain']
            result['joint_harm'] = bool(result['private_gain'] > 0 and result['delta_welfare'] < 0
                                        and result['delta_cooperation'] < 0)
            result['low_state'] = float(np.mean([m['welfare'] < 1.5 and m['cooperation'] < .2
                                                for m in measurements]))
            rows.append(result)
    return baseline, rows


def assemble(root, available=False):
    manifest = read(root / 'manifest.json')
    rows, baselines, audits, dynamics_jobs = [], [], [], []
    (root / 'matrices').mkdir(exist_ok=True)
    for spec in manifest['specifications']:
        if available and any(not (root/'pairs'/f"s{spec['seed']}"/f'{i:03d}_{j:03d}.json').exists()
                             for i,j in spec['pairs']):
            continue
        matrices, resolved, audit = load_matrices(root, spec)
        baseline, deploy = deployment(spec, matrices, resolved)
        rows.extend(deploy); baselines.append({'seed': spec['seed'], **baseline}); audits.append(audit)
        for group in spec['groups']:
            idx = [resolved[i] for i in group['local_entities']]
            local = [m[np.ix_(idx, idx)] for m in matrices]
            assert all(np.isfinite(m).all() for m in local)
            assert np.max(np.abs((local[0]+local[0].T)/2 - (1+1.5*(local[1]+local[1].T)-local[2]))) < 1e-10
            name = f"s{spec['seed']}_{group['mode']}_{group['arm']}"
            np.savez_compressed(root / 'matrices' / f'{name}.npz', A=local[0], C=local[1], CC=local[2])
            dynamics_jobs.append({'name': name, 'seed': spec['seed'], 'mode': group['mode'], 'arm': group['arm']})
    write(root / 'deployment.json', {'baselines': baselines, 'rows': rows, 'complete':len(baselines)==20})
    write(root / 'matrix_audit.json', {'populations': audits,
          'successful_games': sum(r['successful_games'] for r in audits),
          'failed_pairs': sum(r['failed_pairs'] for r in audits), 'welfare_identity_passed': True})
    write(root / 'dynamics_jobs.json', {'jobs': dynamics_jobs, 'settings': manifest['dynamics']})
    print(json.dumps({'assembled': len(dynamics_jobs), 'deployment_rows': len(rows),
                      'successful_games': sum(r['successful_games'] for r in audits),
                      'failed_pairs': sum(r['failed_pairs'] for r in audits)}), flush=True)


def population_metrics(states, A, C, CC, k):
    batches, n = states.shape
    counts = np.bincount((states + k*np.arange(batches)[:, None]).ravel(), minlength=batches*k).reshape(batches, k)
    payoffs = (counts @ A.T - np.diag(A))/(n-1)
    welfare = np.sum(counts*payoffs, axis=1)/n
    cooperation = np.sum(counts*(counts @ C.T - np.diag(C)), axis=1)/(n*(n-1))
    mutual = np.sum(counts*(counts @ CC.T - np.diag(CC)), axis=1)/(n*(n-1))
    diversity = 1 - np.sum((counts/n)**2, axis=1)
    child_share = counts[:, 12:].sum(axis=1)/n
    values = np.stack([welfare, cooperation, mutual, diversity, child_share], axis=-1)
    return payoffs, values, counts


def dynamic_job(args):
    root, job, settings = args
    root = Path(root); out = root / 'dynamics' / (job['name'] + '.npz')
    if out.exists():
        return {'name': job['name'], 'cached': True}
    mat = np.load(root / 'matrices' / (job['name'] + '.npz'))
    A, C, CC = (mat[k] for k in ('A', 'C', 'CC'))
    n, reps, steps, stride = (settings[k] for k in ['size','replicates','generations','record_every'])
    beta = np.repeat(settings['beta'], reps)
    k = len(A); branches = len(settings['beta'])
    states = np.tile(np.repeat(np.arange(k), n//k), (branches*reps, 1))
    assert n % k == 0
    rng = np.random.default_rng(seed_for(job['seed'], 'cultural-update', job['mode'], job['arm']))
    timeline = np.empty((branches*reps, steps//stride+1, 5))
    tail = np.zeros((branches*reps, 5)); prior_tail = np.zeros_like(tail)
    low_tail = np.zeros(branches*reps); gap_tail = np.zeros(branches*reps)
    positions = np.arange(n)[None, :]
    for t in range(steps+1):
        payoff, metrics, counts = population_metrics(states, A, C, CC, k)
        if t % stride == 0:
            timeline[:, t//stride] = metrics
        if steps-100 < t <= steps:
            tail += metrics/100
            low_tail += ((metrics[:,0] < 1.5) & (metrics[:,1] < .2))/100
        if steps-200 < t <= steps-100:
            prior_tail += metrics/100
        if t == steps:
            break
        peer = rng.integers(0, n-1, size=(reps,n)); peer += peer >= positions
        peer = np.tile(peer, (branches, 1))
        other_types = np.take_along_axis(states, peer, axis=1)
        gap = np.take_along_axis(payoff, other_types, axis=1) - np.take_along_axis(payoff, states, axis=1)
        chance = 1/(1+np.exp(-beta[:,None]*gap/5))
        accepted = np.tile(rng.random((reps,n)), (branches,1)) < chance
        states = np.where(accepted, other_types, states)
        if steps-100 <= t < steps:
            gap_tail += np.sum(accepted*gap, axis=1)/np.maximum(accepted.sum(axis=1),1)/100
        mutation = np.tile(rng.random((reps,n)) < settings['mutation'], (branches,1))
        replacement = np.tile(rng.integers(0,k,(reps,n)), (branches,1))
        states = np.where(mutation, replacement, states)
    assert np.max(np.abs(timeline[:,:,0] - (1+3*timeline[:,:,1]-timeline[:,:,2]))) < 1e-10
    out.parent.mkdir(exist_ok=True)
    np.savez_compressed(out, timeline=timeline.reshape(branches,reps,-1,5),
                        tail=tail.reshape(branches,reps,5), prior_tail=prior_tail.reshape(branches,reps,5),
                        low_tail=low_tail.reshape(branches,reps), copied_payoff_gap=gap_tail.reshape(branches,reps),
                        final_frequencies=(counts/n).reshape(branches,reps,k), beta=settings['beta'],
                        times=np.arange(0,steps+1,stride))
    return {'name': job['name'], 'cached': False}


def run_dynamics(root, workers):
    spec = read(root / 'dynamics_jobs.json'); start = time.monotonic()
    jobs = [(str(root), j, spec['settings']) for j in spec['jobs']]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(dynamic_job,j) for j in jobs]
        try:
            for n,f in enumerate(as_completed(futures,timeout=2700),1):
                f.result()
                if n % 10 == 0 or n == len(jobs):
                    status = {'phase':'dynamics','completed':n,'total':len(jobs),'elapsed_seconds':round(time.monotonic()-start,1)}
                    write(root/'DYNAMICS_PROGRESS.json',status);print(json.dumps(status),flush=True)
        except TimeoutError:
            write(root/'DYNAMICS_TIMEOUT.json',{'seconds':time.monotonic()-start})
            print('Hard 45-minute time limit reached; terminating dynamics workers.',flush=True)
            for process in pool._processes.values():process.terminate()
            raise
    write(root/'DYNAMICS_COMPLETE.json',{'seconds':time.monotonic()-start,'jobs':len(jobs)})


def verify_analysis(root):
    # ALLC/ALLD population: compare aggregate formulas to enumeration.
    A=np.array([[3.,0.],[5.,1.]]);C=np.array([[1.,1.],[0.,0.]]);CC=np.array([[1.,0.],[0.,0.]])
    states=np.array([[0,0,1,1],[0,0,0,0],[1,1,1,1]])
    payoff,metrics,_=population_metrics(states,A,C,CC,2)
    for t,state in enumerate(states):
        expected=state_metrics((A,C,CC),state)
        assert np.allclose(metrics[t,:3],list(expected.values()))
    # Uniformly selecting another member excludes its own index exactly.
    for i in range(4):
        peers=np.arange(3);peers+=peers>=i
        assert sorted(peers)==[j for j in range(4) if j!=i]
    assert np.allclose(1/(1+np.exp(-0*(A-A.T))),.5)
    assert abs(metrics[0,0]-(1+3*metrics[0,1]-metrics[0,2]))<1e-10
    checks=root/'synthetic_checks';(checks/'matrices').mkdir(parents=True,exist_ok=True)
    settings={'size':40,'replicates':50,'generations':300,'record_every':10,'beta':[0,1,5],'mutation':.0025}
    for name,aa,cc,mm in [('equal_fitness',np.ones((2,2))*3,np.ones((2,2)),np.ones((2,2))),
                          ('alld_invasion',A,C,CC)]:
        np.savez_compressed(checks/'matrices'/f'{name}.npz',A=aa,C=cc,CC=mm)
        dynamic_job((str(checks),{'name':name,'seed':800,'mode':'control','arm':'control'},settings))
    equal=np.load(checks/'dynamics/equal_fitness.npz')
    assert np.array_equal(equal['final_frequencies'][0],equal['final_frequencies'][1])
    assert np.array_equal(equal['final_frequencies'][0],equal['final_frequencies'][2])
    control=np.load(checks/'dynamics/alld_invasion.npz')['tail'].mean(axis=1)
    assert control[2,1] < control[0,1]-.2
    # Three ALLD revisions in an ALLC population create the expected private/group conflict.
    spec={'seed':0,'initial':['parent']*12,'groups':[{'mode':'control','arm':'control',
        'children':{'0':['child','child'],'2':['child','child'],'5':['child','child']},
        'selected':{'S2':{'0':'child','2':'child','5':'child'}}}]}
    baseline, deployed=deployment(spec,(A,C,CC),{'parent':0,'child':1})
    chosen=next(r for r in deployed if r['policy']=='S2')
    assert np.isclose(chosen['private_gain'],2) and np.isclose(chosen['opponent_gain'],-3)
    assert np.isclose(chosen['cooperation'],.75)
    assert np.isclose(chosen['welfare'],(36*6+27*5+3*2)/(66*2))
    assert chosen['joint_harm'] and baseline['welfare']==3
    return {'explicit_population_enumeration':True,'no_individual_self_match':True,
            'neutral_imitation_probability':True,'payoff_identity':True,
            'equal_fitness_treatments_identical':True,
            'alld_invasion_positive_control_cooperation':control[:,1].tolist(),
            'individual_group_conflict_positive_control':True}


def main():
    p=argparse.ArgumentParser();p.add_argument('phase',choices=['assemble','dynamics','verify'])
    p.add_argument('--root',type=Path,default=ROOT);p.add_argument('--workers',type=int,default=12)
    p.add_argument('--available',action='store_true',help='Assemble only fully evaluated populations while independent jobs continue')
    a=p.parse_args()
    if a.phase=='assemble':assemble(a.root,a.available)
    elif a.phase=='dynamics':run_dynamics(a.root,a.workers)
    else:
        result=verify_analysis(a.root);write(a.root/'ANALYSIS_ENGINE_CHECK.json',result);print(result)


if __name__=='__main__':
    main()
