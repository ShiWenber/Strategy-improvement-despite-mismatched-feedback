"""Versioned baseline definitions; variants are explicit, not claimed author replicas."""
from .core import Policy


def policy(name, body):
    return Policy(name, 'def strategy(history, rng):\n' + '\n'.join('    '+line for line in body.splitlines())+'\n')


TRAIN = [
    policy('ALLC', "return 'C'"),
    policy('ALLD', "return 'D'"),
    policy('TFT', "return history[-1][1] if history else 'C'"),
    policy('Grim', "return 'D' if any(y == 'D' for x,y in history) else 'C'"),
    policy('Pavlov', "return 'C' if not history or history[-1][0] == history[-1][1] else 'D'"),
    policy('Random', "return 'C' if rng.random() < 0.5 else 'D'"),
    policy('Alternator', "return 'C' if len(history) % 2 == 0 else 'D'"),
    policy('Bayesian', "p = (1 + sum(y == 'C' for x,y in history))/(2 + len(history))\nreturn 'C' if p >= 0.5 else 'D'"),
    policy('GTFT', "return 'C' if not history or history[-1][1] == 'C' or rng.random() < 0.1 else 'D'"),
    policy('Gradual', "count = 0\npunish = 0\ncalm = 0\nfor x,y in history:\n    if punish > 0:\n        punish -= 1\n        if punish == 0:\n            calm = 2\n    elif calm > 0:\n        calm -= 1\n    elif y == 'D':\n        count += 1\n        punish = count\nreturn 'D' if punish else 'C'"),
    policy('Prober', "opening = ('D','C','C')\nif len(history) < 3:\n    return opening[len(history)]\nif history[1][1] == 'C' and history[2][1] == 'C':\n    return 'D'\nreturn history[-1][1]"),
    policy('SuspiciousTFT', "return history[-1][1] if history else 'D'"),
    policy('Extort2', "if not history:\n    return 'D'\np = {('C','C'): 8/9, ('C','D'): 1/2, ('D','C'): 1/3, ('D','D'): 0}[history[-1]]\nreturn 'C' if rng.random() < p else 'D'"),
]

# Holdout definitions never enter generation prompts or selection.
TEST = [
    policy('TF2T', "return 'D' if len(history) >= 2 and all(y == 'D' for x,y in history[-2:]) else 'C'"),
    policy('HardTFT', "return 'D' if any(y == 'D' for x,y in history[-3:]) else 'C'"),
    policy('ContriteTFT', "if not history:\n    return 'C'\nif history[-1] == ('D','C'):\n    return 'C'\nif len(history)>1 and history[-2] == ('D','C') and history[-1] == ('C','D'):\n    return 'C'\nreturn history[-1][1]"),
    policy('WinShiftLoseStay', "return 'D' if not history or history[-1][0] == history[-1][1] else 'C'"),
    policy('Random20', "return 'C' if rng.random()<0.2 else 'D'"),
    policy('Random80', "return 'C' if rng.random()<0.8 else 'D'"),
    policy('CCD', "return 'D' if len(history)%3 == 2 else 'C'"),
    policy('AdaptiveTFT', "trust = 0.5\nfor x,y in history:\n    trust = 0.8*trust+0.2*(y == 'C')\nreturn 'C' if trust>=0.5 else 'D'"),
]
