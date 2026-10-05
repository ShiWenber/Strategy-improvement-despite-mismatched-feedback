"""Post-hoc exact policy contrasts on sealed candidate pools; no API or game calls."""
import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path

import numpy as np


def policies(gains, scores, parent_score, valid):
    """R=random child; G=random then gate; U=random eligible; B=best eligible."""
    eligible = [i for i in range(2) if valid[i] and scores[i] > parent_score]
    winner = max(eligible, key=lambda i: (scores[i], -i)) if eligible else None
    r = sum(gains) / 2
    g = sum(gains[i] for i in eligible) / 2
    u = sum(gains[i] for i in eligible) / len(eligible) if eligible else 0.0
    b = gains[winner] if winner is not None else 0.0
    return dict(R=r, G=g, U=u, B=b, gate=g-r, opportunity=u-g,
                ranking=b-u, total=b-r, winner=winner, eligible=len(eligible))


def self_test():
    assert policies([.2, -.4], [1, 1], 1, [True, True])['B'] == 0
    assert policies([.2, -.4], [3, 2], 1, [False, True])['winner'] == 1
    p = policies([.2, -.4], [3, 2], 1, [True, True])
    assert p['winner'] == 0 and abs(p['ranking']-.3) < 1e-12
    assert policies([.2, -.4], [2, 2], 1, [True, True])['winner'] == 0
    p = policies([.2, -.4], [2, 0], 1, [True, True])
    assert p['G'] == .1 and p['U'] == .2 and p['ranking'] == 0
    for scores in ([0, 0], [2, 0], [0, 2], [2, 3]):
        p = policies([-.3, .2], scores, 1, [True, True])
        assert abs(p['gate'] + p['opportunity'] + p['ranking'] - p['total']) < 1e-12


def run(root):
    self_test()
    root = Path(root)
    hashes = {}

    def read(name):
        raw = (root/name).read_bytes()
        hashes[name] = hashlib.sha256(raw).hexdigest()
        return json.loads(raw)

    manifest = read('manifest.json')
    frozen = read('ANALYSIS.json')
    sealed = {(r['context'], r['arm'], r['rule']): r for r in read('SELECTIONS_SEALED.json')['rows']}
    jobs = defaultdict(list)
    for j in manifest['jobs']:
        jobs[(j['context'], j['arm'])].append(j)
    records = []
    counts = defaultdict(lambda: dict(candidates=0, better=0, worse=0, equal=0, pools=0,
                                    pools_with_better=0, both_better=0))
    metrics = ('R', 'G', 'U', 'B', 'gate', 'opportunity', 'ranking', 'total')
    for (context, arm), jj in sorted(jobs.items()):
        jj.sort(key=lambda x: x['draw'])
        assert len(jj) == 2
        child = [read(f"holdout/{j['id']}.json") for j in jj]
        cs = [read(f"selection_scores/{j['id']}.json") for j in jj]
        ps = read(f'selection_scores/{context}.json')
        gains = [c['delta']['default']['score'] for c in child]
        count = counts[arm]
        count['candidates'] += 2
        count['pools'] += 1
        better = sum(v > 1e-12 for v in gains)
        count['better'] += better
        count['worse'] += sum(v < -1e-12 for v in gains)
        count['equal'] += sum(abs(v) <= 1e-12 for v in gains)
        count['pools_with_better'] += int(better > 0)
        count['both_better'] += int(better == 2)
        for rule in ('S1', 'S2', 'S3'):
            valid = [c['valid'] and s['metrics'][rule]['status'] == 'ok' for c, s in zip(child, cs)]
            scores = [s['metrics'][rule].get('score', float('-inf')) for s in cs]
            parent_score = ps['metrics'][rule]['score']
            for setting in ('default', 'noise01', 'long'):
                gains = [c['delta'][setting]['score'] for c in child]
                p = policies(gains, scores, parent_score, valid)
                actual = sealed[(context, arm, rule)]['winner']
                expected = None if p['winner'] is None else jj[p['winner']]['id']
                assert actual == expected, (context, arm, rule)
                assert abs(p['gate'] + p['opportunity'] + p['ranking'] - p['total']) < 1e-12
                records.append(dict(context=context, seed=jj[0]['seed'], arm=arm, rule=rule,
                                    setting=setting, **p))
    seeds = sorted(manifest['seeds'])
    rng = np.random.default_rng(20260920)
    indices = rng.integers(0, len(seeds), size=(20000, len(seeds)))

    def summarize(values):
        x = np.asarray(values, dtype=float)
        lo, hi = np.quantile(x[indices].mean(axis=1), [.025, .975])
        return dict(mean=float(x.mean()), ci95=[float(lo), float(hi)], seed_values=x.tolist())

    summaries = {}
    for arm in list(manifest['arms']) + ['pooled']:
        for rule in ('S1', 'S2', 'S3'):
            for setting in ('default', 'noise01', 'long'):
                rows = [r for r in records if (arm == 'pooled' or r['arm'] == arm)
                        and r['rule'] == rule and r['setting'] == setting]
                result = {metric: summarize([np.mean([r[metric] for r in rows if r['seed'] == seed])
                                             for seed in seeds]) for metric in metrics}
                if arm != 'pooled':
                    assert np.allclose(result['R']['seed_values'], frozen['raw'][arm]['metrics'][setting+'/score']['seed_values'], atol=1e-12, rtol=0)
                    assert np.allclose(result['B']['seed_values'], frozen['selected'][rule+'/'+arm]['metrics'][setting]['seed_values'], atol=1e-12, rtol=0)
                result['eligible_pool_counts'] = {str(n): sum(r['eligible'] == n for r in rows) for n in range(3)}
                result['accepted_test_degrades'] = sum(r['winner'] is not None and r['B'] < -1e-12 for r in rows)
                summaries[f'{arm}/{rule}/{setting}'] = result
    out = root/'role_analysis'
    out.mkdir(exist_ok=True)
    plan = Path('docs/direct_reciprocity/ROLE_ANALYSIS_PLAN.md')
    result = dict(status='complete', design='post_hoc_fixed_pool_exact_expectations',
                  note='Exploratory unadjusted population-bootstrap intervals. No new model requests or games.',
                  bootstrap_seed=20260920, bootstrap_replicates=20000, independent_clusters=20,
                  counts=dict(counts), summaries=summaries, rows=records, input_sha256=hashes,
                  plan_sha256=hashlib.sha256(plan.read_bytes()).hexdigest(),
                  verification=dict(policy_edge_cases='passed', sealed_decisions_reconstructed=len(sealed),
                                    frozen_raw_and_selected_seed_values='passed', decomposition_identity='passed'))
    (out/'ANALYSIS.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    lines = ['# 固定池角色分析（事后探索）', '', result['note'], '',
             'R=随机候选；G=随机候选后评价门控；U=合格候选中随机；B=合格候选中按分数最优。', '',
             '| 组别/规则 | R | G | U | B | B−R | G−R | U−G | B−U |',
             '| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    for key, row in summaries.items():
        if key.endswith('/default'):
            lines.append('| ' + key.removesuffix('/default') + ' | ' + ' | '.join(f"{row[m]['mean']:+.6f}" for m in ('R', 'G', 'U', 'B', 'total', 'gate', 'opportunity', 'ranking')) + ' |')
    lines += ['', '## 配对差分精度（未校正 95% 种群 bootstrap）', '',
              '| 组别/规则/设置 | B−R | G−R | U−G | B−U |', '| --- | --- | --- | --- | --- |']
    for key, row in summaries.items():
        lines.append('| ' + key + ' | ' + ' | '.join(f"{row[m]['mean']:+.6f} [{row[m]['ci95'][0]:+.6f}, {row[m]['ci95'][1]:+.6f}]" for m in ('total', 'gate', 'opportunity', 'ranking')) + ' |')
    lines += ['', '## 候选与候选池', '', '| 组别 | 改善 | 退化 | 持平 | 至少一个改善/60 | 两个改善/60 |', '| --- | ---: | ---: | ---: | ---: | ---: |']
    for arm, c in counts.items():
        lines.append(f"| {arm} | {c['better']} | {c['worse']} | {c['equal']} | {c['pools_with_better']} | {c['both_better']} |")
    lines += ['', '该分解依赖指定路径，不能把其比例解释为模型与评价器的一般因果贡献。全部区间为事后探索性结果。', '']
    (out/'REPORT.md').write_text('\n'.join(lines), encoding='utf-8')
    return out


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', nargs='?', default='results/feedback_specificity_v2')
    print(run(parser.parse_args().root))
