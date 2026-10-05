import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch
from experiments.direct_reciprocity.core import Config
from experiments.direct_reciprocity.diagnostics import implementation_hash
from experiments.direct_reciprocity.run import read_json, write_json
from experiments.direct_reciprocity.control import prepare_control


class PrepareControlTests(unittest.TestCase):
    def test_fixed_budget_no_performance_feedback_even_when_invalid(self):
        prompts=[]
        def generate(generator,request_id,prompt,cfg):
            prompts.append((request_id,prompt))
            return None
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            cfg=Config(population_size=4,eliminate=2,generations=3,rounds=2,repeats=1)
            write_json(root/'matrix_plan.json',{'implementation_hash':implementation_hash(),
                       'provider':'test','model':'mock'})
            write_json(root/'minimal__paper_truncation__seed0'/'config.json',{'config':asdict(cfg)})
            with patch('experiments.direct_reciprocity.control.Generator.generate',generate):
                prepare_control(root,0)
            state=read_json(root/'independent_control'/'seed0'/'preparation_progress.json')
            self.assertEqual(len(prompts),4)
            self.assertEqual([x[0] for x in prompts],['sample0004','sample0005','sample0006','sample0007'])
            self.assertEqual(state['valid'],0)
            self.assertEqual(state['attempted'],4)
            self.assertFalse(state['selection_performed'])
            self.assertTrue(all('TRAINING PERFORMANCE' not in p and 'PARENT:' not in p for _,p in prompts))


if __name__=='__main__':
    unittest.main()
