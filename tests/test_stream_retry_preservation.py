"""Failed streams remain inspectable across bounded transport retries; no network."""
import json
from types import SimpleNamespace

import httpx
import openai
import pytest

from experiments.config import load_env
from experiments.direct_reciprocity import condition_generation as generation
from experiments.direct_reciprocity.core import Config
from experiments.direct_reciprocity.records import read_json, write_json


class StatusFailure(RuntimeError):
    def __init__(self, status, *, body=None, headers=None):
        super().__init__('offline status failure')
        self.status_code = status
        self.body = body
        self.response = SimpleNamespace(headers=httpx.Headers(headers or {}))


def fake_transport(monkeypatch, failures, client_options=None):
    calls, sleeps = [], []

    class Stream:
        response = SimpleNamespace(status_code=200, http_version='HTTP/1.1', headers={})

        def __init__(self, attempt):
            self.attempt = attempt

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    class Client:
        def __init__(self, **kwargs):
            assert kwargs['max_retries'] == 0
            if client_options is not None:
                client_options.append(kwargs)
            self.chat = self.completions = self

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def create(self, **kwargs):
            calls.append(kwargs)
            return Stream(len(calls))

    def receive(stream, sink, progress):
        sink.write(json.dumps({'attempt': stream.attempt}) + '\n')
        sink.flush()
        progress(100 * stream.attempt)
        if stream.attempt <= len(failures):
            failure = failures[stream.attempt - 1]
            if failure == 'wrapped_transport':
                try:
                    raise httpx.ReadError('offline interrupted stream')
                except httpx.ReadError as exc:
                    raise openai.APIConnectionError(request=httpx.Request('POST', 'https://offline.invalid')) from exc
            raise failure
        return dict(content="def strategy(history, rng):\n    return 'C'\n",
                    reasoning_content='offline reasoning', usage={'total_tokens': 1},
                    finish_reason='stop', response_id='offline', returned_model='offline-fixture')

    monkeypatch.setattr(openai, 'OpenAI', Client)
    monkeypatch.setattr(load_env, 'get_api_key', lambda provider: 'offline-secret')
    monkeypatch.setattr(load_env, 'get_base_url', lambda provider: 'https://offline.invalid')
    monkeypatch.setattr(generation, 'receive_stream', receive)
    monkeypatch.setattr(generation.time, 'sleep', sleeps.append)
    import random
    monkeypatch.setattr(random, 'uniform', lambda start, end: .25)
    return calls, sleeps


def run_stream(root, retries=3):
    spec = generation.specification('offline fixture', 'qwen', 'on', model='offline-fixture')
    return generation.streamed_program(root, {'id': 'candidate'}, spec, Config(rounds=1),
                                       api_retries=retries)


def test_transport_and_rate_limit_retries_preserve_every_attempt(tmp_path, monkeypatch):
    calls, sleeps = fake_transport(monkeypatch, ['wrapped_transport', StatusFailure(429)])
    assert run_stream(tmp_path) is not None
    assert len(calls) == 3 and sleeps == [2.25, 60.25]
    archives = sorted((tmp_path / 'attempt_history').iterdir())
    assert len(archives) == 2
    for attempt, archive in enumerate(archives, 1):
        failed = read_json(archive / 'requests_candidates/candidate.json')
        assert failed['status'] == 'api_error'
        assert failed['retry_number'] == attempt
        assert failed['retry_delay_seconds'] == sleeps[attempt - 1]
        assert read_json(archive / 'streams/candidate.jsonl') == {'attempt': attempt}
        assert read_json(archive / 'request_progress/candidate.json')['characters_received'] == 100 * attempt
    assert read_json(tmp_path / 'requests_candidates/candidate.json')['status'] == 'valid'
    assert read_json(tmp_path / 'streams/candidate.jsonl') == {'attempt': 3}


@pytest.mark.parametrize('failure', [StatusFailure(400), RuntimeError('Stream ended without finish_reason')])
def test_unconfirmed_failures_are_preserved_without_retry(tmp_path, monkeypatch, failure):
    calls, sleeps = fake_transport(monkeypatch, [failure])
    with pytest.raises(RuntimeError, match='Request failed'):
        run_stream(tmp_path)
    assert len(calls) == 1 and sleeps == []
    assert not (tmp_path / 'attempt_history').exists()
    assert read_json(tmp_path / 'requests_candidates/candidate.json')['status'] == 'api_error'
    assert read_json(tmp_path / 'streams/candidate.jsonl') == {'attempt': 1}


def test_resuming_saved_non_retryable_error_does_not_issue_another_request(tmp_path, monkeypatch):
    calls, sleeps = fake_transport(monkeypatch, [])
    failed = dict(status='api_error', http_status=400, exception_chain=[
        {'module': 'httpx', 'type': 'HTTPStatusError'}])
    write_json(tmp_path / 'requests_candidates/candidate.json', failed)
    write_json(tmp_path / 'streams/candidate.jsonl', {'partial': True})
    with pytest.raises(RuntimeError, match='not a confirmed retryable failure'):
        run_stream(tmp_path)
    assert calls == sleeps == []
    assert read_json(tmp_path / 'requests_candidates/candidate.json') == failed
    assert read_json(tmp_path / 'streams/candidate.jsonl') == {'partial': True}


def test_resuming_transport_failure_archives_partial_stream_before_replacement(tmp_path, monkeypatch):
    calls, sleeps = fake_transport(monkeypatch, [])
    failed = dict(status='api_error', http_status=None, exception_chain=[
        {'module': 'httpx', 'type': 'ReadError'}])
    write_json(tmp_path / 'requests_candidates/candidate.json', failed)
    write_json(tmp_path / 'streams/candidate.jsonl', {'partial': True})
    write_json(tmp_path / 'request_progress/candidate.json', {'characters_received': 10})
    assert run_stream(tmp_path) is not None
    assert len(calls) == 1 and sleeps == []
    archive, = (tmp_path / 'attempt_history').iterdir()
    assert read_json(archive / 'requests_candidates/candidate.json') == failed
    assert read_json(archive / 'streams/candidate.jsonl') == {'partial': True}
    assert read_json(archive / 'request_progress/candidate.json')['characters_received'] == 10


@pytest.mark.parametrize('retry_after,expected', [('15', 60.25), ('90', 90.25),
                                               ('3600', 3600.25), ('3601', 60.25),
                                               ('-1', 60.25), ('nan', 60.25), ('invalid', 60.25)])
def test_rate_limit_honors_bounded_retry_after_and_minimum_wait(tmp_path, monkeypatch, retry_after, expected):
    failure = StatusFailure(429, headers={'Retry-After': retry_after, 'Authorization': 'offline-secret'})
    calls, sleeps = fake_transport(monkeypatch, [failure])
    assert run_stream(tmp_path) is not None
    assert len(calls) == 2 and sleeps == [expected]
    archive, = (tmp_path / 'attempt_history').iterdir()
    failed = read_json(archive / 'requests_candidates/candidate.json')
    assert failed['retry_after'] == retry_after
    assert 'Authorization' not in json.dumps(failed)
    assert 'offline-secret' not in json.dumps(failed)


def test_rate_limit_honors_http_date_retry_after(tmp_path, monkeypatch):
    from email.utils import formatdate
    monkeypatch.setattr(generation.time, 'time', lambda: 1_790_000_000.)
    retry_after = formatdate(1_790_000_120., usegmt=True)
    calls, sleeps = fake_transport(monkeypatch, [StatusFailure(429, headers={'Retry-After': retry_after})])
    assert run_stream(tmp_path) is not None
    assert len(calls) == 2 and sleeps == [120.25]
    archive, = (tmp_path / 'attempt_history').iterdir()
    assert read_json(archive / 'requests_candidates/candidate.json')['retry_after_seconds'] == 120.


@pytest.mark.parametrize('nested', [False, True])
def test_provider_error_fields_are_whitelisted_and_redacted(tmp_path, monkeypatch, nested):
    error = {'type': 'rate_limit', 'code': 'offline-secret', 'message': 'retry key offline-secret',
             'api_key': 'offline-secret', 'headers': {'Authorization': 'offline-secret'}}
    body = {'error': error} if nested else error
    failure = StatusFailure(429, body=body, headers={'Retry-After': 'offline-secret',
                                                   'X-Api-Key': 'offline-secret'})
    calls, sleeps = fake_transport(monkeypatch, [failure])
    with pytest.raises(RuntimeError, match='Request failed'):
        run_stream(tmp_path, retries=0)
    assert len(calls) == 1 and sleeps == []
    failed = read_json(tmp_path / 'requests_candidates/candidate.json')
    assert failed['provider_error'] == {'type': 'rate_limit', 'code': '[REDACTED]',
                                        'message': 'retry key [REDACTED]'}
    assert failed['retry_after'] == '[REDACTED]' and failed['retry_after_seconds'] is None
    assert 'X-Api-Key' not in json.dumps(failed)
    assert 'offline-secret' not in json.dumps(failed)


def test_resuming_saved_rate_limit_waits_only_remaining_retry_after(tmp_path, monkeypatch):
    calls, sleeps = fake_transport(monkeypatch, [])
    monkeypatch.setattr(generation.time, 'time', lambda: 1000.)
    failed = dict(status='api_error', http_status=429, finished_at=990., retry_after_seconds=120.)
    write_json(tmp_path / 'requests_candidates/candidate.json', failed)
    assert run_stream(tmp_path) is not None
    assert len(calls) == 1 and sleeps == [110.25]
    archive, = (tmp_path / 'attempt_history').iterdir()
    assert read_json(archive / 'requests_candidates/candidate.json') == failed


@pytest.mark.parametrize('setting', [None, '0'])
def test_default_transport_remains_sdk_managed_and_records_environment_mode(tmp_path, monkeypatch, setting):
    if setting is None:
        monkeypatch.delenv('DIRECT_RECIPROCITY_API_DIRECT', raising=False)
    else:
        monkeypatch.setenv('DIRECT_RECIPROCITY_API_DIRECT', setting)
    options = []
    calls, sleeps = fake_transport(monkeypatch, [], options)
    assert run_stream(tmp_path) is not None
    assert len(options) == 1 and 'http_client' not in options[0]
    assert options[0]['timeout'].connect == 30 and options[0]['timeout'].read == 3600
    saved = read_json(tmp_path / 'requests_candidates/candidate.json')
    assert saved['transport'] == {'direct': False, 'trust_env': True}
    assert len(calls) == 1 and sleeps == []
    assert 'transport' not in calls[0]


def test_direct_transport_uses_explicit_httpx_client_and_sdk_closes_it(tmp_path, monkeypatch):
    monkeypatch.setenv('DIRECT_RECIPROCITY_API_DIRECT', '1')
    monkeypatch.setenv('HTTPS_PROXY', 'http://proxy-must-not-be-used.invalid:7890')
    monkeypatch.setattr(load_env, 'get_api_key', lambda provider: 'offline-secret')
    monkeypatch.setattr(load_env, 'get_base_url', lambda provider: 'https://offline.invalid')
    clients, requests = [], []

    def respond(request):
        requests.append(request)
        chunk = {'id': 'offline', 'object': 'chat.completion.chunk', 'created': 1,
                 'model': 'offline-fixture', 'choices': [{'index': 0, 'finish_reason': 'stop',
                    'delta': {'content': "def strategy(history, rng):\n    return 'C'\n",
                              'reasoning_content': 'offline reasoning'}}]}
        return httpx.Response(200, headers={'content-type': 'text/event-stream'},
                              text='data: ' + json.dumps(chunk) + '\n\ndata: [DONE]\n\n')

    class DirectClient(httpx.Client):
        def __init__(self, **kwargs):
            assert kwargs['trust_env'] is False
            assert kwargs['timeout'].connect == 30 and kwargs['timeout'].read == 3600
            super().__init__(**kwargs, transport=httpx.MockTransport(respond))
            clients.append(self)

    monkeypatch.setattr(httpx, 'Client', DirectClient)
    before = generation.specification('offline fixture', 'qwen', 'on', model='offline-fixture')
    assert run_stream(tmp_path) is not None
    assert len(clients) == 1 and clients[0].is_closed
    assert len(requests) == 1 and requests[0].url.host == 'offline.invalid'
    saved = read_json(tmp_path / 'requests_candidates/candidate.json')
    assert saved['transport'] == {'direct': True, 'trust_env': False}
    assert generation.specification('offline fixture', 'qwen', 'on', model='offline-fixture') == before
    assert 'transport' not in json.loads(requests[0].content)
