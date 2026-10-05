"""Prompt treatments differ only in supplied performance information."""
import json


def build_prompt(cfg, parent=None, population=None, evaluation=None):
    rules = f'''Write a Python policy to maximize your cumulative score in an iterated Prisoner's Dilemma tournament.
Payoffs (own action, opponent action): CC={cfg.reward}, CD={cfg.sucker}, DC={cfg.temptation}, DD={cfg.punishment}.
Every match lasts {cfg.rounds} rounds. Matches reset history. Execution noise independently flips each action with probability {cfg.noise}.
Selection fitness is {cfg.peer_weight} times average cumulative peer score plus {1-cfg.peer_weight} times average cumulative archive score.
Return ONLY Python source defining def strategy(history, rng): and no other top-level definitions, annotations, decorators or markdown. Optional imports of random are supported.
history is an immutable tuple of (your executed action, opponent executed action) pairs from this match, actions exactly 'C' or 'D'.
There is no opponent identity, source code, third-party observation, persistent cross-match state or reputation.
Return exactly 'C' or 'D'. rng.random(), rng.choice(sequence), rng.randint(a,b) provide reproducible randomness.
Use simple Python builtins: abs,all,any,bool,dict,enumerate,float,int,len,list,max,min,range,reversed,round,set,sorted,str,sum,tuple,zip,isinstance.
import random, import random as an alias, and named from random import statements are allowed at module or function level. They use the same per-match seeded stream as rng. Do not use other imports, global state, classes, private attributes or other APIs. Source length <=16000 characters. Work within 20000 Python instructions per action.
'''
    if parent is None:
        return rules+'\nGenerate one competitive strategy independently.\n'
    prompt = rules+'\nProduce a new strategy improving this parent. You may substantially rewrite it.\nPARENT:\n'+parent.code
    if cfg.prompt in ('score','full'):
        prompt += '\nTRAINING PERFORMANCE:\n'+json.dumps(evaluation,sort_keys=True)
    if cfg.prompt == 'full':
        prompt += '\nTRAINING POPULATION SOURCE:\n'+json.dumps([{'key':p.key,'code':p.code} for p in population])
    return prompt
