"""Budget-matched independent sampling, selected only on each reference training environment."""
import argparse
from dataclasses import asdict, replace
from pathlib import Path
from statistics import mean
from .core import Config, Policy, match, seed_for, versus, ranking
from .baselines import TRAIN, TEST
from .recover_evaluation import tolerate_holdout_failure
from .prompts import build_prompt
from .run import Generator, read_json, write_json
from .diagnostics import implementation_hash, request_budget


def hypothetical_fitness(candidate, slot, population, archive, cfg, generation):
    peer=[]
    for j,opponent in enumerate(population):
        if j==slot:
            continue
        i,k=sorted((slot,j))
        for repeat in range(cfg.repeats):
            seed=seed_for(cfg.seed,'peer',generation,i,k,repeat)
            if slot<j:
                peer.append(match(candidate,opponent,cfg,seed)['scores'][0])
            else:
                peer.append(match(opponent,candidate,cfg,seed)['scores'][1])
    external=versus(candidate,archive,cfg,'archive',generation)
    return cfg.peer_weight*mean(peer)+(1-cfg.peer_weight)*external['score']


def run_control(root,seed,available_only=False,evaluation_workers=1):
    root=Path(root)
    manifest=read_json(root/'matrix_plan.json')
    if manifest['implementation_hash']!=implementation_hash():
        raise RuntimeError('Reference engine changed; cannot compare using another implementation')
    cells=[cell for cell in manifest['cells'] if cell['seed']==seed]
    references=[]
    for cell in cells:
        name=f"{cell['prompt']}__{cell['selection']}__seed{seed}"
        directory=root/name
        if not (directory/'complete.json').exists():
            if available_only:
                continue
            raise RuntimeError('Complete every reference cell for this seed before running control')
        state=read_json(directory/f"generation_{manifest['generations']-1:03d}.json")
        if state['status']!='complete':
            raise RuntimeError('Reference endpoint is incomplete')
        references.append((name,directory,state))
    if not references:
        raise RuntimeError('No complete reference cell is available for this seed')
    cfg=Config(**read_json(references[0][1]/'config.json')['config'])
    cfg=replace(cfg,prompt='minimal',selection='paper_truncation')
    initial=[Policy(**p) for p in read_json(references[0][1]/'generation_000.json')['population']]
    initial_keys=[p.key for p in initial]
    for _,directory,_ in references:
        other=read_json(directory/'generation_000.json')['population']
        if [Policy(**p).key for p in other]!=initial_keys:
            raise RuntimeError('Reference conditions do not share initialization')
    control=root/'independent_control'/f'seed{seed}'
    control.mkdir(parents=True,exist_ok=True)
    initial_path=read_json(references[0][1]/'initial_reference.json')['path']
    initial_requests=request_budget([initial_path])['requests']
    budget=max(state['budget_at_evaluation']['requests'] for _,_,state in references)
    pool_size=len(initial)+budget-initial_requests
    generator=Generator(control/'requests',manifest['provider'],manifest['model'],cfg.temperature)
    pool=list(initial)
    for ordinal in range(len(initial),pool_size):
        prompt=build_prompt(cfg)+f'\nIndependent control candidate {ordinal}; replicate {seed}.\n'
        candidate=generator.generate(f'sample{ordinal:04d}',prompt,cfg)
        pool.append(candidate)
    write_json(control/'pool.json',{'policies':[asdict(p) if p else None for p in pool],
                                  'initial_keys':initial_keys,'max_request_budget':budget,
                                  'shared_initial_requests':initial_requests,
                                  'independent_request_budget':request_budget([control/'requests'])})
    for name,directory,state in references:
        output=control/(name+'.json')
        if output.exists():
            continue
        population=[Policy(**p) for p in state['population']]
        generation=state['generation']
        archive=TRAIN if generation==0 else [Policy(**p) for p in read_json(directory/f'generation_{generation-1:03d}.json')['next_archive']]
        slot=ranking(population,state['assessment'])[0]
        request_limit=state['budget_at_evaluation']['requests']
        limit=len(initial)+request_limit-initial_requests
        checkpoint=control/(name+'_selection.json')
        selection=read_json(checkpoint) if checkpoint.exists() else []
        from .control_scoring import score_candidates
        for result in score_candidates(pool,len(selection),limit,slot,population,archive,cfg,generation,evaluation_workers):
            selection.append(result)
            write_json(checkpoint,selection)
        valid=[r for r in selection if r['fitness'] is not None]
        if not valid:
            raise RuntimeError('No executable independent candidate for '+name)
        winner=min(valid,key=lambda r:(-r['fitness'],r['key'],r['ordinal']))
        champion=pool[winner['ordinal']]
        tests={}
        for label,rounds,noise in [('default',cfg.rounds,0),('noise01',cfg.rounds,0.01),('long',2*cfg.rounds,0)]:
            tests[label]=tolerate_holdout_failure(champion,TEST,replace(cfg,rounds=rounds,noise=noise),'holdout-'+label,generation)
        write_json(output,{'reference':name,'seed':seed,'request_budget':request_limit,'candidate_pool_size':limit,
                           'champion':asdict(champion),'training_fitness':winner['fitness'],
                           'holdout':tests,'selection_errors':sum('error' in r for r in selection),
                           'note':'Independent proposals; selection uses frozen reference peer/archive environment. Matches request count, not tokens or evaluation compute.'})
        print(f'Independent control complete: {name}',flush=True)



def prepare_control(root,seed):
    """Generate the guaranteed truncation-budget prefix without any fitness feedback."""
    root=Path(root)
    manifest=read_json(root/'matrix_plan.json')
    if manifest['implementation_hash']!=implementation_hash():
        raise RuntimeError('Reference implementation changed')
    reference=root/f'minimal__paper_truncation__seed{seed}'
    cfg=Config(**read_json(reference/'config.json')['config'])
    cfg=replace(cfg,prompt='minimal',selection='paper_truncation')
    directory=root/'independent_control'/f'seed{seed}'
    generator=Generator(directory/'requests',manifest['provider'],manifest['model'],cfg.temperature)
    number=cfg.eliminate*(cfg.generations-1)
    valid=0
    for ordinal in range(cfg.population_size,cfg.population_size+number):
        prompt=build_prompt(cfg)+f'\nIndependent control candidate {ordinal}; replicate {seed}.\n'
        candidate=generator.generate(f'sample{ordinal:04d}',prompt,cfg)
        valid+=candidate is not None
        write_json(directory/'preparation_progress.json',{'seed':seed,'attempted':ordinal-cfg.population_size+1,
                   'target':number,'valid':valid,'status':'preparing','selection_performed':False})
        if (ordinal-cfg.population_size+1)%10==0:
            print(f'Control proposal preparation seed={seed}: {ordinal-cfg.population_size+1}/{number}',flush=True)
    write_json(directory/'preparation_progress.json',{'seed':seed,'attempted':number,'target':number,
               'valid':valid,'status':'prepared','selection_performed':False})
    print(f'Control proposals prepared seed={seed}: {valid}/{number} executable',flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root',type=Path)
    parser.add_argument('--seed',type=int)
    parser.add_argument('--prepare-only',action='store_true')
    parser.add_argument('--available-only',action='store_true',
                        help='Evaluate completed reference cells now; rerun later for the remaining cells')
    parser.add_argument('--seeds',type=int,nargs='+')
    parser.add_argument('--workers',type=int,default=2)
    parser.add_argument('--evaluation-workers',type=int,default=1)
    parser.add_argument('--env-file',type=Path)
    args=parser.parse_args()
    if args.evaluation_workers<1:
        parser.error('--evaluation-workers must be positive')
    if args.env_file:
        from dotenv import load_dotenv
        load_dotenv(args.env_file,override=False)
    if args.prepare_only:
        if args.available_only:
            parser.error('--available-only is for evaluation, not proposal preparation')
        from concurrent.futures import ThreadPoolExecutor, as_completed
        seeds=args.seeds if args.seeds is not None else [args.seed]
        if any(seed is None for seed in seeds) or len(seeds)!=len(set(seeds)) or args.workers<1:
            parser.error('Specify unique --seeds or --seed and positive --workers')
        errors=[]
        with ThreadPoolExecutor(max_workers=min(args.workers,len(seeds))) as pool:
            futures={pool.submit(prepare_control,args.root,seed):seed for seed in seeds}
            for future in as_completed(futures):
                seed=futures[future]
                try:
                    future.result()
                except Exception as exc:
                    errors.append(seed)
                    write_json(args.root/'independent_control'/f'seed{seed}'/'preparation_failure.json',
                               {'error_type':type(exc).__name__,'message':str(exc)})
                    print(f'Control preparation failed seed={seed}: {type(exc).__name__}',flush=True)
        if errors:
            raise RuntimeError(f'Control preparation failed for seeds {errors}')
    else:
        if args.seed is None or args.seeds is not None:
            parser.error('Final control evaluation requires one --seed')
        from .process_lock import seed_lock
        with seed_lock(args.root, args.seed):
            run_control(args.root,args.seed,args.available_only,args.evaluation_workers)


if __name__=='__main__':
    main()
