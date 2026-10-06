"""Render figures and audit fonts, bounds and source hashes; no analysis."""
from pathlib import Path
from hashlib import sha256
import json
from matplotlib.text import Text
ROOT=Path(__file__).resolve().parents[2]
AUDIT=ROOT/'results/reproduction'
WIDTH=175/25.4

def render_audit(fig,stem,inputs,script,legend_labels,notes=None):
    fig.canvas.draw(); renderer=fig.canvas.get_renderer(); outside=[]; fonts=[]
    non_drawn=set()
    for ax in fig.axes:
        for axis in (ax.xaxis,ax.yaxis):
            lo,hi=sorted(axis.get_view_interval())
            for tick in (*axis.get_major_ticks(),*axis.get_minor_ticks()):
                if not lo-1e-10<=tick.get_loc()<=hi+1e-10: non_drawn.update((tick.label1,tick.label2))
    for artist in fig.findobj(Text):
        if artist in non_drawn or not artist.get_visible() or not artist.get_text().strip(): continue
        fonts.append(artist.get_fontsize()); b=artist.get_window_extent(renderer)
        if b.x0<-.5 or b.y0<-.5 or b.x1>fig.bbox.x1+.5 or b.y1>fig.bbox.y1+.5: outside.append(artist.get_text())
    assert not outside,(stem,outside)
    assert min(fonts)>=8.5,(stem,min(fonts))
    legends=[]
    for l in fig.legends:
        b=l.get_window_extent(renderer); legends.append({'bbox_canvas_fraction':[b.x0/fig.bbox.width,b.y0/fig.bbox.height,b.x1/fig.bbox.width,b.y1/fig.bbox.height],'labels':[t.get_text() for t in l.get_texts()]})
    assert len(legends)==1 and not any(ax.get_legend() for ax in fig.axes)
    titles=[ax.get_title(loc='left') for ax in fig.axes]
    assert all(t.startswith('(') for t in titles)
    source=ROOT/'reproduct'
    source.mkdir(parents=True,exist_ok=True); AUDIT.mkdir(parents=True,exist_ok=True)
    outputs={}
    for ext in ('pdf','svg','png'):
        p=source/f'{stem}.{ext}'; fig.savefig(p,dpi=600,facecolor='white')
        digest=sha256(p.read_bytes()).hexdigest()
        outputs[ext]={'sha256':digest,'path':p.relative_to(ROOT).as_posix()}
    record={'figure':stem,'scope':'Frozen-data rendering only','new_model_calls':0,'new_games':0,'new_bootstrap':0,'new_fits':0,'new_tests':0,'width_mm':175,'figure_inches':[fig.get_figwidth(),fig.get_figheight()],'minimum_font_pt':min(fonts),'maximum_font_pt':max(fonts),'panel_font_pt':9.5,'legend_font_pt':8.5,'out_of_canvas_text':outside,'legend_position':'figure-level top center; anchor (0.5, 0.988)','legend_labels':legend_labels,'legends':legends,'panel_titles':titles,'inputs_sha256':{str(Path(p).resolve().relative_to(ROOT)).replace('\\','/'):sha256(Path(p).read_bytes()).hexdigest() for p in [*inputs,Path(__file__),Path(__file__).with_name('results_plot_style.py')]},'script_sha256':sha256(Path(script).read_bytes()).hexdigest(),'outputs':outputs,'notes':notes or [],'visual_qa':'pending'}
    (AUDIT/f'{stem}_audit_reproduct.json').write_text(json.dumps(record,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    return record
