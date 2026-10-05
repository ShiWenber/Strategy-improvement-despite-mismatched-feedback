import tempfile
from pathlib import Path
import unittest

from experiments.direct_reciprocity.feedback_selection import analyze
from experiments.direct_reciprocity.run import write_json


class SelectionDiagnosticTests(unittest.TestCase):
    def row(self, rid, training, test):
        return {'id': rid, 'context': 'seed0-rank1', 'seed': 0, 'arm': 'true',
                'valid': True, 'fallback': {'training': False},
                'child': {'name': rid, 'code': 'def strategy(history, rng):\n    return ' + repr('C' if rid == 'a' else 'D')},
                'deployed': {'training': {'score': training}},
                'delta': {s: {'score': training - 3 if s == 'training' else test}
                          for s in ('training', 'default', 'noise01', 'long')}}

    def check(self, a, b):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            write_json(root / 'parents' / 'seed0-rank1.json', {'training': {'score': 3}})
            write_json(root / 'outcomes' / 'a.json', a)
            write_json(root / 'outcomes' / 'b.json', b)
            return analyze(root)['selected'][0]

    def test_holdout_cannot_select(self):
        result = self.check(self.row('a', 4, -1), self.row('b', 3.5, 1))
        self.assertEqual(result['winner'], 'a')
        self.assertEqual(result['delta']['default'], -1)

    def test_tie_keeps_parent(self):
        result = self.check(self.row('a', 3, 1), self.row('b', 2.5, 2))
        self.assertFalse(result['accepted'])
        self.assertEqual(result['delta']['default'], 0)

    def test_invalid_cannot_win(self):
        a = self.row('a', 4, 1)
        a['valid'] = False
        result = self.check(a, self.row('b', 3.5, -1))
        self.assertEqual(result['winner'], 'b')


if __name__ == '__main__':
    unittest.main()
