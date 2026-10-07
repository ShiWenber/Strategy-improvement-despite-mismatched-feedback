import tempfile
import unittest
from pathlib import Path
from experiments.direct_reciprocity.core import Policy
from experiments.direct_reciprocity.records import write_json, read_json
from experiments.direct_reciprocity.analyze_control import summarize_controls


class ControlAnalysisTests(unittest.TestCase):
    def test_budget_and_winner_are_audited_and_missing_is_not_complete(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            cell = {'prompt': 'minimal', 'selection': 'paper_truncation', 'seed': 0}
            name = 'minimal__paper_truncation__seed0'
            write_json(root/'matrix_plan.json', {'cells': [cell], 'generations': 1})
            self.assertFalse(summarize_controls(root)['all_controls_complete'])
            policy = {'name': 'ALLC', 'code': "def strategy(history, rng):\n    return 'C'\n"}
            key = Policy(**policy).key
            folder = root/'independent_control/seed0'
            test = {'score': 300, 'cooperation': 1, 'worst_score': 300}
            write_json(root/name/'complete.json', {})
            write_json(root/name/'generation_000.json', {'status': 'complete',
                       'budget_at_evaluation': {'requests': 1}, 'holdout': {'default': test},
                       'test_configs': {'default': {'rounds': 100}}})
            write_json(folder/'pool.json', {'initial_keys': [key], 'shared_initial_requests': 1,
                       'policies': [policy]})
            write_json(folder/(name+'_selection.json'), [{'ordinal': 0, 'key': key, 'fitness': 300}])
            output = folder/(name+'.json')
            control = {'reference': name, 'seed': 0, 'request_budget': 1, 'candidate_pool_size': 1,
                       'champion': policy, 'training_fitness': 300, 'holdout': {'default': test}}
            write_json(output, control)
            report = summarize_controls(root)
            self.assertTrue(report['all_controls_complete'])
            self.assertEqual(report['summaries'][0]['mean_difference'], 0)
            control['request_budget'] = 2
            control['training_fitness'] = 400
            write_json(output, control)
            report = summarize_controls(root)
            self.assertFalse(report['all_controls_complete'])
            self.assertTrue(any('unequal request budgets' in issue for issue in report['protocol_issues']))
            self.assertTrue(any('training-only selection' in issue for issue in report['protocol_issues']))
