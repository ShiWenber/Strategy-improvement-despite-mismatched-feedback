"""Deterministic parallel candidate scoring, returned in proposal order."""
from concurrent.futures import ProcessPoolExecutor


def score_one(arguments):
    from .control import hypothetical_fitness
    ordinal, candidate, slot, population, archive, cfg, generation = arguments
    result = {'ordinal': ordinal, 'key': candidate.key if candidate else None, 'fitness': None}
    if candidate is not None:
        try:
            result['fitness'] = hypothetical_fitness(candidate, slot, population, archive, cfg, generation)
        except Exception as exc:
            result['error'] = f'{type(exc).__name__}: {exc}'
    return result


def score_candidates(pool, start, limit, slot, population, archive, cfg, generation, workers=1):
    if workers < 1:
        raise ValueError('Scoring workers must be positive')
    jobs = [(i, pool[i], slot, population, archive, cfg, generation) for i in range(start, limit)]
    if workers == 1:
        yield from map(score_one, jobs)
    else:
        with ProcessPoolExecutor(max_workers=workers) as executor:
            yield from executor.map(score_one, jobs, chunksize=1)
