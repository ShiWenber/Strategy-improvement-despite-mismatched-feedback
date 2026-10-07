import unittest
from tools.direct_reciprocity.trajectory_analysis import align_pair


class TrajectoryTests(unittest.TestCase):
    def test_shared_support_without_lookahead_and_with_missing_value(self):
        left = [{'generation': i, 'requests': b, 'score': s} for i, (b, s) in enumerate([(12, 2), (18, 3), (24, None)])]
        right = [{'generation': i, 'requests': b, 'score': s} for i, (b, s) in enumerate([(12, 2), (20, 4), (30, 5)])]
        points = align_pair(left, right, 'score')
        self.assertEqual([p['budget'] for p in points], [12, 18, 20, 24])
        self.assertEqual(points[1]['right_generation'], 0)
        self.assertEqual(points[1]['difference'], -1)
        self.assertEqual(points[2]['difference'], 1)
        self.assertIsNone(points[3]['difference'])
        self.assertEqual(align_pair([], right, 'score'), [])

    def test_equal_budget_uses_latest_generation(self):
        left = [{'generation': 0, 'requests': 12, 'score': 2}, {'generation': 1, 'requests': 12, 'score': 3}]
        right = [{'generation': 0, 'requests': 12, 'score': 4}]
        self.assertEqual(align_pair(left, right, 'score')[0]['difference'], 1)
