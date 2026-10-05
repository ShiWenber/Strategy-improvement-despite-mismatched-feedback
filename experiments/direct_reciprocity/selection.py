"""Truncation selection over the evaluation ranking."""
import random
from .core import ranking, seed_for


def selection_plan(population, evaluation, cfg, generation):
    """Keep the top N - eliminate agents and refill the rest from survivors.

    Every refilled slot schedules one full-mutation offspring of a surviving
    agent, and parent draws come from a stream derived from seed and generation,
    so replaying the same call returns the same plan.
    """
    rng = random.Random(seed_for(cfg.seed,'selection',generation))
    order = ranking(population,evaluation)
    kept = order[:-cfg.eliminate]
    return {i:i for i in kept}, [(i,rng.choice(kept)) for i in order[-cfg.eliminate:]]
