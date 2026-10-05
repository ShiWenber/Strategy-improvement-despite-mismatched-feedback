import unittest
from dataclasses import replace
from experiments.direct_reciprocity.core import Config, PolicyError, match, evaluate, update_archive, act, RandomView
from experiments.direct_reciprocity.baselines import TRAIN, TEST, policy


class DirectReciprocityTests(unittest.TestCase):
    def setUp(self):
        self.cfg = Config(rounds=10, repeats=1)
        self.c, self.d, self.tft = TRAIN[:3]

    def test_payoffs(self):
        for a,b,want in ((self.c,self.c,[30,30]),(self.c,self.d,[0,50]),
                         (self.d,self.c,[50,0]),(self.d,self.d,[10,10]),
                         (self.tft,self.d,[9,14])):
            self.assertEqual(match(a,b,self.cfg,0)['scores'],want)

    def test_noise_is_executed_history(self):
        self.assertEqual(match(self.c,self.c,replace(self.cfg,noise=1),0)['scores'],[10,10])
        self.assertEqual(match(self.d,self.d,replace(self.cfg,noise=1),0)['scores'],[30,30])

    def test_reproducible_random_and_fresh_matches(self):
        a = match(TRAIN[5],self.tft,self.cfg,12)
        match(self.d,TRAIN[5],self.cfg,88)
        self.assertEqual(a,match(TRAIN[5],self.tft,self.cfg,12))

    def test_simultaneous_bilateral_view(self):
        copy = policy('copy', "return 'C' if not history else history[-1][1]")
        self.assertEqual(match(copy,self.d,self.cfg,2)['scores'],[9,14])

    def test_no_silent_bad_action(self):
        for body in ("return True", "return 'cooperate'", "while True:\n    pass"):
            with self.assertRaises(PolicyError):
                match(policy('bad',body),self.c,self.cfg,0)
        with self.assertRaises(PolicyError):
            match(policy('mutate', "history.append(('C','C'))\nreturn 'C'"),self.c,self.cfg,0)

    def test_single_character_wrong_action_is_rejected(self):
        # Every body above is multi-character or None, so a naive length check
        # would reject them too. These one-character returns are what reach the
        # payoff table instead of raising, turning a clear PolicyError into a
        # KeyError crash on a live run.
        for body in ("return 'c'","return 'd'","return 'X'","return '0'","return 1","return 1.0"):
            with self.assertRaises(PolicyError):
                match(policy('wrong',body),self.c,self.cfg,0)

    def test_deterministic_match_is_seat_symmetric(self):
        # Swapping the two seats must reverse the scores exactly. The random
        # streams are positional rather than per-policy, so a stochastic
        # strategy legitimately draws differently on each seat and is excluded.
        # This is what pins the right-hand history view: a mirrored history turns
        # a right-hand strategy into a different strategy and the scores stop
        # reversing. Suspect TFT-like baselines break first.
        pool=[p for p in TRAIN+TEST if 'rng.' not in p.code and 'random.' not in p.code]
        self.assertGreater(len(pool),10)
        cfg=Config(rounds=10,repeats=1,noise=0)
        for a in pool:
            for b in pool:
                self.assertEqual(match(a,b,cfg,3)['scores'],
                                 match(b,a,cfg,3)['scores'][::-1],
                                 f'{a.name} vs {b.name} is not seat-symmetric')

    def test_right_hand_strategy_reads_opponent_actions(self):
        # The seat-symmetry test fails in aggregate; this localises the fault.
        # A strategy that defects once and then copies history[-1][1] must see
        # the opponent's last action and switch to cooperation. Under a
        # mirrored history it reads its own action and defects for good.
        cfg=Config(rounds=10,repeats=1,noise=0)
        defect_then_copy="return 'D' if not history else ('C' if history[-1][1]=='C' else 'D')"
        # Same strategy, same opponent, each seat in turn: identical play, so the
        # scores must be exact mirrors. A mirrored history breaks only one seat.
        self.assertEqual(match(self.c,policy('right',defect_then_copy),cfg,3)['scores'],[27,32])
        self.assertEqual(match(policy('left',defect_then_copy),self.c,cfg,3)['scores'],[32,27])

    def test_peer_no_self_and_weighting(self):
        result=evaluate([self.c,self.d],[self.c],self.cfg,0)
        self.assertAlmostEqual(result[0]['fitness'],12)
        self.assertAlmostEqual(result[1]['fitness'],50)

    def test_archive_dedup_and_no_mutation(self):
        archive=[self.c]
        result=evaluate([self.c,self.d],archive,self.cfg,0)
        updated=update_archive(archive,[self.c,self.d],result,2)
        self.assertEqual(len(updated),2)
        self.assertEqual(archive,[self.c])

    def test_all_baselines_execute(self):
        for a in TRAIN+TEST:
            result=match(a,self.tft,self.cfg,0)
            self.assertEqual(len(result['scores']),2)



class SelectionAndPromptTests(unittest.TestCase):
    def test_truncation_keeps_population_size_and_parents(self):
        from experiments.direct_reciprocity.selection import selection_plan
        population=TRAIN[:12]
        evaluation=[{'fitness':100*i} for i in range(12)]
        cfg=Config()
        kept,jobs=selection_plan(population,evaluation,cfg,0)
        destinations=list(kept)+[d for d,p in jobs]
        self.assertEqual(sorted(destinations),list(range(12)))
        self.assertTrue(all(0<=p<12 for d,p in jobs))
        self.assertEqual((kept,jobs),selection_plan(population,evaluation,cfg,0))
        self.assertEqual(set(kept),set(range(6,12)))

    def test_prompt_treatments_and_no_holdout_leak(self):
        from experiments.direct_reciprocity.prompts import build_prompt
        evaluation=[{'key':p.key,'fitness':100} for p in TRAIN[:2]]
        prompts={name:build_prompt(Config(prompt=name),TRAIN[0],TRAIN[:2],evaluation)
                 for name in ('minimal','score','full')}
        self.assertNotIn('TRAINING PERFORMANCE',prompts['minimal'])
        self.assertIn('TRAINING PERFORMANCE',prompts['score'])
        self.assertNotIn('TRAINING POPULATION SOURCE',prompts['score'])
        self.assertIn('TRAINING POPULATION SOURCE',prompts['full'])
        for prompt in prompts.values():
            self.assertNotIn('TF2T',prompt)

    def test_durable_request_reuse_and_identity(self):
        import tempfile
        from pathlib import Path
        from experiments.direct_reciprocity.run import Generator
        class Response:
            id='response-test'
            model='mock'
            usage=None
            choices=[type('Choice',(),{'message':type('Message',(),{'content':"def strategy(history, rng):\n    return 'C'\n"})(), 'finish_reason':'stop'})()]
        class Client:
            def __init__(self):
                self.calls=0
                self.chat=self
                self.completions=self
            def create(self,**kwargs):
                self.calls+=1
                return Response()
        with tempfile.TemporaryDirectory() as temp:
            gen=Generator(Path(temp),'test','mock',1)
            gen.client=Client()
            first=gen.generate('one','prompt',Config(rounds=2))
            again=gen.generate('one','prompt',Config(rounds=2))
            self.assertEqual(first,again)
            self.assertEqual(gen.client.calls,1)
            with self.assertRaises(RuntimeError):
                gen.generate('one','different prompt',Config(rounds=2))

class RunReplayTests(unittest.TestCase):
    def test_complete_run_resume_does_not_generate_again(self):
        import tempfile
        from unittest.mock import patch
        from experiments.direct_reciprocity.run import run, read_json
        from pathlib import Path
        calls=[]
        def fake_generate(self,request_id,prompt,cfg):
            calls.append(request_id)
            return policy(request_id,"return 'C' if not history else history[-1][1]")
        with tempfile.TemporaryDirectory() as temp:
            cfg=Config(population_size=4,eliminate=2,generations=2,rounds=3,repeats=1)
            with patch('experiments.direct_reciprocity.run.Generator.generate',fake_generate):
                run(cfg,temp,'test','mock')
            directory=Path(temp)/'minimal__paper_truncation__seed0'
            last=read_json(directory/'generation_001.json')
            self.assertEqual(last['status'],'complete')
            self.assertEqual(len(last['next_population']),4)
            self.assertEqual(len(calls),6)
            # Initialization is restored through its durable Generator cache in
            # production; here the mock verifies only that no offspring rerun.
            calls.clear()
            with patch('experiments.direct_reciprocity.run.Generator.generate',fake_generate):
                run(cfg,temp,'test','mock')
            self.assertEqual(calls,[f'initial-{i}' for i in range(4)])
            self.assertEqual(last,read_json(directory/'generation_001.json'))



class MatrixDiagnosticsTests(unittest.TestCase):
    def test_matrix_has_15_unique_cells(self):
        from experiments.direct_reciprocity.matrix import cells
        planned=cells(range(5))
        self.assertEqual(len(planned),15)
        self.assertEqual(len({tuple(r.values()) for r in planned}),15)
        self.assertTrue(all(r['selection']=='paper_truncation' for r in planned))

    def test_interrupted_future_children_not_in_evaluation_budget(self):
        import tempfile
        from pathlib import Path
        from experiments.direct_reciprocity.run import write_json
        from experiments.direct_reciprocity.diagnostics import request_budget
        with tempfile.TemporaryDirectory() as temp:
            for name in ('initial-0','g001-child000','g002-child000'):
                write_json(Path(temp)/(name+'.json'),{'fingerprint':name,'status':'valid','usage':{'total_tokens':10}})
            self.assertEqual(request_budget([temp],0)['requests'],1)
            self.assertEqual(request_budget([temp],1)['total_tokens'],20)

    def test_behavior_profile_depends_on_actions_not_source(self):
        from experiments.direct_reciprocity.diagnostics import behavior_profile
        self.assertEqual(behavior_profile(policy('a',"return 'C'")),
                         behavior_profile(policy('b',"x = 'C'\nreturn x")))
        self.assertNotEqual(behavior_profile(TRAIN[0]),behavior_profile(TRAIN[1]))

    def test_incomplete_matrix_is_not_complete_analysis(self):
        import tempfile
        from pathlib import Path
        from experiments.direct_reciprocity.run import write_json
        from experiments.direct_reciprocity.matrix import cells
        from experiments.direct_reciprocity.analyze import summarize
        with tempfile.TemporaryDirectory() as temp:
            write_json(Path(temp)/'matrix_plan.json',{'cells':cells([0]),'generations':10})
            result=summarize(temp)
            self.assertFalse(result['all_main_cells_complete'])
            self.assertEqual(len(result['cells']),3)
            self.assertEqual(result['endpoints'],[])


class IndependentControlTests(unittest.TestCase):
    def test_hypothetical_slot_reproduces_original_fitness(self):
        from experiments.direct_reciprocity.control import hypothetical_fitness
        population=TRAIN[:4]
        cfg=Config(population_size=4,eliminate=2,rounds=5,repeats=2,noise=.1)
        assessment=evaluate(population,TRAIN,cfg,1)
        for slot, original in enumerate(population):
            self.assertAlmostEqual(hypothetical_fitness(original,slot,population,TRAIN,cfg,1),
                                   assessment[slot]['fitness'])


class RandomImportTests(unittest.TestCase):
    def test_import_forms_use_the_match_rng(self):
        from experiments.direct_reciprocity.core import Policy
        plain=policy('rng',"return 'C' if rng.random()<0.5 else 'D'")
        variants=[
            "import random\ndef strategy(history, rng):\n    return 'C' if random.random()<0.5 else 'D'\n",
            "import random as r\ndef strategy(history, rng):\n    return 'C' if r.random()<0.5 else 'D'\n",
            "def strategy(history, rng):\n    import random\n    return 'C' if random.random()<0.5 else 'D'\n",
            "from random import random as draw\ndef strategy(history, rng):\n    return 'C' if draw()<0.5 else 'D'\n",
        ]
        cfg=Config(rounds=30,repeats=1)
        for code in variants:
            for seed in (0,1,100):
                self.assertEqual(match(Policy('imported',code),TRAIN[2],cfg,seed),
                                 match(plain,TRAIN[2],cfg,seed))

    def test_import_does_not_change_global_random_or_other_match(self):
        import random
        from experiments.direct_reciprocity.core import Policy
        imported=Policy('imported',"import random\ndef strategy(history, rng):\n    random.seed(123)\n    return random.choice(('C','D'))\n")
        cfg=Config(rounds=10)
        state=random.getstate()
        first=match(TRAIN[5],TRAIN[2],cfg,9)
        match(imported,TRAIN[5],cfg,10)
        self.assertEqual(state,random.getstate())
        self.assertEqual(first,match(TRAIN[5],TRAIN[2],cfg,9))

    def test_random_constructor_without_seed_is_reproducible(self):
        imported=policy('imported',"import random\nr = random.Random()\nreturn r.choice(('C','D'))")
        self.assertEqual(match(imported,TRAIN[2],Config(rounds=30),4),
                         match(imported,TRAIN[2],Config(rounds=30),4))

    def test_other_imports_remain_outside_api(self):
        with self.assertRaises(PolicyError):
            policy('other',"import os\nreturn 'C'").compile()


class InitialReuseTests(unittest.TestCase):
    def test_revalidate_old_import_and_preserve_original_prompt(self):
        import tempfile
        from pathlib import Path
        from experiments.direct_reciprocity.reuse import reuse_initial
        from experiments.direct_reciprocity.run import write_json,read_json
        with tempfile.TemporaryDirectory() as temp:
            src=Path(temp)/'source'
            dest=Path(temp)/'dest'/'initial-1.json'
            raw={'provider':'test','model':'mock','status':'invalid','started_at':1,
                 'prompt':'original old prompt','fingerprint':'old-fingerprint',
                 'finish_reason':'stop','usage':{'total_tokens':100},
                 'content':"import random\ndef strategy(history, rng):\n    return random.choice(('C','D'))\n"}
            source=src/'initial-1.invalid-attempt0.json'
            write_json(source,raw)
            result=reuse_initial(src,dest,'initial-1',Config(rounds=2),'test','mock',read_json,write_json)
            self.assertIsNotNone(result)
            saved=read_json(dest)
            self.assertEqual(saved['prompt'],raw['prompt'])
            self.assertEqual(saved['fingerprint'],raw['fingerprint'])
            self.assertEqual(saved['original_status'],'invalid')
            self.assertEqual(read_json(source),raw)
            self.assertIsNone(reuse_initial(src,Path(temp)/'not-found.json','initial-10',Config(rounds=2),'test','mock',read_json,write_json))

if __name__ == '__main__':
    unittest.main()
