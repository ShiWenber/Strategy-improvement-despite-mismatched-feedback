import copy
import json
import unittest

from experiments.direct_reciprocity.baselines import TRAIN, TEST
from experiments.direct_reciprocity.core import Config
from experiments.direct_reciprocity.feedback import (TRANSFER, MIXTURES, derangement, score_table,
                                                      feedback_prompt, behavior_diagnostics)


class FeedbackTests(unittest.TestCase):
    def setUp(self):
        self.population = TRAIN[:4]
        self.assessment = [{'fitness': x, 'secret': 'must-not-leak'} for x in (1, 3, 2, 4)]
        self.mapping = derangement(4, 3)

    def test_shuffle_preserves_values_and_breaks_pairing(self):
        before = copy.deepcopy(self.assessment)
        rows = score_table(self.population, self.assessment, 'shuffled', self.mapping)
        self.assertEqual(sorted(r['fitness'] for r in rows), [1, 2, 3, 4])
        self.assertTrue(all(r['fitness'] != self.assessment[i]['fitness'] for i, r in enumerate(rows)))
        self.assertEqual(self.assessment, before)
        self.assertEqual(self.mapping, derangement(4, 3))
        with self.assertRaises(ValueError):
            derangement(1, 3)

    def test_hidden_has_no_scores_or_extra_assessment(self):
        prompt = feedback_prompt(Config(), self.population, 1, self.assessment, 'hidden', self.mapping)
        self.assertNotIn('CUMULATIVE TRAINING FITNESS', prompt)
        self.assertNotIn('must-not-leak', prompt)
        for p in self.population:
            self.assertIn(json.dumps(p.code)[1:-1], prompt)

    def test_true_and_shuffled_differ_only_in_table(self):
        a = feedback_prompt(Config(), self.population, 1, self.assessment, 'true', self.mapping)
        b = feedback_prompt(Config(), self.population, 1, self.assessment, 'shuffled', self.mapping)
        for text, arm in [(a, 'true'), (b, 'shuffled')]:
            table = json.dumps(score_table(self.population, self.assessment, arm, self.mapping), sort_keys=True)
            if arm == 'true':
                normalized = text.replace(table, '<table>')
            else:
                self.assertEqual(normalized, text.replace(table, '<table>'))

    def test_transfer_disjoint_and_weights(self):
        self.assertFalse({p.key for p in TRANSFER} & {p.key for p in TRAIN + TEST})
        for weights in MIXTURES.values():
            self.assertAlmostEqual(sum(weights), 1)
            self.assertEqual(len(weights), len(TRANSFER))

    def test_diagnostics_known_behaviors(self):
        cooperator = behavior_diagnostics(TRAIN[0], Config())
        defector = behavior_diagnostics(TRAIN[1], Config())
        for label in cooperator:
            self.assertEqual(cooperator[label]['cooperation_first4'], 1)
            self.assertEqual(defector[label]['cooperation_first4'], 0)
            self.assertEqual(cooperator[label]['mutual_cooperation_last5'], 1)
            self.assertEqual(defector[label]['mutual_cooperation_last5'], 0)


if __name__ == '__main__':
    unittest.main()
