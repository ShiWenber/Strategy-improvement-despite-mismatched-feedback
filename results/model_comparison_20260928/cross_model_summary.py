"""Recompute four model/configuration mainline summaries and verify paired tests."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]

# Where the frozen raw contrast lives. The Qwen top-level file holds only the
# focus contrasts, while the per-mode files hold the full per-arm results.
FROZEN_TAU = {
    ('DeepSeek', 'Off'): ('results/feedback_specificity_v2/ANALYSIS.json', ('primary',)),
    ('DeepSeek', 'On'): ('results/feedback_specificity_thinking_384k_20260923/ANALYSIS.json',
                         ('focus_holm_two', 'thinking_accurate_minus_mismatched')),
    ('Qwen', 'Off'): ('results/qwen3_8/ANALYSIS.json', ('focus', 'off')),
    ('Qwen', 'On'): ('results/qwen3_8/ANALYSIS.json', ('focus', 'on')),
}
RESULT_FILES = {
    ('DeepSeek', 'Off'): 'results/feedback_specificity_v2/ANALYSIS.json',
    ('DeepSeek', 'On'): 'results/feedback_specificity_thinking_384k_20260923/ANALYSIS.json',
    ('Qwen', 'Off'): 'results/qwen3_8/off/ANALYSIS.json',
    ('Qwen', 'On'): 'results/qwen3_8/on/ANALYSIS.json',
}


def read(relative):
    return json.loads((ROOT / relative).read_text(encoding='utf-8'))


def dig(node, keys):
    for key in keys:
        node = node[key]
    return node


def result_block(model, mode, payload):
    """The two thinking runs and the Qwen runs wrap their result under a key."""
    if model == 'DeepSeek' and mode == 'On':
        return payload['thinking']
    if model == 'Qwen':
        return payload['result']
    return payload


def frozen_raw_contrast(model, mode):
    """Frozen mean, interval, seed values, and sign-swap p for the raw contrast."""
    relative, keys = FROZEN_TAU[(model, mode)]
    return dig(read(relative), keys)


def raw_seed_values(result):
    return (np.asarray(result['raw']['accurate']['metrics']['default/score']['seed_values'], dtype=float)
            - np.asarray(result['raw']['mismatched']['metrics']['default/score']['seed_values'], dtype=float))


def sign_swap(values):
    """Exact paired sign-swap p over the 20 population means."""
    values = np.asarray(values, dtype=float)
    observed = abs(values.sum())
    index = np.arange(1 << len(values), dtype=np.uint32)
    permuted = np.zeros(len(index))
    for j, value in enumerate(values):
        permuted += np.where((index >> j) & 1, value, -value)
    return float(np.mean(np.abs(permuted) >= observed - 1e-12))


def main():
    statistics, sources = {}, {}
    for (model, mode), relative in RESULT_FILES.items():
        result = result_block(model, mode, read(relative))
        contrast = frozen_raw_contrast(model, mode)
        values = raw_seed_values(result)
        assert np.allclose(values, contrast['seed_values'], atol=1e-12, rtol=0)
        assert abs(sign_swap(values) - contrast['sign_swap_p']) < 1e-12
        key = model + '/' + mode.upper()
        statistics[key] = {
            'raw_mismatched': result['raw']['mismatched']['metrics']['default/score'],
            's3_mismatched': result['selected']['S3/mismatched']['metrics']['default'],
            'raw_accurate_minus_mismatched': {k: contrast[k] for k in ['n_seeds', 'seed_values', 'mean', 'ci95', 'sign_swap_p']}}
        sources[key] = relative
    report = {'sources': sources, 'statistics': statistics,
              'unit': '20 shared independent populations; 3 parents per population',
              'interval': 'Unadjusted population bootstrap intervals',
              'note': 'Two report conditions only. S3 uses V; H was previously used in follow-ups.'}
    destination = ROOT / 'results/model_comparison_20260928/cross_model_mainline_data.json'
    destination.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print('Recomputed four model/configuration mainline summaries')


if __name__ == '__main__':
    main()
