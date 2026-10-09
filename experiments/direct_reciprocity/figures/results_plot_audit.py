"""Render figures and audit fonts and bounds; no analysis."""
from pathlib import Path
import json,re
from matplotlib.text import Text
from matplotlib.lines import Line2D
from matplotlib.transforms import Bbox
ROOT=Path(__file__).resolve().parents[3]
AUDIT=ROOT/'results/reproduction'
WIDTH=175/25.4

def path_label(path):
    resolved=Path(path).resolve()
    return resolved.relative_to(ROOT).as_posix() if resolved.is_relative_to(ROOT) else resolved.as_posix()

def validate_panel_layout(fig,stem):
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
    assert not fig.legends, (stem,'Use a separate legend inside each lettered panel.')
    legends=[]
    for ax in fig.axes:
        legend=ax.get_legend()
        assert legend is not None,(stem,ax.get_title(loc='left'),'Missing panel legend')
        b=legend.get_window_extent(renderer); owner=ax.get_window_extent(renderer)
        assert owner.contains(b.x0,b.y0) and owner.contains(b.x1,b.y1),(stem,'Legend outside its panel')
        labels=[t.get_text() for t in legend.get_texts()]
        assert not any('95%' in label or 'confidence interval' in label.lower() for label in labels)
        annotations=[*fig.texts,ax.title,ax._left_title,*ax.texts,ax.xaxis.label,ax.yaxis.label]
        overlaps=[t.get_text() for t in annotations if t.get_visible() and t.get_text().strip() and b.overlaps(t.get_window_extent(renderer))]
        assert not overlaps,(stem,ax.get_title(loc='left'),overlaps)
        data_overlaps=[]
        for artist in [*ax.lines,*ax.patches]:
            # Zero baselines and row/background shading are explanatory guides.
            if not artist.get_visible() or artist.get_zorder()<=0: continue
            if artist in ax.lines and artist.get_transform()!=ax.transData: continue
            # Errorbar Line2D artists can retain a composite extent spanning
            # their caps and markers; the individual collections are audited
            # below for actual interval/point overlap.
            if stem == 'figS3' and isinstance(artist, Line2D):
                continue
            if b.overlaps(artist.get_window_extent(renderer)): data_overlaps.append(type(artist).__name__)
        for collection in ax.collections:
            if hasattr(collection,'get_segments'):
                for segment in collection.get_segments():
                    low_x,high_x=sorted(ax.get_xlim()); low_y,high_y=sorted(ax.get_ylim())
                    assert all(low_x-1e-10<=point[0]<=high_x+1e-10 and low_y-1e-10<=point[1]<=high_y+1e-10 for point in segment),(stem,'Clipped interval endpoint')
                    points=collection.get_transform().transform(segment)
                    if len(points) and b.overlaps(Bbox.from_extents(*points.min(axis=0),*points.max(axis=0))): data_overlaps.append(type(collection).__name__)
            else:
                points=collection.get_offset_transform().transform(collection.get_offsets())
                if any(b.contains(*point) for point in points): data_overlaps.append(type(collection).__name__)
        assert not data_overlaps,(stem,ax.get_title(loc='left'),data_overlaps)
        legends.append({'panel':ax.get_title(loc='left'),'bbox_canvas_fraction':[b.x0/fig.bbox.width,b.y0/fig.bbox.height,b.x1/fig.bbox.width,b.y1/fig.bbox.height],'labels':labels,'overlapping_data':data_overlaps,'overlapping_annotations':overlaps})
    titles=[ax.get_title(loc='left') for ax in fig.axes]
    assert all(re.fullmatch(r'\([a-z]\)\s+\S[\s\S]*',t) for t in titles),(stem,titles)
    assert [re.match(r'\(([a-z])\)',t)[1] for t in titles]==[chr(97+i) for i in range(len(titles))]
    expected={'figS1':6,'figS2':3,'figS3':2,'figS4':4,'figS5':4,'figS6':2}
    assert len(legends)==expected[stem]
    return {'minimum_font_pt':min(fonts),'maximum_font_pt':max(fonts),'out_of_canvas_text':outside,'legends':legends,'panel_titles':titles,'figure_legend_count':0,'legend_position':'one independent legend in the upper part of each lettered panel'}

def render_audit(fig,stem,inputs,script,legend_labels,notes=None, *, output_dir=None, audit_dir=None):
    layout=validate_panel_layout(fig,stem)
    source=Path(output_dir).resolve() if output_dir else ROOT/'reproduct'
    audit=Path(audit_dir).resolve() if audit_dir else AUDIT
    source.mkdir(parents=True,exist_ok=True); audit.mkdir(parents=True,exist_ok=True)
    outputs={}
    for ext in ('pdf','svg','png'):
        p=source/f'{stem}.{ext}'; fig.savefig(p,dpi=600,facecolor='white')
        outputs[ext]={'path':path_label(p)}
    record={'figure':stem,'scope':'Frozen-data rendering only','new_model_calls':0,'new_games':0,'new_bootstrap':0,'new_fits':0,'new_tests':0,'width_mm':175,'figure_inches':[fig.get_figwidth(),fig.get_figheight()], 'panel_font_pt':9.5,'legend_font_pt':8.5,**layout,'legend_labels':legend_labels,'outputs':outputs,'notes':notes or [],'visual_qa':'pending'}
    (audit/f'{stem}_audit_reproduct.json').write_text(json.dumps(record,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    return record
