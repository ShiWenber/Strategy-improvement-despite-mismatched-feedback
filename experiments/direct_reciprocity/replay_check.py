"""Independent payoff accumulation for saved champion-vs-archive samples."""
from pathlib import Path
from statistics import mean
import random
from .core import Config, Policy, RandomView, act, seed_for
from .baselines import TRAIN
from .run import read_json, write_json


def independent_duel(a,b,cfg,seed):
    left_rng=RandomView(seed_for(seed,'left'))
    right_rng=RandomView(seed_for(seed,'right'))
    left=a.compile(left_rng)
    right=b.compile(right_rng)
    noise_left=random.Random(seed_for(seed,'noise-left'))
    noise_right=random.Random(seed_for(seed,'noise-right'))
    history=[]
    score=0.0
    cooperations=0
    for _ in range(cfg.rounds):
        own=act(left,tuple(history),left_rng)
        other=act(right,tuple((y,x) for x,y in history),right_rng)
        if noise_left.random()<cfg.noise:
            own={'C':'D','D':'C'}[own]
        if noise_right.random()<cfg.noise:
            other={'C':'D','D':'C'}[other]
        # Deliberately separate branches, not engine payoff dictionary.
        if own=='C':
            score+=cfg.reward if other=='C' else cfg.sucker
            cooperations+=1
        else:
            score+=cfg.temptation if other=='C' else cfg.punishment
        history.append((own,other))
    return score,cooperations/cfg.rounds


def replay_samples(root):
    root=Path(root)
    plan=read_json(root/'matrix_plan.json')
    checks=[]
    for seed in sorted({r['seed'] for r in plan['cells']}):
        directory=root/f'minimal__paper_truncation__seed{seed}'
        path=directory/'generation_000.json'
        if not path.exists():
            continue
        state=read_json(path)
        if state['status']!='complete':
            continue
        cfg=Config(**read_json(directory/'config.json')['config'])
        champion=Policy(**state['champion'])
        row=next(r for r in state['assessment'] if r['key']==champion.key)
        for index in (0,1,2,5):
            opponent=TRAIN[index]
            sample=[independent_duel(champion,opponent,cfg,seed_for(seed,'archive',0,index,repeat)) for repeat in range(cfg.repeats)]
            score=mean(x[0] for x in sample)
            cooperation=mean(x[1] for x in sample)
            recorded=row['archive']['opponents'][index]
            equal=abs(score-recorded['score'])<1e-12 and abs(cooperation-recorded['cooperation'])<1e-12
            checks.append({'seed':seed,'champion_key':champion.key,'opponent':opponent.name,
                           'score':score,'cooperation':cooperation,'matches_record':equal})
    result={'scope':'Generation-0 training champion against ALLC, ALLD, TFT, Random; five seeds when available. Independent accumulation with shared policy execution contract. Not a full replay.',
            'checks':checks,'all_available_samples_match':all(r['matches_record'] for r in checks) if checks else None}
    write_json(root/'PAYOFF_REPLAY.json',result)
    print(f"Independent sample checks: {len(checks)}, matching: {sum(r['matches_record'] for r in checks)}")
    return result


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('root',type=Path)
    replay_samples(parser.parse_args().root)
