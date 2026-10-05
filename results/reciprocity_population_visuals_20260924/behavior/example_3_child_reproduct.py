def strategy(history, rng):
    n = len(history)
    if n == 0:
        return 'C'
    if n == 1:
        return 'C'
    if n >= 99:
        return 'D'
    
    my = [h[0] for h in history]
    op = [h[1] for h in history]
    last_my = my[-1]
    last_op = op[-1]
    
    total_op_def = op.count('D')
    if total_op_def > n * 0.5:
        return 'D'
    
    if last_op == 'D':
        if n >= 4:
            last4_my = my[-4:]
            last4_op = op[-4:]
            alt1 = last4_my == ['C', 'D', 'C', 'D'] and last4_op == ['D', 'C', 'D', 'C']
            alt2 = last4_my == ['D', 'C', 'D', 'C'] and last4_op == ['C', 'D', 'C', 'D']
            if (alt1 or alt2) and total_op_def < n * 0.4:
                return 'C'
        
        if last_my == 'D':
            if total_op_def < n * 0.3 and n > 10:
                if rng.random() < 0.5:
                    return 'C'
            return 'D'
        else:
            return 'D'
    
    recent_op = op[-10:]
    recent_op_def = recent_op.count('D')
    
    if recent_op_def == 0:
        my_def_count = my.count('D')
        if my_def_count == 0:
            if n > 15 and rng.random() < 0.1:
                return 'D'
            return 'C'
        else:
            start = max(0, n - 20)
            forgiven = 0
            retaliated = 0
            for i in range(start + 1, n):
                if my[i-1] == 'D':
                    if op[i] == 'C':
                        forgiven += 1
                    elif op[i] == 'D':
                        retaliated += 1
            total = forgiven + retaliated
            if total == 0:
                forgive_rate = 1.0
            else:
                forgive_rate = forgiven / total
            prob = 0.02 + 0.28 * forgive_rate
            recent_my = my[-20:]
            recent_my_def = recent_my.count('D')
            if recent_my_def > len(recent_my) * 0.3:
                prob *= 0.5
            if rng.random() < prob:
                return 'D'
            return 'C'
    else:
        return 'C'
