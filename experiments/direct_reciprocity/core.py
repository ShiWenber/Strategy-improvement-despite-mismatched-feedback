"""Bilateral IPD engine. All score and random-stream conventions are explicit."""
from __future__ import annotations

import ast
import builtins
from dataclasses import dataclass
from tools.direct_reciprocity.records import digest
import json
import random
import sys
from statistics import mean
from types import MappingProxyType, SimpleNamespace


@dataclass(frozen=True)
class Config:
    population_size: int = 12
    generations: int = 10
    eliminate: int = 6
    rounds: int = 100
    repeats: int = 5
    reward: float = 3
    sucker: float = 0
    temptation: float = 5
    punishment: float = 1
    peer_weight: float = 0.6
    archive_add: int = 3
    noise: float = 0
    temperature: float = 1
    seed: int = 0
    prompt: str = 'minimal'
    # Retained as part of the run identity and of recorded configs; the
    # tournament and Fermi rules were removed, so truncation is the only rule.
    selection: str = 'paper_truncation'

    def __post_init__(self):
        if not 2 <= self.population_size or not 0 < self.eliminate < self.population_size:
            raise ValueError('Require N >= 2 and 0 < eliminate < N')
        if min(self.generations, self.rounds, self.repeats) < 1:
            raise ValueError('generations, rounds and repeats must be positive')
        if not 0 <= self.noise <= 1 or not 0 <= self.peer_weight <= 1:
            raise ValueError('noise/peer_weight must be probabilities')
        if not 0 <= self.archive_add <= self.population_size:
            raise ValueError('archive_add out of range')
        if not self.temptation > self.reward > self.punishment > self.sucker:
            raise ValueError('Require T > R > P > S')
        if self.prompt not in ('minimal', 'score', 'full'):
            raise ValueError('Unknown prompt')
        if self.selection != 'paper_truncation':
            raise ValueError('Only the paper_truncation rule remains; tournament and fermi were removed')


def seed_for(*parts):
    return int(digest(json.dumps(parts, sort_keys=True))[:16], 16)


class PolicyError(ValueError):
    pass


_BUILTINS = {k: getattr(builtins,k) for k in (
    'abs', 'all', 'any', 'bool', 'dict', 'enumerate', 'float', 'int', 'len',
    'list', 'max', 'min', 'range', 'reversed', 'round', 'set', 'sorted',
    'str', 'sum', 'tuple', 'zip', 'isinstance'
) }


@dataclass(frozen=True)
class Policy:
    name: str
    code: str

    @property
    def key(self):
        return digest(self.code)

    def compile(self, rng=None):
        if len(self.code) > 16000:
            raise PolicyError('Policy exceeds 16000 characters')
        tree = ast.parse(self.code)
        functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)]
        if len(functions) != 1 or any(not isinstance(node,(ast.FunctionDef,ast.Import,ast.ImportFrom)) for node in tree.body):
            raise PolicyError('Define strategy plus optional random imports at module level')
        fn = functions[0]
        if fn.name != 'strategy' or fn.decorator_list or fn.returns:
            raise PolicyError('Require undecorated, unannotated strategy')
        if [a.arg for a in fn.args.args] != ['history', 'rng'] or (
            fn.args.vararg or fn.args.kwarg or fn.args.kwonlyargs or fn.args.posonlyargs
            or fn.args.defaults or any(a.annotation for a in fn.args.args)
        ):
            raise PolicyError('Require strategy(history, rng) without defaults/annotations')
        for node in ast.walk(tree):
            if isinstance(node, ast.Import) and any(alias.name != 'random' for alias in node.names):
                raise PolicyError('Only random imports are supported by this policy API')
            if isinstance(node, ast.ImportFrom) and (node.module != 'random' or node.level or any(alias.name.startswith('_') or alias.name == '*' for alias in node.names)):
                raise PolicyError('Only named public imports from random are supported')
            if isinstance(node, (ast.Global, ast.Nonlocal, ast.ClassDef, ast.AsyncFunctionDef)):
                raise PolicyError('Global state and classes are outside the policy API')
            if isinstance(node, ast.Attribute) and node.attr.startswith('_'):
                raise PolicyError('Private attribute access is outside the policy API')
        view = rng if rng is not None else RandomView(0)
        module = seeded_random_module(view)
        def import_random(name, globals=None, locals=None, fromlist=(), level=0):
            if name != 'random' or level:
                raise PolicyError('Only random imports are supported')
            return module
        scope = {'__builtins__': MappingProxyType({**_BUILTINS,'__import__':import_random})}
        exec(compile(tree, '<ipd-policy>', 'exec'), scope)
        return scope['strategy']


class RandomView:
    """Per-player stream; no access to engine state or the opponent stream."""
    def __init__(self, seed):
        self._rng = random.Random(seed)
    def random(self):
        return self._rng.random()
    def choice(self, values):
        return self._rng.choice(values)
    def randint(self, a, b):
        return self._rng.randint(a, b)


def seeded_random_module(view):
    """Module-style random API backed by the same per-policy stream as rng.

    Do not touch process-global random state. Random() without a seed derives
    its seed from this match stream instead of wall-clock/system entropy.
    """
    names=('random','randint','randrange','choice','choices','shuffle','sample',
           'uniform','triangular','betavariate','expovariate','gammavariate',
           'gauss','lognormvariate','normalvariate','vonmisesvariate',
           'paretovariate','weibullvariate','getrandbits','randbytes','getstate','setstate')
    api={name:getattr(view._rng,name) for name in names}
    def new_random(seed=None):
        return random.Random(view._rng.getrandbits(128) if seed is None else seed)
    def reseed(seed=None, version=2):
        view._rng.seed(view._rng.getrandbits(128) if seed is None else seed,version=version)
    return SimpleNamespace(**api,Random=new_random,seed=reseed)


def act(fn, history, rng):
    # Deterministic execution budget prevents a generated Python loop hanging a run.
    # This API is not advertised as an OS security sandbox.
    remaining = 20000
    def trace(frame, event, arg):
        nonlocal remaining
        if event == 'call':
            frame.f_trace_opcodes = True
        if event in ('line', 'opcode'):
            remaining -= 1
            if remaining <= 0:
                raise PolicyError('Policy instruction budget exceeded')
        return trace
    old = sys.gettrace()
    try:
        sys.settrace(trace)
        action = fn(tuple(history), rng)
    except Exception as exc:
        raise PolicyError(f'{type(exc).__name__}: {exc}') from exc
    finally:
        sys.settrace(old)
    if type(action) is not str or action not in ('C', 'D'):
        raise PolicyError('Policy must return exactly C or D')
    return action


def match(a: Policy, b: Policy, cfg: Config, seed: int):
    # Each fresh function and history exists for only one bilateral match.
    rng_a, rng_b = RandomView(seed_for(seed, 'left')), RandomView(seed_for(seed, 'right'))
    left, right = a.compile(rng_a), b.compile(rng_b)
    errors_a = random.Random(seed_for(seed, 'noise-left'))
    errors_b = random.Random(seed_for(seed, 'noise-right'))
    history_a, history_b = [], []
    scores, cooperation = [0.0, 0.0], [0, 0]
    payoff = {('C','C'): (cfg.reward,cfg.reward), ('C','D'): (cfg.sucker,cfg.temptation),
              ('D','C'): (cfg.temptation,cfg.sucker), ('D','D'): (cfg.punishment,cfg.punishment)}
    for _ in range(cfg.rounds):
        x, y = act(left, history_a, rng_a), act(right, history_b, rng_b)
        if errors_a.random() < cfg.noise:
            x = 'D' if x == 'C' else 'C'
        if errors_b.random() < cfg.noise:
            y = 'D' if y == 'C' else 'C'
        p, q = payoff[x,y]
        scores[0] += p
        scores[1] += q
        cooperation[0] += x == 'C'
        cooperation[1] += y == 'C'
        history_a.append((x,y))
        history_b.append((y,x))
    return {'scores': scores, 'cooperation': [x/cfg.rounds for x in cooperation]}


def versus(policy, opponents, cfg, phase, generation=0):
    rows = []
    for j, opponent in enumerate(opponents):
        games = [match(policy, opponent, cfg, seed_for(cfg.seed, phase, generation, j, r))
                 for r in range(cfg.repeats)]
        rows.append({'opponent': opponent.name, 'key': opponent.key,
                     'score': mean(g['scores'][0] for g in games),
                     'cooperation': mean(g['cooperation'][0] for g in games)})
    return {'score': mean(r['score'] for r in rows),
            'cooperation': mean(r['cooperation'] for r in rows),
            'worst_score': min(r['score'] for r in rows), 'opponents': rows}


def evaluate(population, archive, cfg, generation):
    n = len(population)
    scores, coops = [[] for _ in population], [[] for _ in population]
    for i in range(n):
        for j in range(i+1,n):
            for repeat in range(cfg.repeats):
                game = match(population[i], population[j], cfg,
                             seed_for(cfg.seed,'peer',generation,i,j,repeat))
                for index, side in ((i,0),(j,1)):
                    scores[index].append(game['scores'][side])
                    coops[index].append(game['cooperation'][side])
    result = []
    for i, policy in enumerate(population):
        external = versus(policy, archive, cfg, 'archive', generation)
        peer = mean(scores[i])
        result.append({'key':policy.key, 'peer_score':peer, 'peer_cooperation':mean(coops[i]),
                       'archive':external,
                       'fitness':cfg.peer_weight*peer+(1-cfg.peer_weight)*external['score']})
    return result


def ranking(population, evaluation):
    return sorted(range(len(population)), key=lambda i:(-evaluation[i]['fitness'],population[i].key,i))


def update_archive(archive, population, evaluation, count):
    result = list(archive)
    keys = {p.key for p in result}
    for i in ranking(population,evaluation)[:count]:
        if population[i].key not in keys:
            result.append(population[i])
            keys.add(population[i].key)
    return result
