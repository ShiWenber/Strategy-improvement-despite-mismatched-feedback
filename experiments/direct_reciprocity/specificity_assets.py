"""Frozen v2 measurement assets. No test result enters generation or selection."""
from dataclasses import asdict
from pathlib import Path
import json
import os
import sys
from statistics import mean

from .baselines import policy
from .core import Config, RandomView, act, seed_for

ARMS = ('score', 'accurate', 'mismatched', 'background', 'cooperation')
FAMILIES = ('recovery', 'exploitation', 'random', 'memory')
SEEDS = tuple(range(200, 220))
RANKS = (1, 3, 6)
REPEATS = 20


def tokenizer():
    deps = Path(__file__).resolve().parents[2] / '.research_deps'
    if str(deps) not in sys.path:
        sys.path.insert(0, str(deps))
    os.environ.setdefault('TIKTOKEN_CACHE_DIR', str(deps / 'tiktoken_cache'))
    import tiktoken
    return tiktoken.get_encoding('cl100k_base')


def panel(split):
    """24 V opponents match 11 peers + 13 archive; H has 12 opponents.

    Equal family sizes make ordinary means family-balanced. Families overlap
    with training; these are parameter/implementation transfer experiments.
    """
    if split not in ('V', 'H'):
        raise ValueError(split)
    rows = []
    count = 6 if split == 'V' else 3
    for j in range(count):
        onset = ([5, 9, 15, 21, 27, 33] if split == 'V' else [7, 13, 19])[j]
        burst = ([1, 3, 2, 4, 6, 3] if split == 'V' else [2, 3, 5])[j]
        forgive = ([.04, .12, .20, .28, .36, .44] if split == 'V' else [.08, .18, .32])[j]
        body = (f't = len(history)\nif {onset} <= t < {onset + burst}:\n    return \'D\'\n'
                f"return 'C' if not history or history[-1][1] == 'C' or rng.random() < {forgive} else 'D'")
        rows.append(('recovery', policy(f'{split}_Recovery{j}', body)))
        delay = ([1, 3, 8, 17, 23, 31] if split == 'V' else [0, 11, 29])[j]
        if j % 2 == 0:
            body = f"return 'C' if len(history) < {delay} else 'D'"
        else:
            period = 7 + j if split == 'V' else 5 + 2 * j
            body = f"return 'C' if len(history) < {delay} or (len(history)-{delay}) % {period} >= 3 else 'D'"
        rows.append(('exploitation', policy(f'{split}_Exploitation{j}', body)))
        prob = ([.12, .26, .42, .58, .74, .88] if split == 'V' else [.18, .46, .78])[j]
        rows.append(('random', policy(f'{split}_Random{j}', f"return 'C' if rng.random() < {prob} else 'D'")))
        cc = round(.65 + .045 * j + (.025 if split == 'H' else 0), 4)
        cd = round(.03 + .025 * j, 4)
        dc = round(.4 + .06 * j + (.03 if split == 'H' else 0), 4)
        dd = round(.02 + .018 * j, 4)
        body = f"p = {{('C','C'):{cc}, ('C','D'):{cd}, ('D','C'):{dc}, ('D','D'):{dd}}}\nreturn 'C' if not history or rng.random() < p[history[-1]] else 'D'"
        rows.append(('memory', policy(f'{split}_Memory{j}', body)))
    return rows


def probe_specs(split):
    if split == 'F':
        return [dict(name=name, forced=10, onset=0, burst=burst, restore=restore,
                     horizon=24, period=5, forgiveness=0.)
                for name, burst, restore in [('one_D_TFT', 1, 'TFT'), ('four_D_TFT', 4, 'TFT'),
                                            ('four_D_ALLC', 4, 'ALLC'), ('sustained_D', 24, 'ALLD'),
                                            ('periodic_D', 0, 'periodic')]]
    if split != 'H':
        raise ValueError(split)
    return [dict(name=f'{mode}_{name}', forced=7 if mode == 'controlled' else 0,
                 onset=onset, burst=burst, restore=restore, horizon=40, period=7, forgiveness=.15)
            for mode in ('controlled', 'natural')
            for name, onset, burst, restore in [('two_D_TFT', 3, 2, 'TFT'),
                                               ('five_D_GTFT', 9, 5, 'GTFT'),
                                               ('three_D_ALLC', 6, 3, 'ALLC'),
                                               ('sustained_D', 5, 35, 'ALLD'),
                                               ('periodic_D', 4, 0, 'periodic')]]


def probes(candidate, cfg, split, repeats=None):
    repeats = repeats or (10 if split == 'F' else 20)
    output = {}
    for spec in probe_specs(split):
        runs = []
        for repeat in range(repeats):
            rng = RandomView(seed_for('specificity-probe', split, cfg.seed, spec['name'], repeat))
            other = RandomView(seed_for('specificity-probe-opponent', split, cfg.seed, spec['name'], repeat))
            fn = candidate.compile(rng)
            history = [('C', 'C')] * spec['forced']
            actions = []
            onset, end = spec['onset'], spec['onset'] + spec['burst']
            for t in range(spec['horizon']):
                x = act(fn, history, rng)
                if t < onset:
                    y = 'C'
                elif onset <= t < end or spec['restore'] == 'ALLD':
                    y = 'D'
                elif spec['restore'] == 'periodic':
                    y = 'D' if (t - onset) % spec['period'] < 2 else 'C'
                elif spec['restore'] == 'ALLC':
                    y = 'C'
                else:
                    y = history[-1][0] if history else 'C'
                    if spec['restore'] == 'GTFT' and other.random() < spec['forgiveness']:
                        y = 'C'
                history.append((x, y))
                actions.append((x, y))
            payoff = {('C', 'C'): cfg.reward, ('C', 'D'): cfg.sucker,
                      ('D', 'C'): cfg.temptation, ('D', 'D'): cfg.punishment}
            row = {'own_cooperation_first4': mean(x == 'C' for x, _ in actions[:4]),
                   'own_cooperation_after4': mean(x == 'C' for x, _ in actions[4:]),
                   'mutual_cooperation_last5': mean(x == y == 'C' for x, y in actions[-5:]),
                   'own_cooperation_last5': mean(x == 'C' for x, _ in actions[-5:]),
                   'unilateral_cooperation_last5': mean(x == 'C' and y == 'D' for x, y in actions[-5:]),
                   'score': mean(payoff[a] for a in actions)}
            if spec['restore'] in ('TFT', 'GTFT', 'ALLC'):
                times = [i + 5 - end for i in range(end, len(actions) - 4)
                         if all(a == ('C', 'C') for a in actions[i:i + 5])]
                row['not_recovered'] = float(not times)
                row['recovery_time_capped'] = min(times) if times else len(actions) - end
            runs.append(row)
        output[spec['name']] = {'mean': {key: mean(row[key] for row in runs) for key in runs[0]},
                                'runs': runs}
    return output


def diagnostic_block(diagnostics):
    head = ('MEASURED PARENT BEHAVIOR. Each controlled probe begins with ten externally supplied CC rounds, '
            'then runs 24 further rounds. These histories need not be naturally reachable. '
            'one_D_TFT and four_D_TFT use one or four initial defections followed by copying your last action; '
            'four_D_ALLC uses four defections followed by unconditional cooperation; sustained_D always defects; '
            'periodic_D defects on the first two positions of each five-round cycle. '
            'Each statistic averages ten independent random streams. Use these measurements when deciding '
            'what to retain or change to maximize cumulative tournament fitness.\n')
    lines = []
    for name, result in diagnostics.items():
        lines.append(name + ': ' + '; '.join(f'{key}={value:.4f}' for key, value in sorted(result['mean'].items())))
    return head + '\n'.join(lines)


BACKGROUND = (
    'BACKGROUND INFORMATION. These statements describe the game and interface, not measurements of this parent. ',
    'Each policy outputs one of two action symbols at each decision. ',
    'The history contains executed action pairs from the current bilateral match. ',
    'The first coordinate belongs to this player and the second to its opponent. ',
    'A new match begins with an empty history and resets the action sequence. ',
    'The function receives history and a reproducible random generator as arguments. ',
    'The payoff table specifies the reward associated with each pair of actions. ',
    'A cumulative score adds the rewards obtained over a fixed number of rounds. ',
    'The tournament combines a peer component and an archive component. ',
    'Population source entries are displayed in slot order, with a score for each slot. ',
    'Source code must obey the stated Python interface and return a valid action. ',
    'The external evaluator executes the returned function on successive histories. ',
)
COOPERATION = (
    'GENERAL COOPERATION ADVICE. This is general guidance, not a measurement or diagnosis of this parent. ',
    'Consider beginning cooperatively to make mutual cooperation possible. ',
    'Give a partner opportunities to return to a mutually cooperative interaction. ',
    'Avoid allowing an isolated defection to cause permanent mutual retaliation. ',
    'Consider forgiveness after a temporary disruption in otherwise cooperative play. ',
    'Preserve established mutual cooperation when the partner continues cooperating. ',
    'A conciliatory action can sometimes help end a chain of alternating retaliation. ',
    'Prefer repairs that support recovering mutual cooperation after a short conflict. ',
    'A short punishment followed by renewed cooperation may restore coordination. ',
    'Consider the cumulative value of a long sequence of mutually cooperative rounds. ',
    'An occasional mistaken action need not erase the possibility of future cooperation. ',
    'Use these general suggestions while pursuing the stated tournament objective. ',
)


def length_matched_text(sentences, target):
    enc = tokenizer()
    result = sentences[0]
    i = 1
    while len(enc.encode(result)) < .97 * target:
        sentence = sentences[1 + (i - 1) % (len(sentences) - 1)]
        if len(enc.encode(result + sentence)) > 1.05 * target:
            break
        result += sentence
        i += 1
    if not .95 * target <= len(enc.encode(result)) <= 1.05 * target:
        raise ValueError('Cannot match text length within frozen tolerance')
    return result


def assets_record():
    return {'panels': {split: [{'family': family, **asdict(p)} for family, p in panel(split)]
                       for split in ('V', 'H')},
            'probes': {split: probe_specs(split) for split in ('F', 'H')},
            'tokenizer': 'tiktoken cl100k_base; proxy tokenizer, not provider billing tokenizer',
            'families_disjoint_from_training': False}
