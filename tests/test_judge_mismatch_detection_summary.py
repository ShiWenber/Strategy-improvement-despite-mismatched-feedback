import json

from experiments.direct_reciprocity import judge_mismatch_detection_summary as analysis


def test_extract_trace_sends_complete_trace_in_one_request(monkeypatch):
    trace = 'Opening context\n' + 'Reasoning about the report.\n' * 4000 + 'Final resolution'
    summary = 'Verbatim report provenance.\n' * 4000
    calls = []
    client = object()

    def summarize(actual_client, system, user):
        calls.append((actual_client, system, user))
        return summary

    monkeypatch.setattr(analysis, '_call_summary', summarize)

    result = analysis.extract_trace(client, trace, 'The measured parent behavior')

    assert len(calls) == 1
    assert calls[0][0] is client
    assert trace in calls[0][2]
    assert 'The measured parent behavior' in calls[0][2]
    assert result == {'summary': summary.strip()}


def test_process_judges_cached_summary_without_length_metadata(tmp_path, monkeypatch):
    job = analysis.Job('s200-rank1-d0-pos0', 's200-rank1', 'mismatched', 0)
    summary = {'summary': 'The report might describe a different parent.'}
    summaries = tmp_path / 'summaries'
    summaries.mkdir()
    (summaries / f'{job.job_id}.json').write_text(json.dumps(summary), encoding='utf-8')
    monkeypatch.setattr(analysis, 'OUT', tmp_path)
    monkeypatch.setattr(analysis, 'load_record', lambda _job_id: {
        'status': 'valid', 'reasoning_content': 'Complete reasoning trace'})
    monkeypatch.setattr(analysis, 'report_block', lambda _context, _arm: 'Measured behavior')
    judged = []

    def judge(text, block):
        judged.append((text, block))
        return {'ok': True, 'origin_choice': 'questions_its_origin'}

    monkeypatch.setattr(analysis, 'judge_summary', judge)

    result = analysis.process(job)

    assert judged == [(summary['summary'], 'Measured behavior')]
    assert result['ok']
    assert result['origin_choice'] == 'questions_its_origin'
    assert json.loads((tmp_path / 'judgments' / f'{job.job_id}.json').read_text(encoding='utf-8')) == result
