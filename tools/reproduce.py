"""Offline reproduction from archived responses; never makes model API calls."""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys
import time

WORK = Path(__file__).resolve().parents[1]
HERE = WORK / 'reproduct'
CHECKS = WORK / 'results/reproduction'
RUNS = {'DeepSeek/OFF': 'results/feedback_specificity_v2',
        'DeepSeek/ON': 'results/feedback_specificity_thinking_384k_20260923',
        'Qwen/OFF': 'results/qwen3_8/off', 'Qwen/ON': 'results/qwen3_8/on'}
ARMS = ['accurate', 'mismatched']
REPORT = {'scope': 'Frozen-response statistical reproduction and sampled game replay',
          'live_api_calls': 0, 'steps': [], 'comparisons': []}


def read(p):
    p = Path(p)
    output = p.with_name(p.stem + '_reproduct' + p.suffix)
    return json.loads((output if output.exists() else p).read_text(encoding='utf-8-sig'))


def write(p, value):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    temporary = p.with_name(p.name + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    os.replace(temporary, p)


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def frozen(rel):
    return json.loads((WORK / rel).read_text(encoding='utf-8-sig'))


def run(name, args, timeout=1800):
    log = CHECKS / (name + '_reproduct.log')
    log.parent.mkdir(exist_ok=True)
    env = os.environ.copy()
    env.update(PYTHONPATH=str(WORK), PYTHONIOENCODING='utf-8',
               MPLBACKEND='Agg', MPLCONFIGDIR=str(WORK / '.mplconfig'))
    args = (['--module', args[1], '--', *args[2:]] if args[0] == '-m'
            else ['--script', str(args[0]), '--', *args[1:]])
    args = ['tools/reproduce_worker.py', *args]
    start = time.monotonic()
    print('RUN ' + name, flush=True)
    with log.open('w', encoding='utf-8') as out:
        result = subprocess.run([sys.executable, *args], cwd=WORK, env=env,
                                stdout=out, stderr=subprocess.STDOUT, timeout=timeout)
    step = {'name': name, 'command': [sys.executable, *args], 'exit_code': result.returncode,
            'seconds': round(time.monotonic() - start, 3), 'log': log.relative_to(WORK).as_posix()}
    REPORT['steps'].append(step)
    write(CHECKS / 'verification_reproduct.json', REPORT)
    if result.returncode:
        raise RuntimeError(f'{name} failed; inspect {log}')
    print('PASS ' + name, flush=True)


def prepare():
    manifest = frozen('results/reproduction/INPUT_MANIFEST.json')
    for record in manifest['records']:
        assert sha(WORK / record['path']) == record['sha256'], record['path']
    REPORT['input_hashes_verified'] = len(manifest['records'])
    print(f"PASS {len(manifest['records'])} canonical input hashes", flush=True)


def compare(label, expected, actual):
    errors, numbers, exact, max_difference = [], 0, True, 0.0

    def visit(a, b, key):
        nonlocal numbers, exact, max_difference
        if isinstance(a, dict):
            if not isinstance(b, dict) or set(a) != set(b):
                errors.append(key + ': keys differ')
                return
            for k in a:
                visit(a[k], b[k], key + '/' + k)
        elif isinstance(a, list):
            if not isinstance(b, list) or len(a) != len(b):
                errors.append(key + ': length differs')
                return
            for i, (x, y) in enumerate(zip(a, b)):
                visit(x, y, key + '/' + str(i))
        elif isinstance(a, (int, float)) and not isinstance(a, bool):
            numbers += 1
            if not isinstance(b, (int, float)):
                errors.append(key + ': type differs')
                return
            delta = abs(a - b)
            max_difference = max(max_difference, delta)
            exact = exact and a == b
            if delta > 1e-12:
                errors.append(key + f': {a} != {b}')
        elif a != b:
            errors.append(key + ': value differs')

    visit(expected, actual, label)
    result = {'label': label, 'numeric_values': numbers, 'exact_numeric_match': exact,
              'max_abs_difference': max_difference, 'tolerance': 1e-12,
              'status': 'passed' if not errors else 'mismatch', 'errors': errors[:30]}
    REPORT['comparisons'].append(result)
    write(CHECKS / 'verification_reproduct.json', REPORT)
    if errors:
        raise RuntimeError(f'{label}: {len(errors)} mismatches')


def statistics():
    run('main_statistics', ['-m', 'experiments.direct_reciprocity.specificity_analysis'])
    rel = RUNS['DeepSeek/OFF'] + '/ANALYSIS.json'
    before, after = frozen(rel), read(WORK / rel)
    compare('main raw/selected/primary', {k: before[k] for k in ['raw', 'selected', 'primary']},
            {k: after[k] for k in ['raw', 'selected', 'primary']})
    run('fixed_pool', ['-m', 'experiments.direct_reciprocity.role_analysis'])
    rel = RUNS['DeepSeek/OFF'] + '/role_analysis/ANALYSIS.json'
    compare('fixed_pool summaries', frozen(rel)['summaries'], read(WORK / rel)['summaries'])
    run('thinking_statistics', ['thinking_control_analysis.py'])
    rel = RUNS['DeepSeek/ON'] + '/ANALYSIS.json'
    before, after = frozen(rel), read(WORK / rel)
    for key in ['thinking', 'historical', 'focus_holm_two', 'configuration_differences_exploratory']:
        compare('thinking ' + key, before[key], after[key])
    compare('thinking request accounting', before['audit'], after['audit'])
    run('qwen_statistics', ['results/qwen3_8/analyze.py'])
    for mode in ['off', 'on']:
        rel = 'results/qwen3_8/' + mode + '/ANALYSIS.json'
        compare('qwen ' + mode, frozen(rel)['result'], read(WORK / rel)['result'])
    run('population_statistics', ['tools/analyze_population.py'])
    rel = 'results/reciprocity_population_visuals_20260924/population_summary.json'
    compare('population distributions and selection counts', frozen(rel)['configurations'], read(WORK / rel)['configurations'])
    run('opponent_statistics', ['tools/figures/analyze_opponent_profiles.py'])
    rel = 'results/figure4_opponent_profiles_20260926/ANALYSIS.json'
    before, after = frozen(rel), read(WORK / rel)
    for config in ['non_thinking', 'thinking']:
        compare('opponent ' + config, before['configs'][config]['summaries'], after['configs'][config]['summaries'])
    run('behavior_statistics', ['tools/figures/plot_behavior_evidence.py'])
    rel = 'results/reciprocity_population_visuals_20260924/behavior/ANALYSIS.json'
    before, after = frozen(rel), read(WORK / rel)
    for config in ['non_thinking', 'thinking']:
        compare('behavior ' + config, before['configs'][config]['summaries'], after['configs'][config]['summaries'])
    run('distance_statistics', ['-m', 'experiments.direct_reciprocity.mismatch_distance', '--root', '.'])
    for mode in ['off', 'on']:
        rel = 'docs/direct_reciprocity/mismatch_distance/mismatch_distance_thinking_' + mode + '.json'
        before, after = frozen(rel), read(WORK / rel)
        # Compare measurements and inference independently of path metadata.
        for key in ['rows', 'distance_summary', 'distance_diagnostics', 'weak_mismatch_sensitivity']:
            compare('distance ' + mode + ' ' + key, before[key], after[key])
    run('cross_model_checks', ['results/model_comparison_20260928/cross_model_summary.py'])
    rel = 'results/model_comparison_20260928/cross_model_mainline_data.json'
    compare('cross-model mainline summaries', frozen(rel)['statistics'], read(WORK / rel)['statistics'])
    export_data()


def csv_write(name, rows):
    path = HERE / name
    if not rows:
        return
    with path.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def export_data():
    candidates, populations, summaries = [], [], []
    for config, rel in RUNS.items():
        root = WORK / rel
        manifest = read(root / 'manifest.json')
        report = read(root / 'ANALYSIS.json')
        stats = report if config == 'DeepSeek/OFF' else report['thinking' if config == 'DeepSeek/ON' else 'result']
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
        for arm in ARMS:
            for stage in ['raw', 'S1', 'S2', 'S3']:
                metric = stats['raw'][arm]['metrics']['default/score'] if stage == 'raw' else stats['selected'][stage + '/' + arm]['metrics']['default']
                summaries.append({'configuration': config, 'arm': arm, 'stage': stage,
                                  'mean': metric['mean'], 'ci95_low': metric['ci95'][0], 'ci95_high': metric['ci95'][1]})
                for seed, value in zip(manifest['seeds'], metric['seed_values']):
                    populations.append({'configuration': config, 'seed': seed, 'arm': arm,
                                        'stage': stage, 'gain_per_round': value})
    csv_write('candidate_gains.csv', candidates)
    csv_write('population_gains.csv', populations)
    csv_write('condition_statistics.csv', summaries)
    rows = [read(p) for p in sorted((WORK / 'results/mismatch_detection_jev/judgments').glob('*.json'))]
    from collections import Counter
    summary = {}
    for arm in ARMS:
        pool = [r for r in rows if r['arm'] == arm]
        strict = [r for r in pool if r.get('origin_prob_questions', 0) >= .40 and r.get('origin_confidence', 0) >= .60]
        summary[arm] = {'total': len(pool), 'strict_origin_questions': len(strict),
                        'handling': dict(Counter(r['resolution_choice'] for r in pool)),
                        'strict_handling': dict(Counter(r['resolution_choice'] for r in strict))}
    assert summary['mismatched']['strict_origin_questions'] == 31
    assert summary['accurate']['strict_origin_questions'] == 0
    assert summary['mismatched']['strict_handling'] == {'kept_using': 30, 'discarded': 1}
    assert all(summary[a]['total'] == 120 for a in ARMS)
    write(HERE / 'jev_recount.json', {'threshold': .40, 'confidence_gate': .60, 'by_arm': summary, 'live_api_calls': 0})


def figures():
    scripts = 'tools/figures/'
    run('main_figures', [scripts + 'plot_results_three_figures.py'])
    run('full_selectors_and_policy', [scripts + 'plot_camera_ready.py', '--figures', '3', '4', '5'])
    run('full_distributions', [scripts + 'build_interface_figures.py'])
    run('full_opponent_figure', [scripts + 'plot_opponent_profiles.py'])
    run('report_distance_figure', [scripts + 'plot_mismatch_distance.py'])
    run('compact_paper_tables', [str(WORK / 'tools/export_paper_tables.py'), '--work', str(WORK), '--output', str(CHECKS / 'tables')])
    # Figure 1 is the original method artwork, referenced once in the paper.
    outputs = [{'name': p.name, 'sha256': sha(p)} for p in sorted(HERE.glob('fig*.*'))]
    write(CHECKS / 'FIGURE_MANIFEST_reproduct.json', outputs)


def replay():
    run('sampled_game_replay', [str(WORK / 'tools/replay_worker.py'), '--work', str(WORK), '--output', str(HERE / 'replay.json')])
    result = read(HERE / 'replay.json')
    assert all(r['status'] in ['ok', 'invalid_candidate_no_game_replay'] for r in result['records'])
    REPORT['replay'] = result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', choices=['all', 'prepare', 'statistics', 'figures', 'replay', 'export'], default='all')
    a = parser.parse_args()
    HERE.mkdir(exist_ok=True)
    CHECKS.mkdir(parents=True, exist_ok=True)
    REPORT['started_utc'] = datetime.now(timezone.utc).isoformat()
    REPORT['status'] = 'running'
    REPORT['stage'] = a.stage
    REPORT['python'] = sys.version
    REPORT['packages'] = {p: importlib.metadata.version(p) for p in ['numpy', 'matplotlib', 'scipy', 'openai', 'pandas']}
    write(CHECKS / 'verification_reproduct.json', REPORT)
    try:
        prepare()
        if a.stage in ['all', 'statistics']:
            statistics()
        if a.stage == 'export':
            export_data()
        if a.stage in ['all', 'figures']:
            figures()
        if a.stage in ['all', 'replay']:
            replay()
        prepare()  # Confirm that no original input was overwritten by a stage.
        REPORT['status'] = 'passed'
        REPORT['stage'] = a.stage
    except Exception as exc:
        REPORT.update(status='failed', error=str(exc), stage=a.stage)
        raise
    finally:
        REPORT['finished_utc'] = datetime.now(timezone.utc).isoformat()
        write(CHECKS / 'verification_reproduct.json', REPORT)
    print('PASS ' + a.stage + '; see results/reproduction/verification_reproduct.json', flush=True)


if __name__ == '__main__':
    main()
