"""Analyze paired thinking follow-ups and shared historical records."""
import argparse
from collections import Counter
from pathlib import Path
import json

import numpy as np

from .records import read_json, write_json
from .specificity import seal_selections
from .specificity_analysis import contrast, holm, aggregate_holdouts
from .condition_generation import specification
from .holdout_metrics import audit_deltas

SOURCE = Path('results/feedback_specificity_v2')
DEFAULT_ROOT = Path('results/feedback_specificity_thinking_384k_20260923')


def audit(root, m):
    root = Path(root)
    issues, records = [], []
    complete = root / 'COMPLETE.json'
    if not complete.exists():
        status_path = root / 'EXECUTION_STATUS.json'
        if status_path.exists():
            status = read_json(status_path)
            stage = status.get('stage', 'unknown')
            completed = status.get('completed', '?')
            total = status.get('total', '?')
            errors = len(status.get('errors', []))
            raise RuntimeError(
                f'Incomplete run at {root}: stage={stage}, '
                f'completed={completed}/{total}, errors={errors}; '
                'finish or discard the run before analysis'
            )
        raise RuntimeError(f'Incomplete run at {root}: missing COMPLETE.json')
    read_json(complete)
    selected = seal_selections(root, m, readonly=True)
    if len(selected['rows']) != len(m['jobs']) // m['draws'] * 3:
        issues.append('Sealed selection count differs from manifest')
    for j in m['jobs']:
        identity = j['id']
        r = read_json(root/'requests_candidates'/(identity+'.json'))
        c = read_json(root/'contexts'/(j['context']+'.json'))
        child = read_json(root/'candidates'/(identity+'.json'))
        row = read_json(root/'holdout'/(identity+'.json'))
        parent = read_json(root/'holdout'/(j['context']+'.json'))
        expected = specification(c['prompts'][j['arm']], 'deepseek', 'on', model=m['api']['model'])
        if any(r.get(k) != v for k,v in expected.items()):
            issues.append(identity+': request parameters differ')
        if r['started_at'] < m['frozen_at']:
            issues.append(identity+': generation before protocol freeze')
        if not r.get('reasoning_content'):
            issues.append(identity+': no native reasoning evidence')
        if r.get('returned_model') != m['api']['model']:
            issues.append(identity+': unexpected model')
        if child['valid'] != (r['status']=='valid'):
            issues.append(identity+': validity mismatch')
        if child['child']:
            code = r['content']
            if code.strip().startswith('```') and code.strip().splitlines()[-1].strip()=='```':
                code = '\n'.join(code.strip().splitlines()[1:-1])
            if child['child']['code'] != code:
                issues.append(identity+': code differs from returned content')
        issues.extend(audit_deltas(row, parent, identity))
        records.append(r)
    archived = [read_json(p) for p in (root/'attempt_history').glob('*/requests_candidates/*.json')]
    return {'issues':issues, 'requests':len(records),
            'archived_attempts':len(archived),
            'statuses':dict(Counter(r['status'] for r in records)),
            'returned_models':dict(Counter(r.get('returned_model') for r in records)),
            'finish_reasons':dict(Counter(r.get('finish_reason') for r in records)),
            'reasoning_chars':sum(len(r['reasoning_content']) for r in records),
            'note':'Reasoning character counts are not tokens. This is a record and arithmetic audit, not an independent game implementation.'}


def aggregate(root, m):
    return aggregate_holdouts(root, m)


def paired_metric_contrast(new, old, seeds):
    """Pair available populations only after confirming matching parent contexts."""
    if new.get('context_ids') != old.get('context_ids'):
        raise ValueError('Configuration contrast requires the same evaluable parent contexts')
    a = dict(zip(new.get('seed_ids', seeds), new['seed_values']))
    b = dict(zip(old.get('seed_ids', seeds), old['seed_values']))
    paired = [seed for seed in seeds if seed in a and seed in b]
    result = contrast([a[seed] - b[seed] for seed in paired])
    if 'seed_ids' in new:
        result.update(seed_ids=paired, context_ids=new.get('context_ids', []),
                      n_contexts=new.get('n_contexts'),
                      missing_contexts=new.get('missing_contexts', []),
                      missing_reasons=new.get('missing_reasons', {}))
    return result


def paired_focus(new, old):
    def vector(obj, arm):
        return np.asarray(obj['raw'][arm]['metrics']['default/score']['seed_values'])
    a = vector(new,'accurate')-vector(new,'mismatched')
    b = vector(old,'accurate')-vector(old,'mismatched')
    out = {'thinking_accurate_minus_mismatched':contrast(a),
           'diagnostic_advantage_change_vs_historical':contrast(a-b)}
    adjusted = holm({key:v['sign_swap_p'] for key,v in out.items()})
    for key,v in out.items():
        v['holm_p'] = adjusted[key]
        v['positive_seeds'] = sum(x>0 for x in v['seed_values'])
        v['negative_seeds'] = sum(x<0 for x in v['seed_values'])
    return out


def analyze(root, source=SOURCE, output_suffix=""):
    root, source = Path(root), Path(source)
    m = read_json(root / 'manifest.json')
    new, old = aggregate(root,m), aggregate(source,m)
    focus = paired_focus(new,old)
    exploratory = {}
    for arm in m['arms']:
        for setting in ('default','noise01','long'):
            exploratory['raw/'+arm+'/'+setting] = paired_metric_contrast(
                new['raw'][arm]['metrics'][setting+'/score'],
                old['raw'][arm]['metrics'][setting+'/score'], m['seeds'])
            for rule in ('S1','S2','S3'):
                exploratory[rule+'/'+arm+'/'+setting] = paired_metric_contrast(
                    new['selected'][rule+'/'+arm]['metrics'][setting],
                    old['selected'][rule+'/'+arm]['metrics'][setting], m['seeds'])
    limitation = ('历史配对配置比较：同时改变原生 thinking、输出预算及有效采样规则，非同期随机化，'
                  '服务端别名无法保证权重固定；H 是已使用过的测试面板。不能单独归因于思考开关，未显著不等于等效。')
    result = {'thinking':new, 'historical':old, 'focus_holm_two':focus,
              'configuration_differences_exploratory':exploratory, 'limitations':limitation,
              }
    write_json(root/f'ANALYSIS{output_suffix}.json',result)
    print(json.dumps({'focus':focus},ensure_ascii=False))
    return result


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root',nargs='?',default=str(DEFAULT_ROOT))
    parser.add_argument('--source', type=Path, default=SOURCE, help='Shared OFF parent records.')
    parser.add_argument('--output-suffix', default='')
    parser.add_argument('--audit-only', action='store_true', help='Run the optional record audit instead of analysis.')
    parser.add_argument('--audit-output', type=Path, help='Explicit destination for the optional audit JSON.')
    args = parser.parse_args()
    if args.audit_only:
        if args.audit_output is None:
            parser.error('--audit-only requires --audit-output')
        result = audit(args.root, read_json(Path(args.root) / 'manifest.json'))
        write_json(args.audit_output, result)
        print(json.dumps(result, ensure_ascii=False))
    else:
        if args.audit_output is not None:
            parser.error('--audit-output requires --audit-only')
        analyze(args.root, args.source, args.output_suffix)
