"""Cross-model report tables: read frozen analyses, recompute the paired contrasts.

Reads only the committed ``ANALYSIS.json`` files and prints the tables used by
``docs/direct_reciprocity/CROSS_MODEL_REPLICATION.md``. Nothing is written to any
results directory; the frozen artifacts are treated as read-only.

- The raw ``tau`` contrast is reported from the frozen payload, and both its
  per-population seed vector and its exact sign-swap p are recomputed as drift
  checks; the script asserts the recomputation matches the frozen record.
- ``tau_S3`` is *not* a frozen endpoint, so it is recomputed here from the frozen
  per-population seed vectors with the project's population-cluster bootstrap.

Usage (from the worktree root)::

    python results/model_comparison_20260928/cross_model_summary.py
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]

ARMS = ('score', 'accurate', 'mismatched')
BOOTSTRAP_DRAWS = 20000
BOOTSTRAP_SEED = 2026093004

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


def s3_seed_values(result):
    return (np.asarray(result['selected']['S3/accurate']['metrics']['default']['seed_values'], dtype=float)
            - np.asarray(result['selected']['S3/mismatched']['metrics']['default']['seed_values'], dtype=float))


def cluster_bootstrap(values, draws=BOOTSTRAP_DRAWS, seed=BOOTSTRAP_SEED):
    """Percentile interval over the 20 population means."""
    values = np.asarray(values, dtype=float)
    n = len(values)
    rng = np.random.default_rng(seed)
    boot = values[rng.integers(0, n, size=(draws, n))].mean(axis=1)
    return float(values.mean()), float(np.quantile(boot, .025)), float(np.quantile(boot, .975))


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
    results = {}
    for key in FROZEN_TAU:
        model, mode = key
        results[key] = result_block(model, mode, read(RESULT_FILES[key]))

    print('## 原始候选（未经筛选）—— tau 取自冻结记录\n')
    print('| 模型 | 模式 | raw Score | raw Accurate | raw Mismatched | tau = A-M | tau CI95 | 符号交换 p |')
    print('|---|---|---:|---:|---:|---:|---|---:|')
    for key in FROZEN_TAU:
        model, mode = key
        result = results[key]
        node = frozen_raw_contrast(model, mode)
        means = {arm: result['raw'][arm]['metrics']['default/score']['mean'] for arm in ARMS}
        tau = raw_seed_values(result)
        assert abs(tau.mean() - node['mean']) < 1e-9, \
            '{}/{}: recomputed tau {} != frozen {}'.format(model, mode, tau.mean(), node['mean'])
        p = sign_swap(tau)
        assert abs(p - node['sign_swap_p']) < 1e-6, \
            '{}/{}: recomputed p {} != frozen {}'.format(model, mode, p, node['sign_swap_p'])
        print('| {} | {} | {:+.5f} | {:+.5f} | {:+.5f} | {:+.6f} | [{:+.6f}, {:+.6f}] | {:.4f} |'.format(
            model, mode, means['score'], means['accurate'], means['mismatched'],
            node['mean'], node['ci95'][0], node['ci95'][1], p))

    print('\n## S3 验证选择后（tau_S3 由本脚本计算，非冻结端点）\n')
    print('| 模型 | 模式 | S3 Score | S3 Accurate | S3 Mismatched | tau_S3 | tau_S3 CI95 |')
    print('|---|---|---:|---:|---:|---:|---|')
    for key in FROZEN_TAU:
        model, mode = key
        result = results[key]
        means = {arm: result['selected']['S3/' + arm]['metrics']['default']['mean'] for arm in ARMS}
        mean, lo, hi = cluster_bootstrap(s3_seed_values(result))
        print('| {} | {} | {:+.5f} | {:+.5f} | {:+.5f} | {:+.6f} | [{:+.6f}, {:+.6f}] |'.format(
            model, mode, means['score'], means['accurate'], means['mismatched'], mean, lo, hi))

    print('\n## |tau| 的置信上限 vs S3 选择增益\n')
    print('| 模型 | 模式 | |tau| 上限 | S3/score | 上限占选择增益 |')
    print('|---|---|---:|---:|---:|')
    for key in FROZEN_TAU:
        model, mode = key
        node = frozen_raw_contrast(model, mode)
        upper = max(abs(node['ci95'][0]), abs(node['ci95'][1]))
        selection = results[key]['selected']['S3/score']['metrics']['default']['mean']
        print('| {} | {} | {:.4f} | {:+.5f} | {:.0f}% |'.format(
            model, mode, upper, selection, 100 * upper / selection))


if __name__ == '__main__':
    main()
