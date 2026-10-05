import random

def strategy(history, rng):
    n = len(history)
    if n == 0:
        return 'C'

    opp = [h[1] for h in history]
    me = [h[0] for h in history]

    def streak(seq, ch):
        s = 0
        for x in reversed(seq):
            if x == ch:
                s += 1
            else:
                break
        return s

    opp_d_total = sum(1 for a in opp if a == 'D')
    my_d_total = sum(1 for a in me if a == 'D')
    opp_c_rate = (n - opp_d_total) / float(n)

    last_opp = opp[-1]
    last_me = me[-1]
    opp_d_streak = streak(opp, 'D')
    opp_c_streak = streak(opp, 'C')

    # Opening: cooperate to encourage mutual cooperation.
    if n < 4:
        return 'C'

    # Strong, persistent defector: minimize losses but keep rare probes.
    if opp_d_total >= n - opp_d_total + 3 or (n >= 12 and opp_c_rate < 0.25):
        if rng.random() < 0.06:
            return 'C'
        return 'D'

    # Long defection streak: punish, but do not lock into permanent conflict.
    if opp_d_streak >= 3:
        if opp_d_streak >= 6:
            # Try an occasional olive branch to break mutual defection.
            if rng.random() < 0.12:
                return 'C'
            return 'D'
        return 'D'

    # Endgame: exploit last few rounds against non-hostile opponents.
    remaining = 100 - n
    if remaining <= 1:
        return 'D'
    if remaining <= 3 and opp_c_rate >= 0.4:
        return 'D'

    # Alternating retaliation detection: sometimes cooperate to break CD/CD cycles.
    if n >= 4:
        if opp[-1] == 'D' and opp[-2] == 'C' and opp[-3] == 'D' and opp[-4] == 'C':
            if rng.random() < 0.55:
                return 'C'
            return 'D'

    # Opponent recently mostly cooperative.
    if opp_c_rate >= 0.75 and opp_d_streak == 0:
        # Occasional low-rate exploitation, but preserve cooperation.
        if n > 8 and rng.random() < 0.06:
            return 'D'
        return 'C'

    # Opponent just defected.
    if last_opp == 'D':
        # If we already retaliated and opponent is otherwise cooperative,
        # offer a conciliatory move to restore coordination.
        if last_me == 'D' and opp_c_rate >= 0.6:
            if opp_d_streak >= 2:
                if rng.random() < 0.25:
                    return 'C'
                return 'D'
            return 'C'
        # If opponent defected against our cooperation, retaliate once.
        if last_me == 'C':
            return 'D'
        # Otherwise continue proportional punishment.
        if opp_c_rate >= 0.5 and rng.random() < 0.2:
            return 'C'
        return 'D'

    # Opponent cooperated.
    if last_opp == 'C':
        # If we accidentally defected and they still cooperate, reciprocate.
        if last_me == 'D':
            if opp_c_rate >= 0.5:
                return 'C'
            if rng.random() < 0.5:
                return 'C'
            return 'D'
        # Sustained cooperation: preserve it.
        if opp_c_streak >= 2:
            return 'C'
        if opp_c_rate >= 0.4:
            return 'C'
        # Distrustful opponent but currently cooperating: probe cautiously.
        if rng.random() < 0.15:
            return 'D'
        return 'C'

    return 'C'
