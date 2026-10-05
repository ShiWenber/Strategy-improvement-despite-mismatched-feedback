"""Audit partial/full matrices and summarize paired-seed effects without pseudo-replication."""
import argparse
from collections import defaultdict
from pathlib import Path
import random
from statistics import mean, stdev
from .run import read_json, write_json


def interval(values, repetitions=10000):
    if len(values)<2:
        return None
    rng=random.Random(20260916)
    samples=sorted(mean(rng.choices(values,k=len(values))) for _ in range(repetitions))
    return [samples[int(.025*repetitions)],samples[int(.975*repetitions)]]


def summarize(root):
    root=Path(root)
    plan=read_json(root/'matrix_plan.json')
    rows=[]
    endpoints=[]
    for cell in plan['cells']:
        name=f"{cell['prompt']}__{cell['selection']}__seed{cell['seed']}"
        directory=root/name
        states=[]
        for path in sorted(directory.glob('generation_*.json')):
            state=read_json(path)
            if state['status']=='complete':
                states.append(state)
        expected=list(range(plan['generations']))
        complete=[s['generation'] for s in states]==expected and (directory/'complete.json').exists()
        rows.append({**cell,'complete':complete,'generations':len(states),
                     'failure':read_json(directory/'failure.json') if (directory/'failure.json').exists() else None})
        if not complete:
            continue
        config=read_json(directory/'config.json')
        if config['implementation_hash'] != plan['implementation_hash']:
            raise ValueError('Mixed implementation hashes')
        state=states[-1]
        metrics={'train_fitness_per_round':max(x['fitness'] for x in state['assessment'])/plan['rounds'],
                 'code_diversity':state['code_diversity'],
                 'behavior_diversity':state['behavior_diagnostics']['distinct_valid_profiles'],
                 'behavior_errors':len(state['behavior_diagnostics']['profile_errors']),
                 'requests':state['budget_at_evaluation']['requests'],
                 'tokens':state['budget_at_evaluation']['total_tokens']}
        for label,result in state['holdout'].items():
            rounds=state['test_configs'][label]['rounds']
            metrics[label+'_runtime_failure']=result.get('status')=='runtime_failure'
            metrics[label+'_score']=result['score']/rounds if result['score'] is not None else None
            metrics[label+'_cooperation']=result['cooperation']
            metrics[label+'_worst_score']=result['worst_score']/rounds if result['worst_score'] is not None else None
        endpoints.append({**cell,**metrics})
    groups=defaultdict(list)
    for row in endpoints:
        groups[row['prompt'],row['selection']].append(row)
    summaries=[]
    for (prompt,selection),records in sorted(groups.items()):
        successful=[r for r in records if r['default_score'] is not None]
        values=[r['default_score'] for r in successful]
        summaries.append({'prompt':prompt,'selection':selection,'n':len(records),
                          'n_successful':len(successful), 'runtime_failures':len(records)-len(successful),
                          'score_mean':mean(values) if values else None,'score_sd':stdev(values) if len(values)>1 else None,
                          'score_bootstrap95':interval(values),
                          'cooperation_mean':mean(r['default_cooperation'] for r in successful) if successful else None,
                          'request_mean':mean(r['requests'] for r in records),
                          'token_mean':mean(r['tokens'] for r in records)})
    contrasts=[]
    for selection in ('paper_truncation',):
        reference={r['seed']:r for r in groups['minimal',selection]}
        for prompt in ('score','full'):
            other={r['seed']:r for r in groups[prompt,selection]}
            seeds=sorted(s for s in set(reference)&set(other) if reference[s]['default_score'] is not None and other[s]['default_score'] is not None)
            if seeds:
                differences=[other[s]['default_score']-reference[s]['default_score'] for s in seeds]
                contrasts.append({'contrast':prompt+' minus minimal','selection':selection,'seeds':seeds,
                                  'differences':differences,'mean':mean(differences),'bootstrap95':interval(differences)})
    output={'all_main_cells_complete':all(r['complete'] for r in rows),'cells':rows,
            'endpoints':endpoints,'group_summaries':summaries,'paired_contrasts':contrasts,
            'missingness_note':'Runtime failures are null, not zero. Score summaries and paired contrasts use successful tests only and may have survivorship bias; report failure counts alongside scores.',
            'note':'Exploratory 5-seed estimates. Equal-generation comparisons are not equal-token or equal-call effects. Independent-sampling control is reported separately.'}
    write_json(root/'analysis.json',output)
    lines=['# 直接互惠主实验进度与结果','',f"完整条件：{sum(r['complete'] for r in rows)}/{len(rows)}。",'',
           '统计单位为独立生成种子；对局轮数不作为独立样本。五种子区间仅用于探索，未作多重检验校正。',
           '训练分数与独立测试分数分开；等代数比较含实际调用量差异，不等于等预算因果效应。','',
           '| 提示 | 选择 | 完整/测试成功/失败 | 测试每轮收益 | 合作率 | 平均请求数 | 平均tokens |',
           '| --- | --- | ---: | ---: | ---: | ---: | ---: |']
    def number(value):
        return 'NA' if value is None else f'{value:.4f}'
    for r in summaries:
        lines.append(f"| {r['prompt']} | {r['selection']} | {r['n']}/{r['n_successful']}/{r['runtime_failures']} | {number(r['score_mean'])} | {number(r['cooperation_mean'])} | {r['request_mean']:.1f} | {r['token_mean']:.0f} |")
    lines+=['','测试执行失败记为缺失；收益及配对差值只使用成功测试，存在幸存者偏差，必须同时报告失败数量。','','完整逐种子指标、未完成条件和配对差值见 analysis.json。独立采样对照未完成前，不将主矩阵完成等同整个研究计划完成。']
    (root/'REPORT.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    return output


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('root',type=Path)
    args=parser.parse_args()
    result=summarize(args.root)
    print(f"Complete: {sum(r['complete'] for r in result['cells'])}/{len(result['cells'])}")


if __name__=='__main__':
    main()
