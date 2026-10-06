"""Recompute four model/configuration mainline summaries and verify paired tests."""
from __future__ import annotations

import argparse
import csv
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


def read(relative, analysis_suffix=''):
    path = ROOT / relative
    path = path.with_name(path.stem + analysis_suffix + path.suffix)
    return json.loads(path.read_text(encoding='utf-8'))


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


def frozen_raw_contrast(model, mode, analysis_suffix=""):
    """Frozen mean, interval, seed values, and sign-swap p for the raw contrast."""
    relative, keys = FROZEN_TAU[(model, mode)]
    return dig(read(relative, analysis_suffix), keys)


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


def export_csv(directory, analysis_suffix="", output_suffix=""):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    candidates, populations, summaries = [], [], []
    for (model, mode), relative in RESULT_FILES.items():
        config = model + '/' + mode.upper()
        rel = Path(relative).parent
        root = ROOT / rel
        manifest = read(root / 'manifest.json')
        report = read(root / 'ANALYSIS.json', analysis_suffix)
        stats = result_block(model, mode, report)
        selections = read(root / 'SELECTIONS_SEALED.json')
        winners = {(r['context'], r['arm'], r['rule']): r['winner'] for r in selections['rows']}
        for job in manifest['jobs']:
            row = read(root / 'holdout' / (job['id'] + '.json'))
            for setting in ['default', 'noise01', 'long']:
                candidates.append({'configuration': config, 'id': job['id'], 'seed': job['seed'],
                                   'context': job['context'], 'arm': job['arm'], 'draw': job['draw'],
                                   'valid': row['valid'], 'setting': setting,
                                   'fallback': row['fallback'][setting], 'gain_per_round': row['delta'][setting]['score'],
                                   'S3_selected': winners[job['context'], job['arm'], 'S3'] == job['id']})
        for arm in ('accurate', 'mismatched'):
            for stage in ['raw', 'S1', 'S2', 'S3']:
                metric = stats['raw'][arm]['metrics']['default/score'] if stage == 'raw' else stats['selected'][stage + '/' + arm]['metrics']['default']
                summaries.append({'configuration': config, 'arm': arm, 'stage': stage,
                                  'mean': metric['mean'], 'ci95_low': metric['ci95'][0], 'ci95_high': metric['ci95'][1]})
                for seed, value in zip(manifest['seeds'], metric['seed_values']):
                    populations.append({'configuration': config, 'seed': seed, 'arm': arm,
                                        'stage': stage, 'gain_per_round': value})
    for stem, rows in [('candidate_gains', candidates), ('population_gains', populations), ('condition_statistics', summaries)]:
        with (directory / (stem + output_suffix + '.csv')).open('w', newline='', encoding='utf-8') as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)


def main():
    global ROOT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, default=ROOT)
    parser.add_argument('--analysis-suffix', default='')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--csv-dir', type=Path, help='Also export candidate, population and condition CSVs.')
    parser.add_argument('--output-suffix', default='', help='Suffix for exported CSV filenames.')
    args = parser.parse_args()
    ROOT = args.work.resolve()
    statistics, sources = {}, {}
    for (model, mode), relative in RESULT_FILES.items():
        result = result_block(model, mode, read(relative, args.analysis_suffix))
        contrast = frozen_raw_contrast(model, mode, args.analysis_suffix)
        values = raw_seed_values(result)
        assert np.allclose(values, contrast['seed_values'], atol=1e-12, rtol=0)
        assert abs(sign_swap(values) - contrast['sign_swap_p']) < 1e-12
        key = model + '/' + mode.upper()
        statistics[key] = {
            'raw_mismatched': result['raw']['mismatched']['metrics']['default/score'],
            's3_mismatched': result['selected']['S3/mismatched']['metrics']['default'],
            'raw_accurate_minus_mismatched': {k: contrast[k] for k in ['n_seeds', 'seed_values', 'mean', 'ci95', 'sign_swap_p']}}
        sources[key] = str(Path(relative).with_name(Path(relative).stem + args.analysis_suffix + '.json')).replace('\\', '/')
    report = {'sources': sources, 'statistics': statistics,
              'unit': '20 shared independent populations; 3 parents per population',
              'interval': 'Unadjusted population bootstrap intervals',
              'note': 'Two report conditions only. S3 uses V; H was previously used in follow-ups.'}
    destination = args.output or ROOT / 'results/model_comparison_20260928/cross_model_mainline_data.json'
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    if args.csv_dir:
        export_csv(args.csv_dir, args.analysis_suffix, args.output_suffix)
    print('Recomputed four model/configuration mainline summaries')


if __name__ == '__main__':
    main()
