"""Condition dispatch barriers, durable data logs and shared native requests; no network."""
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import threading
from types import SimpleNamespace

import pytest

from experiments.direct_reciprocity import condition_generation as generation
from experiments.direct_reciprocity import specificity
from experiments.direct_reciprocity import run
from experiments.direct_reciprocity.core import Config
from experiments.direct_reciprocity.records import write_json, filehash, begin_request, digest
from experiments.direct_reciprocity.specificity_assets import SCORE_ARMS, information_prompt


def rows(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]


@pytest.mark.parametrize('content,finish_reason', [
    ('', 'stop'), ("def strategy(history, rng): return 'C'", 'length'),
    ('invalid python!', 'stop'), ("def strategy(history, rng): return 'X'", 'stop')])
def test_shared_validation_rejects_unusable_programs(content, finish_reason):
    record = dict(status='received', content=content, finish_reason=finish_reason)
    assert run.validate(record, 'fixture', Config(rounds=5)) is None
    assert record['status'] == 'invalid' and record['validation_error']


def test_shared_validation_accepts_fences_and_reuses_terminal_outcomes(monkeypatch):
    code = "def strategy(history, rng):\n    return 'C'"
    record = dict(status='received', content='```python\n' + code + '\n```', finish_reason='stop')
    policy = run.validate(record, 'fixture', Config(rounds=5))
    assert policy.code == code and record['status'] == 'valid' and record['code_hash'] == policy.key
    before = record.copy()

    def no_replay(*args):
        pytest.fail('Completed program validation must not replay matches')

    monkeypatch.setattr(run, 'match', no_replay)
    assert run.validate(record, 'fixture', Config()).key == policy.key and record == before
    invalid = dict(status='invalid', validation_error='previous failure')
    assert run.validate(invalid, 'fixture', Config()) is None
    assert invalid == dict(status='invalid', validation_error='previous failure')


@pytest.fixture
def batch(tmp_path):
    manifest = specificity.freeze(tmp_path, seeds=[901, 902], ranks=[1], arms=SCORE_ARMS)
    for cid in {j['context'] for j in manifest['jobs']}:
        write_json(tmp_path / 'contexts' / (cid + '.json'),
                   {'parent': {'name': 'parent', 'code': "def strategy(history, rng):\n    return 'C'\n"},
                    'prompts': {a: a + ' fixture scores' for a in SCORE_ARMS}})
    return tmp_path, manifest


def finish_fixture(root, job, status='valid'):
    write_json(Path(root) / 'requests_candidates' / (job['id'] + '.json'),
               {'status': status, 'prompt': job['arm'] + ' fixture scores', 'started_at': 1,
                'finished_at': 2, 'content': 'fixture', 'usage': {'total_tokens': 3}})
    write_json(Path(root) / 'candidates' / (job['id'] + '.json'), dict(job, valid=status == 'valid'))
    generation.append_data_log(root, job)
    return {'id': job['id'], 'valid': status == 'valid'}


def test_frozen_order_and_function_parameter_preserve_shared_prompt(batch):
    root, manifest = batch
    assert manifest['generation_order'] == ['score', 'accurate', 'mismatched']
    assert [j['arm'] for j in manifest['jobs']] == ['score'] * 4 + ['accurate'] * 4 + ['mismatched'] * 4
    assert manifest['arm_positions'] == {'score': 0, 'accurate': 1, 'mismatched': 2}
    orders = [[(j['seed'], j['rank'], j['draw']) for j in manifest['jobs'] if j['arm'] == a] for a in SCORE_ARMS]
    assert orders[0] == orders[1] == orders[2]
    base, reports = 'same code and genuine scores', {'accurate': 'OWN REPORT', 'mismatched': 'DONOR REPORT'}
    for arm in SCORE_ARMS:
        prompt = information_prompt(base, arm, reports)
        assert prompt.startswith(base) and prompt.endswith('Return only the new strategy source.\n')
        assert ('OWN REPORT' in prompt) == (arm == 'accurate')
        assert ('DONOR REPORT' in prompt) == (arm == 'mismatched')
    with pytest.raises(ValueError, match='differs'):
        generation.generate_candidate(root, manifest['jobs'][0], 'accurate')


def test_complete_condition_barriers_hold_with_multiple_workers_and_resume(batch):
    root, manifest = batch
    completed, lock = [], threading.Lock()
    slow_started, release_slow, matching_started = threading.Event(), threading.Event(), threading.Event()
    slow_id = [j['id'] for j in manifest['jobs'] if j['arm'] == 'score'][-1]

    def generate(arg):
        directory, job = arg
        if job['id'] == slow_id:
            slow_started.set()
            assert release_slow.wait(timeout=10)
        if job['arm'] != 'score':
            matching_started.set()
        with lock:
            if job['arm'] == 'accurate':
                assert completed.count('score') == 4
            if job['arm'] == 'mismatched':
                assert completed.count('score') == completed.count('accurate') == 4
        result = finish_fixture(directory, job)
        with lock:
            completed.append(job['arm'])
        return result

    with ThreadPoolExecutor(max_workers=1) as runner:
        result = runner.submit(generation.generate_conditions, root, manifest, 3, generate)
        try:
            assert slow_started.wait(timeout=10)
            assert not matching_started.wait(timeout=.1)
        finally:
            release_slow.set()
        result.result(timeout=10)
    assert completed == ['score'] * 4 + ['accurate'] * 4 + ['mismatched'] * 4
    for arm in SCORE_ARMS:
        log = rows(generation.log_path(root, arm))
        assert len(log) == 4 and {r['arm'] for r in log} == {arm}
        assert {r['status'] for r in log} == {'valid'}
        assert all(r['record_sha256']['requests_candidates/' + r['id'] + '.json'] ==
                   filehash(root / 'requests_candidates' / (r['id'] + '.json')) for r in log)
    original_logs = {a: generation.log_path(root, a).read_bytes() for a in SCORE_ARMS}

    def resume(arg):
        directory, job = arg
        generation.append_data_log(directory, job)
        return {'id': job['id'], 'cached': True}

    generation.generate_conditions(root, manifest, 3, resume)
    assert {a: generation.log_path(root, a).read_bytes() for a in SCORE_ARMS} == original_logs


def test_failed_condition_stops_later_arms_and_keeps_partial_data_log(batch):
    root, manifest = batch
    dispatched = []

    def fail(arg):
        directory, job = arg
        dispatched.append(job['arm'])
        finish_fixture(directory, job, 'api_error')
        (Path(directory) / 'candidates' / (job['id'] + '.json')).unlink()
        raise RuntimeError('fixture transport failure')

    with pytest.raises(RuntimeError, match='stopped after errors'):
        generation.generate_conditions(root, manifest, 1, fail)
    assert dispatched == ['score']
    log = rows(generation.log_path(root, 'score'))
    assert len(log) == 4 and Counter(r['status'] for r in log) == {'api_error': 1, 'pending': 3}
    with pytest.raises(RuntimeError, match='Complete score'):
        generation.generate_conditions(root, manifest, 1, fail, arm='accurate')
    assert all(r['status'] == 'pending' for r in rows(generation.log_path(root, 'accurate')))


def test_explicit_arm_generation_and_log_export_include_evaluation_records(batch):
    root, manifest = batch
    generation.generate_conditions(root, manifest, 2, lambda arg: finish_fixture(*arg), arm='score')
    assert not any((root / 'candidates' / (j['id'] + '.json')).exists() for j in manifest['jobs'] if j['arm'] != 'score')
    job = manifest['jobs'][0]
    write_json(root / 'selection_scores' / (job['id'] + '.json'), {'S3': 2})
    write_json(root / 'holdout' / (job['id'] + '.json'), {'gain': .1})
    before = {p: p.read_bytes() for folder in ('requests_candidates', 'candidates', 'selection_scores', 'holdout')
              for p in (root / folder).glob('*.json')}
    generation.write_arm_logs(root, manifest)
    log = next(r for r in rows(generation.log_path(root, 'score')) if r['id'] == job['id'])
    assert log['selection_scores'] == {'S3': 2} and log['holdout'] == {'gain': .1}
    assert all(p.read_bytes() == contents for p, contents in before.items())


@pytest.mark.parametrize('provider,mode', [('deepseek', 'on'), ('qwen', 'off'), ('qwen', 'on')])
def test_shared_native_transport_preserves_parameters_and_reuses_completed_requests(batch, monkeypatch, provider, mode):
    import openai
    from experiments.config import load_env
    root, manifest = batch
    job, sent = manifest['jobs'][0], []
    spec = generation.specification('score fixture scores', provider, mode)
    code = "def strategy(history, rng):\n    return 'C'\n"

    class Stream:
        response = SimpleNamespace(status_code=200, http_version='HTTP/1.1', headers={'x-request-id': 'offline'})

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def __iter__(self):
            yield SimpleNamespace(id='offline-response', model=spec['model'], usage=None,
                                  choices=[SimpleNamespace(index=0, delta=SimpleNamespace(content=code,
                                      reasoning_content='offline reasoning' if mode == 'on' else ''), finish_reason='stop')],
                                  model_dump=lambda: {'offline': True})

    class Client:
        def __init__(self, **kwargs):
            assert kwargs['max_retries'] == 0
            self.chat = self.completions = self

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def create(self, **kwargs):
            sent.append(kwargs)
            return Stream()

    monkeypatch.setattr(openai, 'OpenAI', Client)
    monkeypatch.setattr(load_env, 'get_api_key', lambda p: 'offline-secret')
    monkeypatch.setattr(load_env, 'get_base_url', lambda p: 'https://offline.invalid')
    first = generation.generate_candidate(root, job, 'score', provider=provider, mode=mode)
    assert first['valid']
    expected = {k: v for k, v in spec.items() if k not in ('provider', 'prompt')}
    expected['messages'] = [{'role': 'user', 'content': spec['prompt']}]
    assert sent == [expected]
    saved = root / 'requests_candidates' / (job['id'] + '.json')
    before = saved.read_bytes()
    # Recover a candidate container from a durable response without another request.
    (root / 'candidates' / (job['id'] + '.json')).unlink()
    again = generation.generate_candidate(root, job, 'score', provider=provider, mode=mode)
    assert again['valid'] and saved.read_bytes() == before and sent == [expected]
    cached = generation.generate_candidate(root, job, 'score', provider=provider, mode=mode)
    assert cached['cached'] and sent == [expected]
    with pytest.raises(RuntimeError, match='identity collision'):
        generation.generate_candidate(root, job, 'score', provider=provider, mode='off' if mode == 'on' else 'on')
    assert sent == [expected]


def test_uncertain_native_request_is_logged_without_retry(batch, monkeypatch):
    root, manifest = batch
    job = manifest['jobs'][0]
    spec = generation.specification('score fixture scores', 'qwen', 'on')
    begin_request(root / 'requests_candidates' / (job['id'] + '.json'), spec)
    with pytest.raises(RuntimeError, match='Uncertain'):
        generation.generate_candidate(root, job, 'score', provider='qwen', mode='on')
    log = rows(generation.log_path(root, 'score'))[-1]
    assert log['status'] == 'requested' and log['candidate'] is None


@pytest.mark.parametrize('relative,provider,mode', [
    ('feedback_specificity_v2', 'deepseek', 'off'),
    ('feedback_specificity_thinking_384k_20260923', 'deepseek', 'on'),
    ('qwen3_8/off', 'qwen', 'off'), ('qwen3_8/on', 'qwen', 'on')])
def test_shared_settings_preserve_all_archived_request_fingerprints(relative, provider, mode):
    root = Path(__file__).resolve().parents[1] / 'results' / relative
    for path in (root / 'requests_candidates').glob('*.json'):
        saved = json.loads(path.read_text(encoding='utf-8-sig'))
        spec = generation.specification(saved['prompt'], provider, mode)
        assert saved['fingerprint'] == digest(json.dumps(spec, sort_keys=True)), path
        assert all(saved[key] == value for key, value in spec.items())
