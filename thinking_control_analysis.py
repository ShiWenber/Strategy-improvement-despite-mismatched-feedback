"""Analyze only a complete, audited thinking follow-up against frozen historical outputs."""
import argparse
from collections import Counter
from pathlib import Path
from statistics import mean
import json

import numpy as np

from experiments.direct_reciprocity.core import Policy, digest
from experiments.direct_reciprocity.run import read_json, write_json
from experiments.direct_reciprocity.specificity import seal_selections
from experiments.direct_reciprocity.specificity_analysis import contrast, summarize, holm, behavior_delta
from experiments.direct_reciprocity.thinking_control import DEFAULT_ROOT, SOURCE, verify, specification, filehash


def audit(root, m):
    root = Path(root)
    issues, records = [], []
    release = read_json(root/'H_RELEASED.json')
    read_json(root/'COMPLETE.json')
    selected = seal_selections(root, m)
    if len(selected['rows']) != 900:
        issues.append('Expected 900 sealed selections')
    if release['selection_digest'] != digest((root/'SELECTIONS_SEALED.json').read_text(encoding='utf-8')):
        issues.append('Selection seal mismatch')
    for j in m['jobs']:
        identity = j['id']
        r = read_json(root/'requests_candidates'/(identity+'.json'))
        c = read_json(root/'contexts'/(j['context']+'.json'))
        child = read_json(root/'candidates'/(identity+'.json'))
        row = read_json(root/'holdout'/(identity+'.json'))
        parent = read_json(root/'holdout'/(j['context']+'.json'))
        expected = specification(c['prompts'][j['arm']])
        if any(r.get(k) != v for k,v in expected.items()):
            issues.append(identity+': request parameters differ')
        if r.get('fingerprint') != digest(json.dumps(expected, sort_keys=True)):
            issues.append(identity+': request fingerprint differs')
        if digest(r['prompt']) != m['prompt_hashes'][identity]:
            issues.append(identity+': historical prompt differs')
        if r['started_at'] < m['frozen_at']:
            issues.append(identity+': generation before protocol freeze')
        if not r.get('reasoning_content'):
            issues.append(identity+': no native reasoning evidence')
        if r.get('returned_model') != m['api']['model']:
            issues.append(identity+': unexpected model')
        if child['valid'] != (r['status']=='valid'):
            issues.append(identity+': validity mismatch')
        if child['child']:
            if Policy(**child['child']).key != r.get('code_hash'):
                issues.append(identity+': code hash differs')
            code = r['content']
            if code.strip().startswith('```') and code.strip().splitlines()[-1].strip()=='```':
                code = '\n'.join(code.strip().splitlines()[1:-1])
            if child['child']['code'] != code:
                issues.append(identity+': code differs from returned content')
        if filehash(root/'holdout'/(j['context']+'.json')) != filehash(SOURCE/'holdout'/(j['context']+'.json')):
            issues.append(identity+': reused parent differs')
        if selected['candidate_hashes'][identity] != digest((root/'candidates'/(identity+'.json')).read_text(encoding='utf-8')):
            issues.append(identity+': candidate changed after selection')
        for setting in ('default','noise01','long'):
            for metric in ('score','cooperation','worst_score'):
                d = row['deployed'][setting][metric]-parent['measured'][setting][metric]
                if abs(d-row['delta'][setting][metric]) > 1e-10:
                    issues.append(identity+': delta arithmetic')
                if row['fallback'][setting] and abs(d)>1e-10:
                    issues.append(identity+': invalid fallback')
        records.append(r)
    def tokens(key):
        return sum((r.get('usage') or {}).get(key,0) or 0 for r in records)
    reasoning_tokens = [(r.get('usage') or {}).get('completion_tokens_details',{}).get('reasoning_tokens')
                        if (r.get('usage') or {}).get('completion_tokens_details') else None for r in records]
    archived = [read_json(p) for p in (root/'attempt_history').glob('*/requests_candidates/*.json')]
    return {'issues':issues, 'requests':len(records),
            'archived_attempts':len(archived),
            'archived_attempts_usage_missing':sum(r.get('usage') is None for r in archived),
            'archived_attempts_reported_total_tokens':sum((r.get('usage') or {}).get('total_tokens',0) or 0 for r in archived),
            'statuses':dict(Counter(r['status'] for r in records)),
            'returned_models':dict(Counter(r.get('returned_model') for r in records)),
            'finish_reasons':dict(Counter(r.get('finish_reason') for r in records)),
            'usage_missing':sum(r.get('usage') is None for r in records),
            'prompt_tokens':tokens('prompt_tokens'),'completion_tokens':tokens('completion_tokens'),
            'total_tokens':tokens('total_tokens'),
            'reasoning_tokens_reported':sum(v for v in reasoning_tokens if v is not None),
            'reasoning_token_usage_missing':sum(v is None for v in reasoning_tokens),
            'reasoning_chars':sum(len(r['reasoning_content']) for r in records),
            'note':'Reasoning character counts are not tokens. This is a record and arithmetic audit, not an independent game implementation.'}


def aggregate(root, m):
    root = Path(root)
    rows = [read_json(root/'holdout'/(j['id']+'.json')) for j in m['jobs']]
    by_id = {r['id']:r for r in rows}
    parents = {cid:read_json(root/'holdout'/(cid+'.json')) for cid in {j['context'] for j in m['jobs']}}
    for row in rows:
        row['behavior_delta'] = behavior_delta(row, parents[row['context']])
    selected = read_json(root/'SELECTIONS_SEALED.json')['rows']
    result = {'raw':{},'selected':{}}
    for arm in m['arms']:
        rr = [r for r in rows if r['arm']==arm]
        metrics = {}
        for setting in ('default','noise01','long'):
            for metric in ('score','cooperation','worst_score'):
                values = [mean(r['delta'][setting][metric] for r in rr if r['seed']==s) for s in m['seeds']]
                metrics[setting+'/'+metric] = summarize(values)
        behavior = {metric:summarize([mean(r['behavior_delta'][metric] for r in rr if r['seed']==s) for s in m['seeds']])
                    for metric in rr[0]['behavior_delta']}
        result['raw'][arm] = {'n':len(rr),'valid':sum(r['valid'] for r in rr),'metrics':metrics,'behavior':behavior,
                             'fallbacks':{s:sum(r['fallback'][s] for r in rr) for s in ('default','noise01','long','behavior')}}
        for rule in ('S1','S2','S3'):
            choices = [r for r in selected if r['arm']==arm and r['rule']==rule]
            sm = {setting:summarize([mean(by_id[r['winner']]['delta'][setting]['score'] if r['winner'] else 0.
                                         for r in choices if r['seed']==s) for s in m['seeds']])
                  for setting in ('default','noise01','long')}
            result['selected'][rule+'/'+arm] = {'n':len(choices),'accepted':sum(r['accepted'] for r in choices), 'metrics':sm}
    return result


def paired_focus(new, old):
    def vector(obj, arm):
        return np.asarray(obj['raw'][arm]['metrics']['default/score']['seed_values'])
    a = vector(new,'accurate')-vector(new,'mismatched')
    b = vector(old,'accurate')-vector(old,'mismatched')
    out = {'thinking_accurate_minus_mismatched':contrast(a),
           'diagnostic_advantage_change_vs_historical':contrast(a-b)}
    adjusted = holm({key:v['sign_swap_p'] for key,v in out.items()})
    for key,v in out.items():
        v['holm_p'] = adjusted[key]
        v['positive_seeds'] = sum(x>0 for x in v['seed_values'])
        v['negative_seeds'] = sum(x<0 for x in v['seed_values'])
    return out


def analyze(root):
    root = Path(root)
    m = verify(root)
    aud = audit(root,m)
    write_json(root/'AUDIT.json',aud)
    if aud['issues']: raise RuntimeError('Audit failed; do not interpret results')
    new, old = aggregate(root,m), aggregate(SOURCE,m)
    old_saved = read_json(SOURCE/'ANALYSIS.json')
    for arm in m['arms']:
        for setting in ('default','noise01','long'):
            x = old['raw'][arm]['metrics'][setting+'/score']['seed_values']
            y = old_saved['raw'][arm]['metrics'][setting+'/score']['seed_values']
            if not np.allclose(x,y,atol=1e-12,rtol=0):
                raise RuntimeError('Historical reconstruction mismatch')
    focus = paired_focus(new,old)
    exploratory = {}
    for arm in m['arms']:
        for setting in ('default','noise01','long'):
            x = new['raw'][arm]['metrics'][setting+'/score']['seed_values']
            y = old['raw'][arm]['metrics'][setting+'/score']['seed_values']
            exploratory['raw/'+arm+'/'+setting] = contrast(np.asarray(x)-np.asarray(y))
            for rule in ('S1','S2','S3'):
                x = new['selected'][rule+'/'+arm]['metrics'][setting]['seed_values']
                y = old['selected'][rule+'/'+arm]['metrics'][setting]['seed_values']
                exploratory[rule+'/'+arm+'/'+setting] = contrast(np.asarray(x)-np.asarray(y))
    limitation = ('历史配对配置比较：同时改变原生 thinking、输出预算及有效采样规则，非同期随机化，'
                  '服务端别名无法保证权重固定；H 是已使用过的测试面板。不能单独归因于思考开关，未显著不等于等效。')
    result = {'audit':aud, 'thinking':new, 'historical':old, 'focus_holm_two':focus,
              'configuration_differences_exploratory':exploratory, 'limitations':limitation,
              'analysis_source_hash':filehash(__file__)}
    write_json(root/'ANALYSIS.json',result)
    lines = ['# 原生思考模式 384K：历史配对补充实验','',
             f"完成 {aud['requests']} 次新候选调用，有效 {aud['statuses'].get('valid',0)} 个；记录审计问题 {len(aud['issues'])}。",
             '','同一 60 个父代、五种反馈、每组两个候选。thinking=enabled，reasoning_effort=high，max_tokens=384000。','',
             '| 反馈组 | 旧配置原始增量 | 思考原始增量 | 旧配置 S3 增量 | 思考 S3 增量 | 思考有效候选 |',
             '| --- | ---: | ---: | ---: | ---: | ---: |']
    for arm in m['arms']:
        vals = [old['raw'][arm]['metrics']['default/score']['mean'],new['raw'][arm]['metrics']['default/score']['mean'],
                old['selected']['S3/'+arm]['metrics']['default']['mean'],new['selected']['S3/'+arm]['metrics']['default']['mean']]
        lines.append('| '+arm+' | '+' | '.join(f'{v:+.5f}' for v in vals)+f" | {new['raw'][arm]['valid']}/120 |")
    lines += ['','重点比较（两个检验作 Holm 校正；完整区间见 ANALYSIS.json）：','']
    for key,v in focus.items():
        lines.append(f"- {key}：每轮差值 {v['mean']:+.5f}；{v['positive_seeds']}/20 种群为正，{v['negative_seeds']}/20 为负；调整后 p={v['holm_p']:.5f}。")
    lines += ['',limitation,'',f"最终候选请求报告 token {aud['total_tokens']:,}，输出 token {aud['completion_tokens']:,}；其中包含思考。384K 是上限，不能当作实际用量。",
              f"另有归档请求尝试 {aud['archived_attempts']} 条，其中 {aud['archived_attempts_usage_missing']} 条缺少用量；归档尝试已报告 token {aud['archived_attempts_reported_total_tokens']:,}。上述已报告用量不代表包含中断请求的完整账单。",
              '', '该报告列出效应与审计事实；是否形成新的论文主张需结合行为结果和上述适用范围解释。','']
    (root/'REPORT.md').write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps({'audit_issues':aud['issues'],'focus':focus},ensure_ascii=False))
    return result


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root',nargs='?',default=str(DEFAULT_ROOT))
    analyze(parser.parse_args().root)
