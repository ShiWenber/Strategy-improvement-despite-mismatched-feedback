"""Population-level estimates, full tables and standalone scientific plots."""
from __future__ import annotations

import base64
import argparse
import csv
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from .collective_welfare import ROOT, ARMS, read, write
from .core import seed_for


def estimate(values, name='default'):
    x=np.asarray(values,float)
    assert x.shape==(20,)
    rng=np.random.default_rng(seed_for('welfare-bootstrap',name))
    samples=x[rng.integers(0,20,size=(20000,20))].mean(axis=1)
    return {'mean':float(x.mean()),'ci95':np.quantile(samples,[.025,.975]).tolist(),
            'positive_populations':int((x>1e-12).sum()),'negative_populations':int((x< -1e-12).sum()),
            'values':x.tolist()}


def sign_flip_p(values):
    x=np.asarray(values,float);target=abs(x.sum());extreme=0
    for start in range(0,1<<20,4096):
        nums=np.arange(start,min(start+4096,1<<20),dtype=np.uint32)
        signs=2*((nums[:,None]>>np.arange(20))&1).astype(float)-1
        extreme+=np.count_nonzero(np.abs(signs@x)>=target-1e-12)
    return extreme/(1<<20)


def export_csv(path, rows):
    keys=list(dict.fromkeys(k for r in rows for k in r))
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=keys);writer.writeheader();writer.writerows(rows)


def summarize(root):
    deploy=read(root/'deployment.json');jobs=read(root/'dynamics_jobs.json')['jobs']
    assert deploy['complete'] and len(deploy['baselines'])==20 and len(jobs)==200
    drows=[];paths={};drift={}
    for job in jobs:
        z=np.load(root/'dynamics'/(job['name']+'.npz'))
        paths[job['name']]=z['timeline'].mean(axis=1)
        for b,beta in enumerate(z['beta']):
            vals=z['tail'][b].mean(axis=0);previous=z['prior_tail'][b].mean(axis=0)
            drows.append({**job,'beta':int(beta),'welfare':float(vals[0]),'cooperation':float(vals[1]),
                'mutual_cooperation':float(vals[2]),'diversity':float(vals[3]),'candidate_label_share':float(vals[4]),
                'low_state_fraction':float(z['low_tail'][b].mean()),
                'copied_payoff_gap':float(z['copied_payoff_gap'][b].mean()),
                'tail_welfare_change':float(vals[0]-previous[0]),'tail_cooperation_change':float(vals[1]-previous[1]),
                'mc_se_cooperation':float(z['tail'][b,:,1].std(ddof=1)/np.sqrt(30))})
    def vector(rows, metric, **filters):
        return np.array([np.mean([r[metric] for r in rows if r['seed']==seed
                            and all(r[k]==v for k,v in filters.items())]) for seed in range(200,220)])
    results={'deployment':{},'dynamics':{},'primary_tests':[],'baselines':{},
             'units':'20 independent source populations; average arms and simulation replicates within population'}
    for metric in ['welfare','cooperation','mutual_cooperation']:
        results['baselines'][metric]=estimate([r[metric] for r in deploy['baselines']],metric)
    dmetrics=['welfare','cooperation','delta_welfare','delta_cooperation','private_gain','opponent_gain','changed_slots','low_state']
    for mode in ['OFF','ON']:
        for policy in ['R','S1','S2','S3']:
            tag=f'{mode}_{policy}';results['deployment'][tag]={m:estimate(vector(deploy['rows'],m,mode=mode,policy=policy),tag+m) for m in dmetrics}
            cells=[r for r in deploy['rows'] if r['mode']==mode and r['policy']==policy]
            results['deployment'][tag]['joint_harm_cells']=sum(r['joint_harm'] for r in cells)
            results['deployment'][tag]['cells']=len(cells)
        for beta in [0,1,5]:
            tag=f'{mode}_beta{beta}'
            results['dynamics'][tag]={m:estimate(vector(drows,m,mode=mode,beta=beta),tag+m)
                for m in ['welfare','cooperation','mutual_cooperation','diversity','candidate_label_share','low_state_fraction','copied_payoff_gap','tail_welfare_change','tail_cooperation_change']}
            for m in ['welfare','cooperation']:
                v=vector(drows,m,mode=mode,beta=beta)-vector(drows,m,mode=mode,beta=0)
                results['dynamics'][tag]['difference_'+m]=estimate(v,tag+'diff'+m)
        for phase,rows,filters,metric in [('deployment',deploy['rows'],{'mode':mode,'policy':'S2'},'delta_welfare'),
                                        ('deployment',deploy['rows'],{'mode':mode,'policy':'S2'},'delta_cooperation'),
                                        ('dynamics',drows,{'mode':mode,'beta':1},'welfare'),
                                        ('dynamics',drows,{'mode':mode,'beta':1},'cooperation')]:
            x=vector(rows,metric,**filters)
            if phase=='dynamics':x-=vector(drows,metric,mode=mode,beta=0)
            results['primary_tests'].append({'phase':phase,'mode':mode,'metric':metric,
                                            **estimate(x,phase+mode+metric),'p_raw':sign_flip_p(x)})
    ordering=sorted(range(8),key=lambda i:results['primary_tests'][i]['p_raw']);running=0
    for pos,i in enumerate(ordering):
        running=max(running,min(1,results['primary_tests'][i]['p_raw']*(8-pos)))
        results['primary_tests'][i]['p_holm']=running
    results['by_arm']={'deployment':{},'dynamics':{}}
    for mode in ['OFF','ON']:
        for arm in ARMS:
            for policy in ['R','S1','S2','S3']:
                tag=f'{mode}_{arm}_{policy}'
                results['by_arm']['deployment'][tag]={m:estimate(vector(deploy['rows'],m,mode=mode,arm=arm,policy=policy),tag+m)
                    for m in ['welfare','cooperation','delta_welfare','delta_cooperation','private_gain','opponent_gain']}
            for beta in [0,1,5]:
                tag=f'{mode}_{arm}_beta{beta}'
                results['by_arm']['dynamics'][tag]={m:estimate(vector(drows,m,mode=mode,arm=arm,beta=beta),tag+m)
                    for m in ['welfare','cooperation','low_state_fraction']}
    write(root/'SUMMARY.json',results)
    export_csv(root/'deployment_by_population.csv',deploy['rows'])
    export_csv(root/'dynamics_by_population.csv',drows)
    export_csv(root/'primary_tests.csv',[{k:v for k,v in r.items() if k not in ['values','ci95']} for r in results['primary_tests']])
    make_plots(root,results,paths,jobs)
    return results


def make_plots(root,s,paths,jobs):
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False,
                         'svg.fonttype':'none','pdf.fonttype':42,'axes.labelsize':10,'legend.frameon':False})
    out=root/'figures';out.mkdir(exist_ok=True)
    palette={'OFF':'#246a9b','ON':'#cb6a2e'}
    fig,axes=plt.subplots(2,2,figsize=(10,8),layout='constrained')
    for col,mode in enumerate(['OFF','ON']):
        ax=axes[0,col];policies=['Original','Random','S2','S3']
        values=[np.array(s['baselines']['cooperation']['values'])]+[
            np.array(s['deployment'][f'{mode}_{p}']['cooperation']['values']) for p in ['R','S2','S3']]
        for j in range(20):ax.plot(range(4),[v[j]*100 for v in values],color=palette[mode],alpha=.16,lw=.8)
        ax.plot(range(4),[v.mean()*100 for v in values],color=palette[mode],marker='o',lw=2.6,label='Mean of 20 populations')
        ax.set(xticks=range(4),xticklabels=policies,ylabel='Population cooperation (%)',title=f'({chr(97+col)}) Thinking {mode}: one-step deployment')
        ax.set_ylim(0,102);ax.legend(loc='lower left',fontsize=8)
        ax=axes[1,col];r=s['deployment'][f'{mode}_S2'];x=np.array(r['private_gain']['values']);y=np.array(r['delta_welfare']['values'])
        ax.scatter(x,y,c=palette[mode],s=40,alpha=.85,edgecolors='white',lw=.5)
        ax.axhline(0,color='#777',lw=.8);ax.axvline(0,color='#777',lw=.8)
        ax.scatter([x.mean()],[y.mean()],c='black',marker='D',s=65,label='Population mean',zorder=3)
        ax.set(xlabel='Individual payoff gain against original peers',ylabel='Change in population mean payoff',
               title=f'({chr(99+col)}) S2: private gain and collective outcome')
        ax.legend(loc='upper right',fontsize=8)
    fig.savefig(out/'deployment.png',dpi=300);fig.savefig(out/'deployment.svg');plt.close(fig)
    fig,axes=plt.subplots(2,2,figsize=(10,7.5),layout='constrained')
    colors=['#66717d','#d38126','#983f55'];labels=['Neutral imitation (beta = 0)','Payoff-biased (beta = 1)','Stronger selection (beta = 5)']
    times=np.arange(0,2001,10)
    for col,mode in enumerate(['OFF','ON']):
        population_paths=np.stack([np.mean([paths[j['name']] for j in jobs if j['seed']==seed and j['mode']==mode],axis=0) for seed in range(200,220)])
        for row,metric in enumerate([1,0]):
            ax=axes[row,col];scale=100 if metric==1 else 1
            for b in range(3):
                values=population_paths[:,b,:,metric]*scale
                rng=np.random.default_rng(270927)
                sample=values[rng.integers(0,20,(2000,20))].mean(axis=1)
                lo,hi=np.quantile(sample,[.025,.975],axis=0)
                ax.fill_between(times,lo,hi,color=colors[b],alpha=.1,lw=0)
                ax.plot(times,values.mean(axis=0),color=colors[b],lw=2,label=labels[b])
            ax.set(title=f'({chr(97+row*2+col)}) Thinking {mode}',xlabel='Imitation generation',
                   ylabel='Population cooperation (%)' if metric==1 else 'Population mean payoff per round',xlim=(0,2000))
            ax.set_ylim((0,102) if metric==1 else (1,3.05))
            if row==0:ax.legend(fontsize=8,loc='lower left')
    fig.savefig(out/'cultural_selection.png',dpi=300);fig.savefig(out/'cultural_selection.svg');plt.close(fig)
    imgs={name:base64.b64encode((out/(name+'.png')).read_bytes()).decode() for name in ['deployment','cultural_selection']}
    html='''<!doctype html><meta charset="utf-8"><title>直接互惠：个体收益与群体福利</title><style>body{font:17px/1.7 system-ui,sans-serif;max-width:1200px;margin:36px auto;padding:0 24px;color:#243344}h1{font-size:28px}figure{margin:30px 0}img{width:100%;border:1px solid #dce2e9}figcaption{color:#526475}a{color:#246a9b}</style><h1>直接互惠：个体收益与群体福利</h1><p>探索性补充实验；使用本地固定程序，无新增模型生成。合作率与群体平均收益分别测量，统计推断单位为 20 个原始种群。</p>'''
    html+='<p><strong>主要发现：局部的个人获益可以伴随群体受损，但收益偏向模仿没有使当前策略库整体陷入低福利；在本次固定库模拟中，它提高了平均合作率和群体收益。</strong></p>'
    html+='<table style="border-collapse:collapse;width:100%"><tr><th>生成模式</th><th>中性模仿合作率</th><th>收益偏向模仿合作率</th><th>群体每轮平均收益</th></tr>'
    for mode,label in [('OFF','未开启思考'),('ON','开启思考')]:
        a=s['dynamics'][mode+'_beta0'];b=s['dynamics'][mode+'_beta1']
        html+=f'<tr style="text-align:center;border-top:1px solid #ddd"><td>{label}</td><td>{a["cooperation"]["mean"]:.1%}</td><td>{b["cooperation"]["mean"]:.1%}</td><td>{a["welfare"]["mean"]:.3f} → {b["welfare"]["mean"]:.3f}</td></tr>'
    html+='</table><p>上表为最后 100 代的平均表现，两列模仿规则使用相同初始组成。少数轨迹仍进入低状态；这不证明低合作不可能发生，也不是让 LLM 连续 2000 代生成新策略。</p>'
    for name,caption in [('deployment','图 1：三个父代槽位的同步部署。上排比较原群体、随机采用及既有 S2/S3 选择后的合作率；连线表示同一种群的配对，不是连续处理阶段。下排比较 S2 下个人对原对手的收益改善与群体平均收益变化。每个点为一个原种群内五种信息条件的平均，黑色菱形为 20 个种群的平均。个人与群体指标使用的对手环境不同。'),('cultural_selection','图 2：固定策略库中的文化选择。每条线先平均模拟重复和五个报告条件，再平均 20 个种群；带状区域为种群 bootstrap 95% 区间。180 个个体，2000 代，同步模仿，0.25% 本地策略重抽。纵轴使用全范围，以显示群体是否整体进入低合作、低福利；曲线不是新生成代码的逐代成绩。')]:
        html+=f'<figure><img src="data:image/png;base64,{imgs[name]}"><figcaption>{caption}</figcaption></figure>'
    html+='<p>完整结果见同目录 RESULT.md、SUMMARY.json 及逐种群 CSV。</p>'
    (root/'preview.html').write_text(html,encoding='utf-8')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,default=ROOT)
    result=summarize(parser.parse_args().root)
    print('Summary and figures complete. Primary effects:')
    for r in result['primary_tests']:
        print(r['phase'],r['mode'],r['metric'],round(r['mean'],6),'Holm p',round(r['p_holm'],6))
