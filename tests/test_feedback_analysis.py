import unittest
from experiments.direct_reciprocity.feedback_analysis import interval, sign_flip_p


class AnalysisTests(unittest.TestCase):
    def test_identical_zero(self):
        self.assertEqual(sign_flip_p([0] * 5), 1)
        self.assertEqual(interval([0] * 5), [0, 0])

    def test_small_sample_resolution(self):
        self.assertEqual(sign_flip_p([1] * 5), 2 / 32)
        self.assertEqual(sign_flip_p([-1] * 5), 2 / 32)

    @staticmethod
    def reference_interval(values, resamples=20000, level=0.95, seed=91826):
        """Independent recomputation of the same percentile bootstrap.

        Written out longhand on purpose: it fixes the quantile level, the
        resample size and the resample width, none of which a self-comparison
        can pin down.
        """
        import random
        from statistics import mean
        rng = random.Random(seed)
        n = len(values)
        samples = sorted(mean(rng.choices(values, k=n)) for _ in range(resamples))
        tail = (1 - level) / 2
        return [samples[int(tail * len(samples))], samples[int((1 - tail) * len(samples))]]

    def test_interval_matches_recomputed_percentile_bootstrap(self):
        # Resampling a constant returns that constant for any level or resample
        # size, so a test built on constant inputs cannot see the 95% level, the
        # k=n rule or the 20000-resample budget change at all. Every input here
        # varies, which is what makes the comparison meaningful.
        for values in ([1,2,3,4,5], [1,2,3,4,5,6,7,8], [0.1,0.9], [5,5,5,4,6], [0,0,0,1,1]):
            self.assertEqual(interval(values), self.reference_interval(values), values)

    def test_interval_is_ordered_and_widens_with_spread(self):
        for values in ([1,2,3,4,5], [0.1,0.9], [0,0,0,1,1], [3,3,4,4,5]):
            low, high = interval(values)
            self.assertLessEqual(low, high, values)
            self.assertGreaterEqual(high, min(values), values)
            self.assertLessEqual(low, max(values), values)
        self.assertGreater(interval([1,2,3,4,5])[1]-interval([1,2,3,4,5])[0],
                           interval([3,3,4,4,5])[1]-interval([3,3,4,4,5])[0])

    def test_published_interval_values_are_pinned(self):
        # These CIs are printed in the results, so the numbers themselves must be
        # reproducible, not merely self-consistent. A self-comparison cannot pin
        # the RNG seed: at 20000 resamples most inputs land on the same quantile
        # grid point for any seed. This input does not, so it pins the seed too.
        low, high = interval([1, 7, 3, 9, 2, 8])
        self.assertAlmostEqual(low, 2.6666666666666665, places=9)
        self.assertAlmostEqual(high, 7.333333333333333, places=9)

    def test_determinism_and_missing(self):
        self.assertEqual(interval([1, 2, 3, 4, 5]), interval([1, 2, 3, 4, 5]))
        self.assertIsNone(interval([]))
        self.assertIsNone(sign_flip_p([]))


if __name__ == '__main__':
    unittest.main()
