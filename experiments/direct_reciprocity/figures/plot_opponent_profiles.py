"""Pure render of frozen opponent-family summaries; no table writes."""
from pathlib import Path
import argparse,json,os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from matplotlib.lines import Line2D
import numpy as np
from .results_plot_style import apply_style,panel_title,panel_legend,BLUE,ORANGE,GREY
from .results_plot_audit import render_audit,WIDTH


def main():
    W=Path(__file__).resolve().parents[3]
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,default=W/'results/figure4_opponent_profiles_20260926/ANALYSIS.json')
    parser.add_argument('--output-dir',type=Path,default=W/'reproduct')
    parser.add_argument('--audit-dir',type=Path,default=W/'results/reproduction')
    args=parser.parse_args()
    INPUT=args.input
    os.environ.setdefault('MPLCONFIGDIR',str(W/'.mplconfig'))
    apply_style();D=json.loads(INPUT.read_text(encoding='utf-8'))
    apply_style();D=json.loads(INPUT.read_text(encoding='utf-8'))
    fig,axs=plt.subplots(2,2,figsize=(WIDTH,5.50),sharex=True,sharey=True)
    fig.subplots_adjust(left=.19,right=.975,bottom=.12,top=.93,wspace=.26,hspace=.80)
    colors={'accurate':BLUE,'mismatched':ORANGE};families=D['families'];labels=['Recovery','Exploitation','Random','Memory-one']
    colors={'accurate':BLUE,'mismatched':ORANGE};families=D['families'];labels=['Recovery','Exploitation','Random','Memory-one']
    colors={'accurate':BLUE,'mismatched':ORANGE};families=D['families'];labels=['Recovery','Exploitation','Random','Memory-one']
    for row,stage in enumerate(['raw','S3']):
     for col,mode in enumerate(['non_thinking','thinking']):
      ax=axs[row,col];ax.axvspan(-.175,0,color='#F4F5F6',zorder=0);ax.axvline(0,color=GREY,lw=.8,zorder=2)
      for k in range(4):
       if k%2==0:ax.axhspan(k-.45,k+.45,color='#F5F7F9',alpha=.45,zorder=0)
      for arm,off in [('accurate',-.17),('mismatched',.17)]:
       rows=[D['configs'][mode]['summaries'][stage][arm][f] for f in families];means=np.array([r['mean'] for r in rows]);ci=np.array([r['ci95_exploratory_unadjusted'] for r in rows])
       ax.barh(np.arange(4)+off,means,height=.28,color=colors[arm],alpha=.8,edgecolor='white',lw=.35,hatch='///' if arm=='mismatched' else None,zorder=3)
       ax.errorbar(means,np.arange(4)+off,xerr=np.vstack([means-ci[:,0],ci[:,1]-means]),fmt='none',ecolor=colors[arm],elinewidth=.85,capsize=2,capthick=.8,zorder=4)
      ax.set_yticks(range(4),labels);ax.set(ylim=(3.55,-1.2),xlim=(-.175,.23));ax.set_xticks([-.1,0,.1,.2],['−0.1','0','+0.1','+0.2']);ax.tick_params(axis='y',length=0,pad=8);ax.tick_params(axis='x',length=3,labelbottom=True)
      panel_title(ax,'abcd'[row*2+col],('Raw' if stage=='raw' else 'S3')+': '+('Thinking OFF' if mode=='non_thinking' else 'Thinking ON'))
      ax.set_xlabel('Payoff gain per round\nvs parent')
      panel_legend(ax,[Patch(facecolor=BLUE,alpha=.8),Patch(facecolor=ORANGE,alpha=.8,hatch='///',edgecolor='white')],['Accurate','Mismatched'],ncol=2)
    legendlabels=['Accurate','Mismatched']
    r=render_audit(fig,'figS4',[INPUT],__file__,legendlabels,['Existing arm-specific unadjusted 95% population-bootstrap intervals reused; paired contrasts are unchanged in supplementary tables.','Original bar and hatch encoding retained. Alternating row shading only assists alignment.'],output_dir=args.output_dir,audit_dir=args.audit_dir);plt.close(fig)
    r=render_audit(fig,'figS4',[INPUT],__file__,legendlabels,['Existing arm-specific unadjusted 95% population-bootstrap intervals reused; paired contrasts are unchanged in supplementary tables.','Original bar and hatch encoding retained. Alternating row shading only assists alignment.'],output_dir=args.output_dir,audit_dir=args.audit_dir);plt.close(fig)
    print(json.dumps({'figure':r['figure'],'bounds':r['out_of_canvas_text'],'minimum_font_pt':r['minimum_font_pt']}))


if __name__ == '__main__':
    main()
