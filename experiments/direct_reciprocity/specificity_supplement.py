"""Replay archived default-H payoffs using the project simulator."""
from dataclasses import replace
from pathlib import Path

from .core import Policy, versus
from .run import read_json
from .specificity import cfg_for
from .specificity_assets import panel


def replay_job(arg):
    root, kind, identity = arg
    root = Path(root)
    row = read_json(root / ('contexts' if kind == 'parent' else 'candidates') / (identity + '.json'))
    c = row if kind == 'parent' else read_json(root / 'contexts' / (row['context'] + '.json'))
    item = c['parent'] if kind == 'parent' else row['child']
    saved = read_json(root / 'holdout' / (identity + '.json'))
    if item is None:
        return {'id': identity, 'kind': kind, 'status': 'invalid_candidate_no_game_replay'}
    try:
        actual = versus(Policy(**item), [p for _, p in panel('H')], replace(cfg_for(c['seed']), repeats=20), 'specificity-H-default')
    except Exception as exc:
        expected = saved['measured']['default']
        return {'id': identity, 'kind': kind, 'status': 'failure_reproduced' if expected['status'] == 'failed' and expected['error_type'] == type(exc).__name__ else 'mismatch',
                'error_type': type(exc).__name__}
    expected = saved['measured']['default']
    errors = {'score': abs(actual['score'] / 100 - expected['score']),
              'cooperation': abs(actual['cooperation'] - expected['cooperation']),
              'worst_score': abs(actual['worst_score'] / 100 - expected['worst_score'])}
    return {'id': identity, 'kind': kind, 'status': 'ok' if max(errors.values()) <= 1e-12 else 'mismatch',
            'errors': errors, 'games_replayed': 240}
