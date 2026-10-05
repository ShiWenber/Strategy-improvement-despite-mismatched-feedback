"""Durable LLM request records and resumable generation-level experiments."""
from __future__ import annotations

import argparse
from dataclasses import asdict, replace
import json
from pathlib import Path
import time

from .core import Config, Policy, PolicyError, digest, evaluate, ranking, update_archive, versus, match
from .baselines import TRAIN, TEST
from .diagnostics import population_behavior, request_budget, implementation_hash
from .reuse import reuse_initial
from .selection import selection_plan
from .prompts import build_prompt
from ..config.load_env import get_api_key, get_base_url, get_model


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    temp = path.with_suffix(path.suffix+'.tmp')
    temp.write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding='utf-8')
    temp.replace(path)


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


class Generator:
    def __init__(self, directory, provider, model, temperature):
        self.directory = Path(directory)
        self.provider,self.model,self.temperature = provider,model,temperature
        self.client = None

    def generate(self, request_id, prompt, cfg):
        path = self.directory/(request_id+'.json')
        specification = {'prompt':prompt,'provider':self.provider,'model':self.model,
                         'temperature':self.temperature, 'max_tokens':6000,
                         'extra_body':{'thinking':{'type':'disabled'}} if self.provider=='deepseek' else {}}
        fingerprint=digest(json.dumps(specification,sort_keys=True))
        if path.exists():
            record=read_json(path)
            if record['fingerprint'] != fingerprint:
                raise RuntimeError('Request identity collision: '+str(path))
            if record['status']=='api_error':
                raise RuntimeError('API request failed previously; inspect '+str(path))
        else:
            if self.client is None:
                from openai import OpenAI
                key=get_api_key(self.provider)
                if not key:
                    raise RuntimeError('Provider not configured: '+self.provider)
                self.client=OpenAI(api_key=key,base_url=get_base_url(self.provider),
                                   timeout=180,max_retries=0)
            record={**specification,'fingerprint':fingerprint,'status':'requested',
                    'started_at':time.time()}
            # A pending record is never silently rerun after an uncertain response.
            write_json(path,record)
            try:
                response=self.client.chat.completions.create(model=self.model,
                    messages=[{'role':'user','content':prompt}],temperature=self.temperature,
                    max_tokens=6000, extra_body=specification['extra_body'])
                record.update(status='received',content=response.choices[0].message.content,
                              response_id=response.id,returned_model=response.model,
                              usage=response.usage.model_dump() if response.usage else None,
                              finish_reason=response.choices[0].finish_reason)
            except Exception as exc:
                record.update(status='api_error',error_type=type(exc).__name__)
                write_json(path,record)
                raise RuntimeError('API failure '+type(exc).__name__+'; request saved at '+str(path)) from None
            record['finished_at']=time.time()
            write_json(path,record)
        if record['status']=='requested':
            raise RuntimeError('Uncertain pending request; inspect provider status before retry: '+str(path))
        if record['status']=='invalid':
            return None
        if not record.get('content') or record.get('finish_reason') == 'length':
            record.update(status='invalid', validation_error='Missing or truncated program output', error_kind='incomplete_response')
            write_json(path,record)
            return None
        code=record.get('content') or ''
        if code.strip().startswith('```'):
            lines=code.strip().splitlines()
            if lines[-1].strip()=='```':
                code='\n'.join(lines[1:-1])
        policy=Policy(request_id,code)
        if record['status']=='valid':
            return policy
        try:
            policy.compile()
            for opponent in TRAIN:
                match(policy,opponent,replace(cfg,repeats=1),12345)
        except Exception as exc:
            record.update(status='invalid',validation_error=f'{type(exc).__name__}: {exc}')
            write_json(path,record)
            return None
        record.update(status='valid',code_hash=policy.key)
        write_json(path,record)
        return policy


def run(cfg, root, provider, model, initial_source=None):
    root=Path(root)
    directory=root/f'{cfg.prompt}__{cfg.selection}__seed{cfg.seed}'
    config_path=directory/'config.json'
    metadata={'initial_source':str(Path(initial_source).resolve()) if initial_source else None,'implementation_hash':implementation_hash(),'config':asdict(cfg),'config_hash':cfg.digest(),'provider':provider,'model':model,
              'baseline_train':[asdict(p) for p in TRAIN], 'baseline_test':[asdict(p) for p in TEST]}
    if config_path.exists() and read_json(config_path)!=metadata:
        raise RuntimeError('Existing run configuration differs')
    write_json(config_path,metadata)
    # Shared initialization identity excludes treatment, includes game and model.
    init_cfg=replace(cfg,prompt='minimal',selection='paper_truncation')
    initial_key=digest(json.dumps({'cfg':asdict(init_cfg),'provider':provider,'model':model},sort_keys=True))[:20]
    generator=Generator(root/'initial'/initial_key,provider,model,cfg.temperature)
    population=[]
    for i in range(cfg.population_size):
        prompt=build_prompt(init_cfg)+f'\nIndependent candidate {i}; replicate {cfg.seed}.\n'
        request_id=f'initial-{i}'
        p=reuse_initial(Path(initial_source)/'initial'/initial_key if initial_source else None,
                        generator.directory/(request_id+'.json'),request_id,init_cfg,provider,model,read_json,write_json)
        if p is None:
            p=generator.generate(request_id,prompt,init_cfg)
        if p is None:
            raise RuntimeError('Invalid initial policy; complete shared initial population before proceeding')
        population.append(p)
    initial_directory=root/'initial'/initial_key
    metadata['initial_directory']=str(initial_directory.resolve())
    # Stored separately to keep configuration identity independent of path spelling.
    write_json(directory/'initial_reference.json',{'path':str(initial_directory.resolve())})
    archive=list(TRAIN)
    generator=Generator(directory/'requests',provider,model,cfg.temperature)
    for generation in range(cfg.generations):
        state_path=directory/f'generation_{generation:03d}.json'
        if state_path.exists():
            state=read_json(state_path)
            if state['status']=='complete':
                population=[Policy(**p) for p in state['next_population']]
                archive=[Policy(**p) for p in state['next_archive']]
                continue
        assessment=evaluate(population,archive,cfg,generation)
        champion=population[ranking(population,assessment)[0]]
        tests={}
        for label, rounds, noise in [('default',cfg.rounds,0),('noise01',cfg.rounds,0.01),
                                      ('long',2*cfg.rounds,0)]:
            tests[label]=versus(champion,TEST,replace(cfg,rounds=rounds,noise=noise),
                                'holdout-'+label,generation)
        fixed=versus(champion,TRAIN,cfg,'fixed',generation)
        state={'status':'evaluated','generation':generation,'config_hash':cfg.digest(),
               'population':[asdict(p) for p in population],'assessment':assessment,
               'archive_keys':[p.key for p in archive],'champion':asdict(champion),
               'fixed_baselines':fixed,'holdout':tests,
               'code_diversity':len({p.key for p in population}),
               'behavior_diagnostics':population_behavior(population),
               'budget_at_evaluation':request_budget([initial_directory,directory/'requests'],generation),
               'test_configs':{'default':{'rounds':cfg.rounds,'noise':0},
                               'noise01':{'rounds':cfg.rounds,'noise':0.01},
                               'long':{'rounds':2*cfg.rounds,'noise':0}}, 'changes':[]}
        next_archive=update_archive(archive,population,assessment,cfg.archive_add)
        next_population=list(population)
        write_json(state_path,state)
        if generation<cfg.generations-1:
            kept,jobs=selection_plan(population,assessment,cfg,generation)
            for destination,source in kept.items():
                next_population[destination]=population[source]
            for ordinal,(destination,parent) in enumerate(jobs):
                request=f'g{generation+1:03d}-child{ordinal:03d}'
                prompt=build_prompt(cfg,population[parent],population,assessment)
                child=generator.generate(request,prompt,cfg)
                next_population[destination]=child if child is not None else population[destination]
                state['changes'].append({'request':request,'destination':destination,'parent':parent,
                                          'parent_key':population[parent].key,
                                          'child_key':child.key if child else None,'valid':child is not None})
                write_json(state_path,state)
        state.update(status='complete',next_population=[asdict(p) for p in next_population],
                     next_archive=[asdict(p) for p in next_archive])
        write_json(state_path,state)
        print(json.dumps({'generation':generation,'run':directory.name,'champion':champion.key[:12],
                          'fitness':max(r['fitness'] for r in assessment),
                          'holdout_score':tests['default']['score']},ensure_ascii=False),flush=True)
        population,archive=next_population,next_archive
    write_json(directory/'complete.json',{'config_hash':cfg.digest(),'generations':cfg.generations})


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',default='results/direct_reciprocity')
    parser.add_argument('--provider',default='deepseek')
    parser.add_argument('--model')
    parser.add_argument('--env-file',type=Path)
    parser.add_argument('--initial-source',type=Path)
    parser.add_argument('--seed',type=int,default=0)
    parser.add_argument('--prompt',choices=['minimal','score','full'],default='minimal')
    # Only the truncation rule remains; the flag is kept as the run-identity field.
    parser.add_argument('--selection',choices=['paper_truncation'],default='paper_truncation')
    parser.add_argument('--generations',type=int,default=10)
    parser.add_argument('--population-size',type=int,default=12)
    parser.add_argument('--eliminate',type=int,default=6)
    parser.add_argument('--rounds',type=int,default=100)
    parser.add_argument('--repeats',type=int,default=5)
    parser.add_argument('--dry-run',action='store_true')
    parser.add_argument('--matrix',action='store_true')
    parser.add_argument('--workers',type=int,default=2)
    parser.add_argument('--seeds',type=int,nargs='+',default=[0,1,2,3,4])
    args=parser.parse_args()
    if args.env_file:
        from dotenv import load_dotenv
        load_dotenv(args.env_file,override=False)
    cfg=Config(seed=args.seed,prompt=args.prompt,selection=args.selection,generations=args.generations,
               population_size=args.population_size,eliminate=args.eliminate,rounds=args.rounds,repeats=args.repeats)
    model=get_model(args.provider,args.model)
    if args.matrix:
        from .matrix import run_matrix
        return run_matrix(args,model)
    if args.dry_run:
        print(json.dumps({'config':asdict(cfg),'model':model,'provider':args.provider,
                          'configured':bool(get_api_key(args.provider))},indent=2))
    else:
        try:
            run(cfg,args.output,args.provider,model,args.initial_source)
        except Exception as exc:
            write_json(Path(args.output)/f'{cfg.prompt}__{cfg.selection}__seed{cfg.seed}'/'failure.json',
                       {'error_type':type(exc).__name__,'message':str(exc),'time':time.time()})
            raise


if __name__=='__main__':
    main()
