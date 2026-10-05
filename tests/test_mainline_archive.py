"""Guard the published two-condition archive against stale-arm data leakage."""
from collections import Counter
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RUNS = ['feedback_specificity_v2', 'feedback_specificity_thinking_384k_20260923',
        'qwen3_8/off', 'qwen3_8/on']


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


@pytest.mark.parametrize('relative', RUNS)
def test_archive_contains_only_complete_report_matching_pairs(relative):
    root = ROOT / 'results' / relative
    manifest = read(root / 'manifest.json')
    assert manifest['arms'] == ['accurate', 'mismatched']
    jobs = manifest['jobs']
    assert len(jobs) == 240
    assert Counter(j['arm'] for j in jobs) == {'accurate': 120, 'mismatched': 120}
    assert len({j['context'] for j in jobs}) == 60
    assert all(n == 2 for n in Counter((j['context'], j['arm']) for j in jobs).values())
    identities = {j['id'] for j in jobs}
    contexts = {j['context'] for j in jobs}
    for folder in ['candidates', 'requests_candidates']:
        assert {p.stem for p in (root / folder).glob('*.json')} == identities
    for folder in ['holdout', 'selection_scores']:
        assert {p.stem for p in (root / folder).glob('*.json')} == identities | contexts
    selections = read(root / 'SELECTIONS_SEALED.json')['rows']
    assert len(selections) == 360
    assert {r['arm'] for r in selections} == {'accurate', 'mismatched'}
    for job in jobs:
        context = read(root / 'contexts' / (job['context'] + '.json'))
        request = read(root / 'requests_candidates' / (job['id'] + '.json'))
        assert set(context['prompts']) == set(manifest['arms'])
        assert set(context['block_tokens']) == set(manifest['arms'])
        assert request['prompt'] == context['prompts'][job['arm']]
        # Keep original identifiers/positions, even when their positions have gaps.
        assert job['id'].endswith('pos' + str(job['position']))


def test_reasoning_annotations_match_the_retained_on_requests():
    jobs = read(ROOT / 'results/feedback_specificity_thinking_384k_20260923/manifest.json')['jobs']
    identities = {j['id'] for j in jobs}
    for folder in ['judgments', 'summaries']:
        paths = list((ROOT / 'results/mismatch_detection_jev' / folder).glob('*.json'))
        assert {p.stem for p in paths} == identities
        if folder == 'judgments':
            assert {read(p)['arm'] for p in paths} == {'accurate', 'mismatched'}
