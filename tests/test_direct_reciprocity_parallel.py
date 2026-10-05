import unittest
from experiments.direct_reciprocity.baselines import TRAIN
from experiments.direct_reciprocity.core import Config
from experiments.direct_reciprocity.control_scoring import score_candidates


class ParallelControlTests(unittest.TestCase):
    def test_parallel_and_serial_match_including_random_and_invalid_proposal(self):
        population = [TRAIN[i] for i in (0, 1, 2, 5)]
        pool = population+[None]
        cfg = Config(population_size=4, eliminate=2, rounds=10, repeats=2, noise=.01)
        args = (pool, 0, len(pool), 0, population, TRAIN[:3], cfg, 9)
        serial = list(score_candidates(*args, workers=1))
        parallel = list(score_candidates(*args, workers=2))
        self.assertEqual(serial, parallel)
        self.assertEqual([r['ordinal'] for r in parallel], list(range(len(pool))))
        self.assertEqual(list(score_candidates(pool, 2, 5, 0, population, TRAIN[:3], cfg, 9, 2)), serial[2:])
