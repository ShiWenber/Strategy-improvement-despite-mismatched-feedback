"""Draw report-distance display from sealed records only; no analyses."""
from pathlib import Path
import argparse,json,os
ROOT=Path(__file__).resolve().parents[2]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--inputs',nargs=2,type=Path,default=[ROOT/f'docs/direct_reciprocity/mismatch_distance/mismatch_distance_thinking_{m}.json' for m in ('off','on')])
parser.add_argument('--output-dir',type=Path,default=ROOT/'reproduct')
parser.add_argument('--audit-dir',type=Path,default=ROOT/'results/reproduction')
args=parser.parse_args()
SOURCES=args.inputs
os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'.mplconfig'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np
from results_plot_style import apply_style,panel_title,panel_legend,BLUE,GREY
from results_plot_audit import render_audit,WIDTH
apply_style();off,on=[json.loads(p.read_text(encoding='utf-8')) for p in SOURCES]
assert len(off['rows'])==60 and [r['delta_full'] for r in off['rows']]==[r['delta_full'] for r in on['rows']]
# Sorting only determines the visual ECDF path; descriptive summaries are sealed.
x=np.sort([r['delta_full'] for r in off['rows']]);y=np.arange(1,len(x)+1)/len(x)
stat=off['distance_summary']['delta_full'];ref=off['distance_diagnostics']['null_within_population_ordered_pairs']
fig,axs=plt.subplots(1,2,figsize=(WIDTH,3.60));fig.subplots_adjust(left=.10,right=.97,bottom=.20,top=.90,wspace=.76)
axs[0].step(x,y,where='post',color=BLUE,lw=1.4);axs[0].axvline(ref['q10'],ls=':',color=GREY,lw=1.1)
axs[0].set(xlim=(0,22),ylim=(0,1.30),ylabel='Cumulative fraction');axs[0].set_yticks([0,.25,.5,.75,1]);axs[0].set_xticks([0,5,10,15,20]);panel_title(axs[0],'a',f'Shared {len(x)} parent–donor pairs')
for yy,low,high,mean,color,marker in [(1,stat['min'],stat['max'],stat['mean'],BLUE,'o'),(0,ref['q10'],ref['q90'],ref['mean'],GREY,'s')]:
 axs[1].plot([low,high],[yy,yy],color=color,lw=1.25)
 axs[1].plot([low,low],[yy-.045,yy+.045],color=color,lw=1.1);axs[1].plot([high,high],[yy-.045,yy+.045],color=color,lw=1.1)
 axs[1].scatter([mean],[yy],color=color,marker=marker,s=32,zorder=3)
axs[1].set(yticks=[0,1],yticklabels=['Within-population\nreference','Parent–donor'],xlim=(0,22),ylim=(-.6,2.1));axs[1].set_xticks([0,5,10,15,20]);axs[1].tick_params(axis='y',length=0,pad=5);panel_title(axs[1],'b','Descriptive reference')
for ax in axs: ax.set_xlabel('Standardized report distance')
panel_legend(axs[0],[Line2D([],[],color=BLUE,lw=1.4),Line2D([],[],color=GREY,ls=':',lw=1.1)],['Parent–donor ECDF','Reference 10th percentile'],ncol=1)
panel_legend(axs[1],[Line2D([],[],marker='o',color=BLUE,ls='none'),Line2D([],[],marker='s',color=GREY,ls='none')],['Parent–donor mean','Reference mean'],ncol=1)
labels=[t.get_text() for ax in axs for t in ax.get_legend().get_texts()]
r=render_audit(fig,'figS6',SOURCES,__file__,labels,['Reference P10 is the 10th percentile of 2640 ordered distinct within-population pairs.','Parent–donor range is the frozen full minimum–maximum range. Reference P10–P90 is a frozen percentile range. Neither range is a confidence interval.','No distance calculation, reference construction, association, bootstrap, or threshold analysis was run.'],output_dir=args.output_dir,audit_dir=args.audit_dir);plt.close(fig)
print(json.dumps({'figure':r['figure'],'bounds':r['out_of_canvas_text'],'minimum_font_pt':r['minimum_font_pt']}))
