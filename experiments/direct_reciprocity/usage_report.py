"""Separate newly incurred API usage from reused historical initialization."""
from pathlib import Path
from collections import Counter
from .run import read_json, write_json


def usage_report(root):
    root=Path(root)
    records=[]
    for path in root.rglob('*.json'):
        record=read_json(path)
        if isinstance(record,dict) and 'fingerprint' in record and 'prompt' in record:
            records.append((path,record))
    groups={'new':[],'reused':[]}
    for path,record in records:
        groups['reused' if record.get('reused_from') else 'new'].append((path,record))
    summary={}
    for name,items in groups.items():
        seen={}
        unreported=0
        conflicts=[]
        for path,r in items:
            usage=r.get('usage')
            if usage is None:
                unreported+=1
                continue
            identity=(r.get('provider'),r.get('response_id') or str(path.resolve()))
            if identity in seen and seen[identity]!=usage:
                conflicts.append(str(path))
            seen[identity]=usage
        summary[name]={'records':len(items),'statuses':dict(Counter(r['status'] for _,r in items)),
                       'distinct_reported_responses':len(seen),'unreported_usage_records':unreported,
                       'usage_conflicts':conflicts,
                       'tokens':{field:sum(u.get(field,0) for u in seen.values()) for field in
                                 ('prompt_tokens','completion_tokens','total_tokens')}}
    result={'root':str(root.resolve()),'groups':summary,
            'note':'New is newly recorded API work in this output tree. Reused token counts describe historical responses, not new charges. Unreported usage is unknown, never assumed free. Prices are not inferred.'}
    write_json(root/'API_USAGE.json',result)
    print(result['groups'])
    return result


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('root',type=Path)
    usage_report(parser.parse_args().root)
