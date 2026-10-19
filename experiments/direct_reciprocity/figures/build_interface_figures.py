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
import numpy as np
from .results_plot_style import apply_style,panel_title,panel_legend,BLUE,ORANGE,GREY,DARK,GREEN
from .results_plot_style import save_figure, WIDTH
from .plot_data import fit_axis, data_limits, finite_values
apply_style()
MODES=('Thinking OFF','Thinking ON');COLORS=(BLUE,ORANGE)
def generation_figure(populations,display,output_dir):
 fig=plt.figure(figsize=(WIDTH,4.35));grid=fig.add_gridspec(2,1,left=.13,right=.965,bottom=.14,top=.91,height_ratios=(1.2,1),hspace=.67)
 ax=fig.add_subplot(grid[0,0])
 for i,mode in enumerate(MODES):
  bars=display['histograms'][mode]
  ax.bar([b['left'] for b in bars],[b['height'] for b in bars],width=[b['right']-b['left'] for b in bars],align='edge',color=COLORS[i],alpha=.12,edgecolor=COLORS[i],linewidth=.35,zorder=1)
  curve=np.asarray(display['density_curves'][mode])
  if curve.size: ax.plot(curve[:,0],curve[:,1],color=COLORS[i],lw=1.6,ls=('-', '-.')[i],zorder=3)
 xvalues=[value for mode in MODES for bar in display['histograms'][mode] for value in (bar['left'],bar['right'])]
 heights=[bar['height'] for mode in MODES for bar in display['histograms'][mode]]
 heights += [point[1] for mode in MODES for point in display['density_curves'][mode]]
 fit_axis(ax,xvalues,include_zero=True,padding=0.)
 fit_axis(ax,heights,axis='y',nonnegative=True,headroom=.32)
 ax.axvline(0,ls=':',color=GREY,lw=.8);ax.set(xlabel='Raw payoff gain per round',ylabel='Density');ax.grid(axis='y',alpha=.16);panel_title(ax,'a','Before selection')
 handles=[(Patch(facecolor=COLORS[i],alpha=.15),Line2D([],[],color=COLORS[i],ls=('-', '-.')[i],lw=1.5)) if display['density_curves'][mode] else Patch(facecolor=COLORS[i],alpha=.15) for i,mode in enumerate(MODES)]
 panel_legend(ax,handles,['OFF','ON'],ncol=2,handler_map={tuple:HandlerTuple(ndivide=None,pad=.12)})
 ax=fig.add_subplot(grid[1,0]);states=[('Retained','s3_retained_parent','#C8C8C8',''),('Selected: H > 0','s3_accepted_test_better',GREEN,''),('Selected: H < 0','s3_accepted_test_worse',ORANGE,'///'),('Selected: H = 0','s3_accepted_test_equal',BLUE,'')]
 states=[state for state in states if any(populations[mode][state[1]] for mode in MODES)]
 totals=[]
 for i,mode in enumerate(MODES):
  offset=0;row=populations[mode]
  for name,key,color,hatch in states:
   n=row[key]
   if n < 0: raise ValueError('Negative candidate-pool count')
   ax.barh(i,n,left=offset,color=color,edgecolor='white',linewidth=.8,height=.48,hatch=hatch)
   if n: ax.text(offset+n/2,i,str(n),ha='center',va='center',fontsize=8.5,color='white' if key=='s3_accepted_test_better' else DARK,bbox={'facecolor':color,'edgecolor':'none','pad':.25})
   offset+=n
  if offset != row['s3_accepted']+row['s3_retained_parent']: raise ValueError('S3 outcome counts do not cover all pools')
  totals.append(offset)
 fit_axis(ax,totals,nonnegative=True,padding=0.,integer=True)
 ax.set_yticks(range(len(MODES)),MODES);ax.set(ylim=(len(MODES)-.33,-.95),xlabel='Fixed candidate pools');ax.tick_params(axis='y',length=0,pad=8);ax.spines['left'].set_visible(False);panel_title(ax,'b','S3 decisions and independent H outcomes')
 panel_legend(ax,[Patch(facecolor=c,hatch=h,edgecolor='white') for _,_,c,h in states],[s[0] for s in states],ncol=len(states))
 record=save_figure(fig,'figS2',output_dir);plt.close(fig);return record

def build_display(populations, bins=30):
 from scipy.stats import gaussian_kde
 if bins < 1: raise ValueError('Histogram bin count must be positive')
 display={'histograms':{},'density_curves':{},'sample_sizes':{},'method':f'Gaussian KDE with Scott bandwidth where identifiable; {bins} equal-width bins over the shared candidate range. Constant samples use histogram only.'}
 values_by_mode={mode:finite_values(row['all_raw_gains']) for mode,row in populations.items()}
 low,high=data_limits(np.concatenate(list(values_by_mode.values())),include_zero=True,padding=.05)
 edges=np.linspace(low,high,bins+1);x=np.linspace(low,high,401)
 for mode,values in values_by_mode.items():
  if len(values)!=populations[mode]['n']: raise ValueError('Candidate count differs from recorded gains')
  height,_=np.histogram(values,bins=edges,density=True)
  display['histograms'][mode]=[{'left':float(a),'right':float(b),'height':float(h)} for a,b,h in zip(edges[:-1],edges[1:],height)]
  display['density_curves'][mode]=np.column_stack([x,gaussian_kde(values)(x)]).tolist() if len(values)>1 and np.ptp(values)>0 else []
  display['sample_sizes'][mode]=len(values)
 return display


def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--input',type=Path,required=True)
 parser.add_argument('--display-output',type=Path,required=True)
 parser.add_argument('--output-dir',type=Path,required=True)
 parser.add_argument('--bins',type=int,default=30)
 parser.add_argument('--reuse-display',action='store_true',help='Use frozen histogram and KDE coordinates without fitting or rewriting the display cache.')
 args=parser.parse_args()
 cache=read_json(args.input);pop={}
 for label,row in cache['configurations'].items():
  mode=row.get('mode',label.split('/')[0].replace('Thinking','').strip().lower())
  if mode in ('off','on'): pop['Thinking '+mode.upper()]=row
 if set(pop)!=set(MODES): raise ValueError('Expected separate Thinking OFF and ON configurations')
 if args.reuse_display:
  record=generation_figure(pop,read_json(args.display_output),args.output_dir)
  print(json.dumps(record))
  return
 display=build_display(pop,args.bins)
 args.display_output.parent.mkdir(parents=True,exist_ok=True);args.display_output.write_text(json.dumps(display,indent=2)+'\n',encoding='utf-8')
 records=[generation_figure(pop,display,args.output_dir)]
 print(json.dumps(records))
if __name__=='__main__':main()
