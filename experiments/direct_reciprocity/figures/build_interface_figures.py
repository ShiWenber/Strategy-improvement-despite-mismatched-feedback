"""Render two-condition distributions and sealed selection outcomes."""
from pathlib import Path
from ..records import read_json
import argparse,json,os
ROOT=Path(__file__).resolve().parents[3]
os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'.mplconfig'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from matplotlib.legend_handler import HandlerTuple
from matplotlib.ticker import MaxNLocator
import numpy as np
from .results_plot_style import apply_style,panel_title,panel_legend,BLUE,ORANGE,GREY,DARK,GREEN
from .results_plot_audit import render_audit,WIDTH
apply_style()
MODES=('Thinking OFF','Thinking ON');COLORS=(BLUE,ORANGE)
POP = None
DISP = None

def vector(report,stage,arm):
 row=report['raw'][arm]['metrics']['default/score'] if stage=='Raw' else report['selected']['S3/'+arm]['metrics']['default']
 return np.asarray(row['seed_values'])

def generation_figure(populations,display,args):
 fig=plt.figure(figsize=(WIDTH,5.60));grid=fig.add_gridspec(2,2,left=.115,right=.985,bottom=.13,top=.92,height_ratios=(1.2,1),hspace=.67,wspace=.44)
 ax=fig.add_subplot(grid[0,0])
 for i,mode in enumerate(MODES):
  bars=display['histograms'][mode]
  ax.bar([b['left'] for b in bars],[b['height'] for b in bars],width=[b['right']-b['left'] for b in bars],align='edge',color=COLORS[i],alpha=.12,edgecolor=COLORS[i],linewidth=.35,zorder=1)
  curve=np.asarray(display['density_curves'][mode]);ax.plot(curve[:,0],curve[:,1],color=COLORS[i],lw=1.6,ls=('-', '-.')[i],zorder=3)
 ax.axvline(0,ls=':',color=GREY,lw=.8);ax.set(xlim=(-.25,.5),ylim=(0,display['ymax']*1.35),xlabel='Raw payoff gain per round',ylabel='Density');ax.set_xticks([-.2,0,.2,.4]);ax.yaxis.set_major_locator(MaxNLocator(4));ax.grid(axis='y',alpha=.16);panel_title(ax,'a','Before selection')
 handles=[(Patch(facecolor=COLORS[i],alpha=.15),Line2D([],[],color=COLORS[i],ls=('-', '-.')[i],lw=1.5)) for i in range(2)]
 panel_legend(ax,handles,['OFF','ON'],ncol=2,handler_map={tuple:HandlerTuple(ndivide=None,pad=.12)})
 ax=fig.add_subplot(grid[0,1]);jitter=np.linspace(-.045,.045,20)
 for i,mode in enumerate(MODES):
  row=populations[mode];raw=np.asarray(row['raw_seed_means']);selected=np.asarray(row['s3_seed_means']);left,right=3*i,3*i+1
  for a,b,j in zip(raw,selected,jitter):ax.plot([left+j,right+j],[a,b],color=COLORS[i],alpha=.27,lw=.8,zorder=1)
  for xx,vals,stage,meanfield in [(left,raw,'Raw','mean_raw'),(right,selected,'S3','mean_s3')]:
   ax.scatter(xx+jitter,vals,s=17,facecolors='white' if stage=='Raw' else COLORS[i],edgecolors=COLORS[i],marker='o' if stage=='Raw' else 's',linewidth=.65,alpha=.9,zorder=2)
   ax.plot([xx-.18,xx+.18],[row[meanfield]]*2,color=DARK,lw=2,zorder=3)
 ax.axhline(0,color=GREY,ls=':',lw=.8);ax.set_xticks([0,1,3,4],['Raw\nOFF','S3\nOFF','Raw\nON','S3\nON']);ax.set(xlim=(-.48,4.48),ylim=(-.065,.25),ylabel='Population mean payoff gain');ax.grid(axis='y',alpha=.16);ax.yaxis.set_major_locator(MaxNLocator(5));panel_title(ax,'b','Same candidate pools')
 panel_legend(ax,[Line2D([],[],marker='o',mfc='white',mec=DARK,ls='none'),Line2D([],[],marker='s',color=DARK,ls='none'),Line2D([],[],color=GREY,alpha=.5,lw=.9),Line2D([],[],color=DARK,lw=2)],['Raw','S3','Population pair','Mean'],ncol=2)
 ax=fig.add_subplot(grid[1,:]);ax.set_position([.21,.13,.755,.265]);states=[('Retained','s3_retained_parent','#C8C8C8',''),('Selected: H > 0','s3_accepted_test_better',GREEN,''),('Selected: H < 0','s3_accepted_test_worse',ORANGE,'///')]
 for i,mode in enumerate(MODES):
  offset=0;row=populations[mode];assert row['s3_accepted_test_equal']==0
  for name,key,color,hatch in states:
   n=row[key];ax.barh(i,n,left=offset,color=color,edgecolor='white',linewidth=.8,height=.48,hatch=hatch);ax.text(offset+n/2,i,str(n),ha='center',va='center',fontsize=8.5,color='white' if key=='s3_accepted_test_better' else DARK,bbox={'facecolor':color,'edgecolor':'none','pad':.25});offset+=n
  assert offset==120
 ax.set_yticks([0,1],MODES);ax.set(xlim=(0,120),ylim=(1.67,-.95),xlabel='Fixed candidate pools (120 per mode)');ax.set_xticks([0,30,60,90,120]);ax.tick_params(axis='y',length=0,pad=8);ax.spines['left'].set_visible(False);panel_title(ax,'c','S3 decisions and independent H outcomes')
 panel_legend(ax,[Patch(facecolor=c,hatch=h,edgecolor='white') for _,_,c,h in states],[s[0] for s in states],ncol=3)
 labels=[t.get_text() for ax in fig.axes for t in ax.get_legend().get_texts()]
 record=render_audit(fig,'figS2',[args.input,args.display_output],__file__,labels,['OFF/ON compound keys each show the histogram fill and the density curve.','Histogram heights and Gaussian KDE curves are read from the existing display cache.','Existing across-population means are read from mean_raw and mean_s3.'],output_dir=args.output_dir,audit_dir=args.audit_dir);plt.close(fig);return record

def main():
 from scipy.stats import gaussian_kde
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--input',type=Path,required=True)
 parser.add_argument('--display-output',type=Path,required=True)
 parser.add_argument('--output-dir',type=Path,required=True)
 parser.add_argument('--audit-dir',type=Path,required=True)
 parser.add_argument('--reuse-display',action='store_true',help='Use frozen histogram and KDE coordinates without fitting or rewriting the display cache.')
 args=parser.parse_args()
 cache=read_json(args.input);pop={m:cache['configurations'][k] for m,k in zip(MODES,('Off / 6k','On / 384k'))}
 if args.reuse_display:
  record=generation_figure(pop,read_json(args.display_output),args)
  print(json.dumps({'figure':record['figure'],'bounds':record['out_of_canvas_text'],'minimum_font_pt':record['minimum_font_pt']}))
  return
 display={'histograms':{},'density_curves':{},'method':'Gaussian KDE with Scott bandwidth; 30 equal-width bins over shared candidate range; two report conditions only'}
 all_values=np.concatenate([row['all_raw_gains'] for row in pop.values()])
 edges=np.linspace(min(-.25,all_values.min()),max(.5,all_values.max()),31)
 x=np.linspace(edges[0],edges[-1],401)
 for mode,row in pop.items():
  values=np.asarray(row['all_raw_gains']);assert len(values)==240
  height,_=np.histogram(values,bins=edges,density=True)
  display['histograms'][mode]=[{'left':float(a),'right':float(b),'height':float(h)} for a,b,h in zip(edges[:-1],edges[1:],height)]
  display['density_curves'][mode]=np.column_stack([x,gaussian_kde(values)(x)]).tolist()
 display['ymax']=float(max(max(b['height'] for b in bars) for bars in display['histograms'].values())*1.1)
 args.display_output.parent.mkdir(parents=True,exist_ok=True);args.display_output.write_text(json.dumps(display,indent=2)+'\n',encoding='utf-8')
 records=[generation_figure(pop,display,args)]
 print(json.dumps([{'figure':r['figure'],'bounds':r['out_of_canvas_text'],'minimum_font_pt':r['minimum_font_pt']} for r in records]))
if __name__=='__main__':main()
