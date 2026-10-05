def strategy(history, rng):
    n = len(history)

    if n == 0:
        return 'C'

    opp = [h[1] for h in history]
    me = [h[0] for h in history]
    opp_def = sum(1 for a in opp if a == 'D')
    me_def = sum(1 for a in me if a == 'D')
    last_me, last_opp = history[-1]

    # Endgame: defect in final rounds
    if n >= 98:
        return 'D'

    # If opponent has heavily defected recently, retaliate
    recent = opp[-8:] if n >= 8 else opp
    recent_def = sum(1 for a in recent if a == 'D')
    if len(recent) >= 4 and recent_def * 2 >= len(recent):
        # but occasionally offer an olive branch if they've calmed
        if recent_def == len(recent):
            return 'D'
        if last_opp == 'C' and rng.random() < 0.35:
            return 'C'
        return 'D'

    # Detect repetitive defector
    if opp_def >= 6 and opp_def * 2 > n:
        return 'D'

    # Tit-for-tat-ish core with forgiveness
    if last_opp == 'D':
        if n >= 6 and sum(1 for a in opp[-6:] if a == 'D') >= 5:
            return 'D'
        if rng.random() < 0.25:
            return 'C'
        return 'D'

    # Cooperate with mostly cooperative opponent
    if last_opp == 'C':
        if n >= 10 and me_def > 0 and opp_def == 0:
            # repair: be extra cooperative
            return 'C'
        return 'C'

    return 'C'
