"""Shared presentation conventions for the manuscript Results figure set.

Rendering only: English text, letter-only panel headings, and independent
legends inside lettered panels. Interval definitions belong in captions.
"""
from matplotlib.lines import Line2D
from matplotlib.legend_handler import HandlerBase
import matplotlib.pyplot as plt

BLUE = '#0072B2'
ORANGE = '#D55E00'
DARK = '#303030'
GREY = '#737373'
GREEN = '#009E73'
PURPLE = '#CC79A7'
FONT = 'DejaVu Sans'
LEGEND_TOP = .988
PANEL_FONT = 9.5
LEGEND_FONT = 8.5

class IntervalKey:
    """A horizontal whisker with end caps, used to explain stored intervals."""
    def __init__(self, color=GREY): self.color=color

class IntervalHandler(HandlerBase):
    def create_artists(self, legend, orig_handle, xdescent, ydescent, width, height, fontsize, trans):
        left, right = -xdescent, width-xdescent
        mid = height/2-ydescent
        cap = height*.25
        return [Line2D([left,right],[mid,mid],color=orig_handle.color,lw=1,transform=trans),
                Line2D([left,left],[mid-cap,mid+cap],color=orig_handle.color,lw=1,transform=trans),
                Line2D([right,right],[mid-cap,mid+cap],color=orig_handle.color,lw=1,transform=trans)]

def apply_style():
    plt.rcParams.update({'font.family':FONT,'font.size':9,
        'axes.labelsize':9,'axes.titlesize':PANEL_FONT,
        'xtick.labelsize':8.5,'ytick.labelsize':8.5,'legend.fontsize':LEGEND_FONT,
        'axes.spines.top':False,'axes.spines.right':False,'axes.linewidth':.6,
        'xtick.major.width':.6,'ytick.major.width':.6,
        'pdf.fonttype':42,'ps.fonttype':42,'svg.fonttype':'none',
        'savefig.dpi':300})

def panel_title(ax, letter, title='', pad=8, **kwargs):
    assert not title, 'Move descriptive panel titles into the caption.'
    return ax.set_title(f'({letter})',loc='left',fontweight='bold',
                        fontsize=PANEL_FONT,pad=pad,**kwargs)

def panel_heading(fig, letter, title, x, y, **kwargs):
    assert not title, 'Move descriptive panel titles into the caption.'
    text = f'({letter})'
    return fig.text(x,y,text,ha='left',va='bottom',
                    fontsize=PANEL_FONT,fontweight='bold',**kwargs)

def top_legend(fig, handles, labels, ncol=3, handler_map=None, **kwargs):
    mapping={IntervalKey:IntervalHandler()}
    if handler_map: mapping.update(handler_map)
    return fig.legend(handles,labels,loc='upper center',bbox_to_anchor=(.5,LEGEND_TOP),
        bbox_transform=fig.transFigure,ncol=ncol,frameon=False,fontsize=LEGEND_FONT,
        borderaxespad=0,handlelength=1.65,handletextpad=.5,columnspacing=1.25,
        labelspacing=.45,handler_map=mapping,**kwargs)

def panel_legend(ax, handles, labels, ncol=2, handler_map=None):
    assert not any('95%' in label or isinstance(handle, IntervalKey)
                   for handle, label in zip(handles, labels)), 'Explain intervals in the caption.'
    mapping={}
    if handler_map: mapping.update(handler_map)
    return ax.legend(handles, labels, loc='upper center', ncol=ncol,
        frameon=True, facecolor='white', edgecolor='none', framealpha=1,
        fontsize=LEGEND_FONT, borderaxespad=.35,
        handlelength=1.4, handletextpad=.4, columnspacing=.85, labelspacing=.3,
        handler_map=mapping)
