"""Offline synthetic integration: no network, no production result writes."""
from dataclasses import asdict
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from experiments.direct_reciprocity import specificity as runner
from experiments.direct_reciprocity import specificity_analysis as analysis
from experiments.direct_reciprocity import paired_control
from experiments.direct_reciprocity.baselines import TRAIN
from experiments.direct_reciprocity.core import Policy, Config
from experiments.direct_reciprocity.records import digest
from experiments.direct_reciprocity.records import write_json, read_json
from experiments.direct_reciprocity.specificity_assets import probes, ARMS, SCORE_ARMS


def synthetic_generate(self, identity, prompt, cfg):
    # A higher selection score deliberately accompanies a worse held-out payoff.
    p = Policy(identity, TRAIN[1 if '-d0-' in identity else 0].code)
    write_json(self.directory / (identity + '.json'), {
        'prompt': prompt, 'status': 'valid', 'started_at': time.time(),
        'code_hash': p.key, 'returned_model': 'offline-synthetic-fixture',
        'usage': {'total_tokens': 0, 'prompt_tokens': 0, 'completion_tokens': 0}})
    return p


def synthetic_selection(candidate, pop, slot, cfg):
    return {s: {'status': 'ok', 'score': 2. if candidate.code == TRAIN[1].code else 1.}
            for s in ('S1', 'S2', 'S3')}


def synthetic_holdout(candidate, cfg):
    score = 0. if candidate.code == TRAIN[1].code else 3.
    output = {s: {'status': 'ok', 'score': score, 'cooperation': score / 3,
                  'worst_score': score, 'families': {f: score for f in ('recovery', 'exploitation', 'random', 'memory')}}
              for s in ('default', 'noise01', 'long')}
    output['behavior'] = {'status': 'ok', 'probes': probes(candidate, cfg, 'H', repeats=1)}
    return output


class PipelineTest(unittest.TestCase):
    def test_frozen_flow_selects_without_holdout_and_audits(self):
        self.exercise_flow(ARMS)

    def test_score_flow_uses_the_same_generation_selection_and_analysis(self):
        self.exercise_flow(SCORE_ARMS)

    def exercise_flow(self, arms):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            with patch.object(runner, 'SEEDS', (901, 902)), patch.object(runner, 'RANKS', (1,)), \
                 patch.object(runner.Generator, 'generate', synthetic_generate), \
                 patch.object(runner, 'evaluate', lambda pop, archive, cfg, gen: [{'fitness': i} for i in range(len(pop))]), \
                 patch.object(runner, 'measured_selection', synthetic_selection), \
                 patch.object(runner, 'holdout_measure', synthetic_holdout):
                manifest = runner.freeze(root, arms=arms)
                for job in manifest['init_jobs']:
                    runner.initial_job((str(root), job))
                for seed in (901, 902):
                    runner.prepare_seed((str(root), seed))
                sealed = runner.make_prompts(root, manifest)
                self.assertEqual(sealed['effective_mismatch_contexts'], 0)
                for job in manifest['jobs']:
                    runner.candidate_job((str(root), job))
                identities = [('parent', f's{s}-rank1') for s in (901, 902)]
                identities += [('child', j['id']) for j in manifest['jobs']]
                for kind, identity in identities:
                    runner.evaluation_job((str(root), kind, identity))
                selection = runner.seal_selections(root, manifest)
                self.assertTrue(all(r['accepted'] for r in selection['rows']))
                self.assertEqual(manifest['arms'], list(arms))
                self.assertEqual(len(manifest['jobs']), 4 * len(arms))
                if 'score' in arms:
                    context = read_json(root / 'contexts/s901-rank1.json')
                    self.assertEqual(context['block_tokens']['score'], 0)
                    self.assertIn('CUMULATIVE TRAINING FITNESS:', context['prompts']['score'])
                self.assertFalse((root / 'holdout').exists())
                write_json(root / 'H_RELEASED.json', {
                    'selection_digest': digest((root / 'SELECTIONS_SEALED.json').read_text(encoding='utf-8'))})
                for kind, identity in identities:
                    runner.holdout_job((str(root), kind, identity))
                write_json(root / 'COMPLETE.json', {'synthetic': True})
                result = analysis.analyze(root)
                self.assertEqual(result['audit']['issues'], [])
                self.assertEqual(result['audit']['n_requests'], 24 + 4 * len(arms))
                self.assertEqual(result['selected']['S3/accurate']['metrics']['default']['mean'], -3)
                if 'score' in arms:
                    self.assertEqual(result['selected']['S3/score']['metrics']['default']['mean'], -3)
                    for provider, name in [('deepseek', 'on'), ('qwen', 'qwen3_8/off'), ('qwen', 'qwen3_8/on')]:
                        paired = root / name
                        prepared = paired_control.prepare(paired, root, provider)
                        self.assertEqual(prepared['arms'], list(SCORE_ARMS))
                        self.assertEqual(prepared['new_calls'], 12)
                        self.assertEqual(prepared['jobs'], manifest['jobs'])
                        self.assertEqual(paired_control.verify(paired, root, provider), prepared)
                        for job in prepared['jobs']:
                            context = read_json(paired / 'contexts' / (job['context'] + '.json'))
                            self.assertEqual(prepared['prompt_hashes'][job['id']], digest(context['prompts'][job['arm']]))
                self.assertFalse((root / 'REPORT.md').exists())

                reused = root / 'reused'
                subset = runner.freeze(reused, seeds=[901], ranks=[1], source=root)
                self.assertEqual(subset['requested_calls']['total'], 4)
                self.assertEqual(runner.population_root(reused), root.resolve())
                runner.make_prompts(reused, subset)
                for job in subset['jobs']:
                    runner.candidate_job((str(reused), job))
                identities = [('parent', 's901-rank1')] + [('child', j['id']) for j in subset['jobs']]
                for kind, identity in identities:
                    runner.evaluation_job((str(reused), kind, identity))
                runner.seal_selections(reused, subset)
                write_json(reused / 'H_RELEASED.json', {
                    'selection_digest': digest((reused / 'SELECTIONS_SEALED.json').read_text(encoding='utf-8'))})
                for kind, identity in identities:
                    runner.holdout_job((str(reused), kind, identity))
                write_json(reused / 'COMPLETE.json', {'synthetic': True})
                small = analysis.analyze(reused, '_reproduct')
                self.assertEqual(small['audit']['n_new_requests'], 4)
                self.assertEqual(small['audit']['n_reused_initial_requests'], 12)
                self.assertEqual(small['primary']['n_seeds'], 1)
                self.assertFalse((reused / 'REPORT_reproduct.md').exists())
                self.assertFalse((reused / 'initial').exists())
                self.assertFalse((reused / 'populations').exists())
                population = root / 'populations/s901.json'
                population.write_text(population.read_text(encoding='utf-8') + '\n', encoding='utf-8')
                with self.assertRaisesRegex(RuntimeError, 'Reused initialization changed'):
                    runner.check_manifest(reused)


if __name__ == '__main__':
    unittest.main()
