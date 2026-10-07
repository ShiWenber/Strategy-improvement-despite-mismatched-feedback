import tempfile
from pathlib import Path
import unittest

from experiments.direct_reciprocity.core import Config, Policy
from experiments.direct_reciprocity.baselines import TRAIN, TEST
from experiments.direct_reciprocity.specificity_assets import (panel, probes, probe_specs, diagnostic_block, tokenizer, ARMS)
from experiments.direct_reciprocity.specificity import choose, training_scores, holdout_job
from experiments.direct_reciprocity.specificity_analysis import holm, sign_swap_p


class SpecificityTests(unittest.TestCase):
    def test_panel_size_balance_and_source_separation(self):
        v, h = panel('V'), panel('H')
        self.assertEqual(len(v), 24)
        self.assertEqual(len(h), 12)
        self.assertFalse({p.key for _, p in v} & {p.key for _, p in h})
        self.assertFalse({p.key for _, p in v + h} & {p.key for p in TRAIN + TEST})
        for rows, count in [(v, 6), (h, 3)]:
            for fam in ('recovery', 'exploitation', 'random', 'memory'):
                self.assertEqual(sum(f == fam for f, _ in rows), count)
            for _, p in rows:
                p.compile()

    def test_cooperation_and_exploitation_instruments(self):
        cooperator = probes(TRAIN[0], Config(), 'F', repeats=2)
        defector = probes(TRAIN[1], Config(), 'F', repeats=2)
        self.assertEqual(cooperator['sustained_D']['mean']['unilateral_cooperation_last5'], 1)
        self.assertEqual(defector['sustained_D']['mean']['unilateral_cooperation_last5'], 0)
        self.assertEqual(cooperator['one_D_TFT']['mean']['not_recovered'], 0)
        self.assertEqual(defector['one_D_TFT']['mean']['not_recovered'], 1)
        self.assertEqual(defector['one_D_TFT']['mean']['recovery_time_capped'], 23)

    def test_holdout_has_natural_and_controlled_new_parameters(self):
        f, h = probe_specs('F'), probe_specs('H')
        self.assertEqual({s['forced'] for s in f}, {10})
        self.assertEqual({s['forced'] for s in h}, {0, 7})
        self.assertFalse({s['horizon'] for s in f} & {s['horizon'] for s in h})

    def test_matched_blocks_and_wrong_diagnosis_are_changed(self):
        a = diagnostic_block(probes(TRAIN[0], Config(), 'F', repeats=1))
        b = diagnostic_block(probes(TRAIN[1], Config(), 'F', repeats=1))
        self.assertEqual(ARMS, ('accurate', 'mismatched'))
        self.assertNotEqual(a, b)
        enc = tokenizer()
        target = len(enc.encode(a))
        for text in [b]:
            self.assertLessEqual(abs(len(enc.encode(text)) / target - 1), .05)

    def test_selection_ignores_holdout_and_keeps_ties(self):
        parent = {'metrics': {'S1': {'score': 3, 'status': 'ok'}}}
        def child(name, score, valid=True):
            return ({'id': name, 'valid': valid, 'holdout': 1000 if name == 'bad' else -1000},
                    {'metrics': {'S1': {'score': score, 'status': 'ok'}}})
        self.assertEqual(choose(parent, [child('good', 3.1), child('bad', 2.9)], 'S1')['winner'], 'good')
        self.assertIsNone(choose(parent, [child('tie', 3), child('invalid', 4, False)], 'S1')['winner'])

    def test_nested_repeats_use_identical_first_five(self):
        cfg = Config(rounds=5)
        pop = TRAIN[:3]
        a = training_scores(TRAIN[5], pop, 0, cfg, repeats=5)
        b = training_scores(TRAIN[5], pop, 0, cfg, repeats=7)
        self.assertEqual(a['S1'], b['S1'])
        self.assertEqual([r[:5] for r in b['peer_replicates']], a['peer_replicates'])
        self.assertEqual(b['games'], (2 + 13) * 7)

    def test_holdout_cannot_run_before_release(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(RuntimeError, 'not released'):
                holdout_job((tmp, 'parent', 'nonexistent'))

    def test_holm_and_exact_sign_swap(self):
        self.assertEqual(holm({'a': .01, 'b': .04, 'c': .03}), {'a': .03, 'c': .06, 'b': .06})
        self.assertAlmostEqual(sign_swap_p([1] * 5), .0625)
        self.assertEqual(sign_swap_p([0] * 5), 1)


if __name__ == '__main__':
    unittest.main()
