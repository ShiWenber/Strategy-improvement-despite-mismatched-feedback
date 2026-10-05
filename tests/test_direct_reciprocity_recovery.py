import unittest
from unittest.mock import patch
from experiments.direct_reciprocity.core import Config, Policy, PolicyError
from experiments.direct_reciprocity.recover_evaluation import tolerate_holdout_failure


class EvaluationRecoveryTests(unittest.TestCase):
    def test_analysis_reports_missing_tests_without_zero_imputation(self):
        import tempfile
        from pathlib import Path
        from experiments.direct_reciprocity.run import write_json
        from experiments.direct_reciprocity.analyze import summarize
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            cells = [{'seed': 0, 'prompt': p, 'selection': 'paper_truncation'} for p in ('minimal', 'score')]
            write_json(root/'matrix_plan.json', {'cells': cells, 'generations': 1,
                       'rounds': 100, 'implementation_hash': 'test'})
            for cell in cells:
                folder = root/f"{cell['prompt']}__paper_truncation__seed0"
                failed = cell['prompt'] == 'score'
                result = {'score': None if failed else 300, 'cooperation': None if failed else 1,
                          'worst_score': None if failed else 200,
                          'status': 'runtime_failure' if failed else 'complete'}
                state = {'status': 'complete', 'generation': 0, 'assessment': [{'fitness': 300}],
                         'code_diversity': 1, 'behavior_diagnostics': {'distinct_valid_profiles': 1, 'profile_errors': []},
                         'budget_at_evaluation': {'requests': 12, 'total_tokens': 100},
                         'holdout': {'default': result}, 'test_configs': {'default': {'rounds': 100}}}
                write_json(folder/'generation_000.json', state)
                write_json(folder/'complete.json', {})
                write_json(folder/'config.json', {'implementation_hash': 'test'})
            report = summarize(root)
            failed = next(r for r in report['group_summaries'] if r['prompt']=='score')
            self.assertEqual(failed['runtime_failures'], 1)
            self.assertEqual(failed['n_successful'], 0)
            self.assertIsNone(failed['score_mean'])
            self.assertEqual(report['paired_contrasts'], [])

    def setUp(self):
        self.policy = Policy('allc', "def strategy(history, rng):\n    return 'C'\n")

    def test_successful_result_is_preserved_exactly(self):
        # Content must survive untouched and must not be relabelled as a failure.
        # Asserted by value, not identity: returning a semantically equal copy is
        # fine, silently mutating or annotating the payload is not.
        expected = {'score': 300, 'cooperation': 1, 'worst_score': 300}
        with patch('experiments.direct_reciprocity.recover_evaluation.versus', return_value=expected) as original:
            actual = tolerate_holdout_failure(self.policy, [], Config(), 'holdout-long', 6)
        self.assertEqual(actual, expected)
        self.assertNotIn('status', actual)
        self.assertNotIn('error', actual)
        original.assert_called_once_with(self.policy, [], Config(), 'holdout-long', 6)

    def test_failure_is_missing_not_zero_or_success(self):
        with patch('experiments.direct_reciprocity.recover_evaluation.versus', side_effect=PolicyError('budget')):
            result = tolerate_holdout_failure(self.policy, [], Config(), 'holdout-long', 6)
        self.assertEqual(result['status'], 'runtime_failure')
        self.assertIsNone(result['score'])
        self.assertIsNone(result['cooperation'])
        self.assertEqual(result['policy_key'], self.policy.key)

    def test_training_failures_and_programming_errors_propagate(self):
        for error, phase in [(PolicyError('budget'), 'archive'), (PolicyError('budget'), 'fixed'),
                             (ValueError('bug'), 'holdout-long')]:
            with patch('experiments.direct_reciprocity.recover_evaluation.versus', side_effect=error):
                with self.assertRaises(type(error)):
                    tolerate_holdout_failure(self.policy, [], Config(), phase)
