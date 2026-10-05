"""Deterministic within-population report donor assignment without fixed points."""
import random


def derangement(n, seed):
    if n < 2:
        raise ValueError('Derangement requires at least two slots')
    rng = random.Random(seed)
    order = list(range(n))
    while True:
        rng.shuffle(order)
        if all(i != j for i, j in enumerate(order)):
            return order
