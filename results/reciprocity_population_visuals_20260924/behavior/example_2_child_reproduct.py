def strategy(history, rng):
    n = len(history)
    if n == 0:
        return 'C'
    if n == 99:
        return 'D'
    last_me, last_opp = history[-1]
    if last_opp == 'C':
        return 'C'
    opp_def = 0
    for h in history:
        if h[1] == 'D':
            opp_def += 1
    k = 0
    for h in reversed(history):
        if h[1] == 'D':
            k += 1
        else:
            break
    if k == 1 and opp_def <= 2:
        return 'C'
    if k == 3 and opp_def <= 4:
        return 'C'
    return 'D'
