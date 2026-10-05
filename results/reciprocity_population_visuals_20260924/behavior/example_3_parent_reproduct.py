def strategy(history, rng):
    if not history:
        return 'C'
    n = len(history)
    my = [h[0] for h in history]
    op = [h[1] for h in history]
    if n == 1:
        return 'C'
    if n < 10:
        if op[-1] == 'D':
            return 'D'
        return 'C'
    op_defects = sum(1 for x in op if x == 'D')
    my_defects = sum(1 for x in my if x == 'D')
    last5_op = op[-5:]
    last5_my = my[-5:]
    defects_last5_op = sum(1 for x in last5_op if x == 'D')
    defects_last5_my = sum(1 for x in last5_my if x == 'D')
    if op_defects == 0:
        if n == 99:
            return 'D'
        return 'C'
    if my_defects > 20 and op_defects > 20:
        return 'D' if n % 2 == 0 else 'C'
    if last5_op == ['D', 'D', 'D', 'D', 'D']:
        return 'D'
    if last5_op == ['C', 'C', 'C', 'C', 'C']:
        if defects_last5_my >= 3:
            return 'C'
        return 'C'
    if defects_last5_op >= 3:
        return 'D'
    if defects_last5_op >= 1:
        if my[-1] == 'D':
            return 'D'
        if len(my) >= 2 and my[-2] == 'D' and op[-1] == 'D':
            return 'D'
        return 'D' if defects_last5_op >= 2 else 'C'
    if defects_last5_op == 0:
        if n == 99:
            return 'D'
        return 'C'
    if op_defects > 0 and op_defects * 2 < n:
        if op[-1] == 'D':
            return 'D'
        if n % 10 == 9:
            return 'D'
        return 'C'
    if op[-1] == 'D':
        return 'D'
    return 'C'
