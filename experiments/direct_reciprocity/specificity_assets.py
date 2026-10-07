"""Frozen v2 measurement assets. No test result enters generation or selection."""
from statistics import mean

from .baselines import policy
from .core import RandomView, act, seed_for

ARMS = ('accurate', 'mismatched')
SCORE_ARMS = ARMS + ('score',)
GENERATION_ORDER = ('score', 'accurate', 'mismatched')


def experiment_arms(arms=None):
    """Keep the matching contrast in every batch, with an optional Score baseline."""
    arms = tuple(ARMS if arms is None else arms)
    if arms not in (ARMS, SCORE_ARMS):
        raise ValueError('Use accurate mismatched, optionally followed by score')
    return arms


def generation_arms(arms):
    """Dispatch complete condition batches in a fixed, recorded order."""
    return tuple(arm for arm in GENERATION_ORDER if arm in experiment_arms(arms))


def information_prompt(base, arm, reports):
    """The information condition changes only the appended behavioural report."""
    if arm not in SCORE_ARMS:
        raise ValueError('Unknown information condition: ' + arm)
    block = '' if arm == 'score' else reports[arm]
    return base + '\n' + block + '\nReturn only the new strategy source.\n'

FAMILIES = ('recovery', 'exploitation', 'random', 'memory')
SEEDS = tuple(range(200, 220))
RANKS = (1, 3, 6)
REPEATS = 20


def tokenizer():
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
