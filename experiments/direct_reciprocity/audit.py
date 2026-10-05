"""Check saved research evidence against the factorial protocol; do not infer missing results."""
from pathlib import Path
from .run import read_json, write_json
from .core import Policy, Config, ranking, update_archive
from .baselines import TRAIN
from .matrix import cells


def audit(root):
    root=Path(root)
    plan=read_json(root/'matrix_plan.json')
    issues=[]
    incomplete=[]
    initial_by_seed={}
    checked=0
    for cell in plan['cells']:
        name=f"{cell['prompt']}__{cell['selection']}__seed{cell['seed']}"
        directory=root/name
        if not (directory/'config.json').exists():
            incomplete.append(name)
            continue
        meta=read_json(directory/'config.json')
        cfg=Config(**meta['config'])
        if cfg.digest()!=meta['config_hash']:
            issues.append(name+': config hash does not match fields')
        if meta['implementation_hash']!=plan['implementation_hash']:
            issues.append(name+': implementation differs from matrix')
        for field in ('generations','population_size','eliminate','rounds','repeats'):
            if getattr(cfg,field)!=plan[field]:
                issues.append(name+': '+field+' differs from matrix')
        if any(getattr(cfg,k)!=v for k,v in cell.items()):
            issues.append(name+': treatment/seed differs from plan')
        previous=None
        full=True
        for generation in range(cfg.generations):
            path=directory/f'generation_{generation:03d}.json'
            if not path.exists():
                full=False
                break
            state=read_json(path)
            if state['status']!='complete':
                full=False
                break
            checked+=1
            if state['generation']!=generation or state['config_hash']!=cfg.digest():
                issues.append(name+f': generation {generation} identity mismatch')
            population=[Policy(**p) for p in state['population']]
            if len(population)!=cfg.population_size or len(state['assessment'])!=cfg.population_size:
                issues.append(name+': population size mismatch')
                continue
            if generation==0:
                keys=[p.key for p in population]
                prior=initial_by_seed.setdefault(cell['seed'],keys)
                if prior!=keys:
                    issues.append(name+': initial population differs across treatments')
                archive=TRAIN
            else:
                if previous['next_population']!=state['population']:
                    issues.append(name+': previous offspring do not match next population')
                archive=[Policy(**p) for p in previous['next_archive']]
            if state['archive_keys']!=[p.key for p in archive]:
                issues.append(name+': archive timing/identity mismatch')
            desired=update_archive(archive,population,state['assessment'],cfg.archive_add)
            if [p.key for p in desired]!=[Policy(**p).key for p in state['next_archive']]:
                issues.append(name+': archive update does not match top-three unique rule')
            champion=population[ranking(population,state['assessment'])[0]]
            if Policy(**state['champion']).key!=champion.key:
                issues.append(name+': champion not chosen exclusively by training fitness')
            for label,test in state['holdout'].items():
                if test.get('status')=='runtime_failure':
                    recovery=directory/'evaluation_recovery.json'
                    if not recovery.exists() or read_json(recovery).get('base_implementation_hash')!=meta['implementation_hash']:
                        issues.append(name+': missing evaluation recovery provenance')
                    if any(test.get(k) is not None for k in ('score','cooperation','worst_score')) or not test.get('error'):
                        issues.append(name+': malformed runtime failure result')
                    continue
                if not 0<=test['cooperation']<=1:
                    issues.append(name+': invalid cooperation rate')
                rounds=state['test_configs'][label]['rounds']
                if not cfg.sucker*rounds<=test['score']<=cfg.temptation*rounds:
                    issues.append(name+': payoff outside game bounds')
            if len(state['next_population'])!=cfg.population_size:
                issues.append(name+': invalid next population size')
            for change in state['changes']:
                record=read_json(directory/'requests'/(change['request']+'.json'))
                if change['valid']!=(record['status']=='valid'):
                    issues.append(name+': offspring validity does not match raw response record')
            previous=state
        done=directory/'complete.json'
        if full and done.exists():
            marker=read_json(done)
            if marker['config_hash']!=cfg.digest() or marker['generations']!=cfg.generations:
                issues.append(name+': completion marker mismatch')
        else:
            incomplete.append(name)
    result={'protocol_issues':issues,'incomplete_cells':incomplete,
            'checked_complete_generations':checked,'all_main_complete':not incomplete and not issues,
            'scope':'Structural evidence audit, not independent recomputation of every payoff. Independent controls must also finish.'}
    write_json(root/'AUDIT.json',result)
    print(f"Checked generations={checked}; issues={len(issues)}; incomplete cells={len(incomplete)}")
    return result


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('root',type=Path)
    audit(parser.parse_args().root)
