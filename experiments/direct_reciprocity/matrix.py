"""Seed-serial, cross-seed concurrent scheduling avoids shared-init races."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
import subprocess
import sys
import time
from .records import write_json, read_json


def cells(seeds):
    return [{'seed':seed,'prompt':prompt,'selection':'paper_truncation'}
            for seed in seeds for prompt in ('minimal','score','full')]


def run_matrix(args,model):
    if args.workers < 1 or len(set(args.seeds)) != len(args.seeds):
        raise ValueError('workers must be positive and seeds unique')
    root=Path(args.output).resolve()
    manifest={'initial_source':str(args.initial_source.resolve()) if args.initial_source else None,'model':model,'provider':args.provider,
              'generations':args.generations,'population_size':args.population_size,
              'eliminate':args.eliminate,'rounds':args.rounds,'repeats':args.repeats,
              'cells':cells(args.seeds)}
    if args.dry_run:
        print(json.dumps(manifest,indent=2))
        return
    path=root/'matrix_plan.json'
    if path.exists() and read_json(path)!=manifest:
        raise RuntimeError('Matrix plan/source differs: choose a new output directory')
    write_json(path,manifest)
    def run_seed(seed):
        outcomes=[]
        for cell in (c for c in manifest['cells'] if c['seed']==seed):
            name=f"{cell['prompt']}__{cell['selection']}__seed{seed}"
            directory=root/name
            directory.mkdir(parents=True,exist_ok=True)
            command=[sys.executable,'-m','experiments.direct_reciprocity.run','--output',str(root),
                     '--provider',args.provider,'--model',model,'--seed',str(seed),
                     '--prompt',cell['prompt'],'--selection',cell['selection'],
                     '--population-size',str(args.population_size),'--eliminate',str(args.eliminate),
                     '--generations',str(args.generations),'--rounds',str(args.rounds),
                     '--repeats',str(args.repeats)]
            if args.initial_source:
                command.extend(['--initial-source',str(args.initial_source.resolve())])
            # Parent loaded environment before spawning; secrets never enter argv.
            with (directory/'process.log').open('a',encoding='utf-8') as log:
                process=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT)
                write_json(directory/'process.json',{'pid':process.pid,'started_at':time.time(),
                           'command':command,'status':'running'})
                code=process.wait()
            done=directory/'complete.json'
            status='complete' if code==0 and done.exists() else 'failed'
            write_json(directory/'process.json',{'pid':process.pid,'finished_at':time.time(),
                       'exit_code':code,'status':status})
            outcome={**cell,'status':status,'exit_code':code}
            outcomes.append(outcome)
            write_json(root/f'seed_{seed}_status.json',outcomes)
            print(json.dumps(outcome),flush=True)
        return outcomes
    completed=[]
    with ThreadPoolExecutor(max_workers=min(args.workers,len(args.seeds))) as pool:
        futures=[pool.submit(run_seed,seed) for seed in args.seeds]
        for future in as_completed(futures):
            completed.extend(future.result())
            write_json(root/'matrix_status.json',completed)
    if any(c['status']!='complete' for c in completed):
        raise RuntimeError('Some matrix cells failed; see per-cell logs and seed status files')
