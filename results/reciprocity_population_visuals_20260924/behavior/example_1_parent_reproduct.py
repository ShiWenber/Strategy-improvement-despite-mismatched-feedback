import random

def strategy(history, rng):
    n = len(history)
    if n == 0:
        return 'C'
    if n == 1:
        return 'C'
    if n == 2:
        opp_last = history[-1][1]
        return 'D' if opp_last == 'D' else 'C'
    last_opp = history[-1][1]
    prev_opp = history[-2][1]
    if last_opp == 'D' and prev_opp == 'D':
        if n < 10:
            return 'D'
        if rng.random() < 0.5:
            return 'D'
        return 'C'
    my_last = history[-1][0]
    if last_opp == 'D':
        if my_last == 'D':
            return 'D' if rng.random() < 0.8 else 'C'
        return 'D'
    if last_opp == 'C' and prev_opp == 'C':
        if n > 95:
            return 'D'
        return 'C'
    if last_opp == 'C':
        if rng.random() < 0.1:
            return 'D'
        return 'C'
    return 'C'
