"""Independent diagnostics; neither behavioral probes nor test scores select parents."""
from itertools import product
from pathlib import Path
from .core import act, RandomView, digest, seed_for


def behavior_profile(policy):
    histories=[()]
    outcomes=list(product('CD',repeat=2))
    for length in (1,2,3):
        histories.extend(product(outcomes,repeat=length))
    actions=[]
    for i, history in enumerate(histories):
        for repeat in range(3):
            rng=RandomView(seed_for('behavior-v1',i,repeat))
            actions.append(act(policy.compile(rng),history,rng))
    return digest(''.join(actions))


def request_budget(paths, generation=None):
    import json
    records=[]
    for directory in paths:
        for path in Path(directory).glob('*.json'):
            if generation is not None and path.name.startswith('g') and path.name[1:4].isdigit() and int(path.name[1:4]) > generation:
                continue
            record=json.loads(path.read_text(encoding='utf-8-sig'))
            if 'fingerprint' in record:
                records.append(record)
    return {'requests':len(records),'valid':sum(r['status']=='valid' for r in records),
            'invalid':sum(r['status']=='invalid' for r in records),
            'api_errors':sum(r['status']=='api_error' for r in records),
            'unknown_usage':sum(r.get('usage') is None for r in records),
            'total_tokens':sum((r.get('usage') or {}).get('total_tokens',0) for r in records),
            'prompt_tokens':sum((r.get('usage') or {}).get('prompt_tokens',0) for r in records),
            'completion_tokens':sum((r.get('usage') or {}).get('completion_tokens',0) for r in records)}


def implementation_hash():
    paths=[Path(__file__).with_name(name) for name in ('core.py','baselines.py','selection.py','prompts.py','run.py','diagnostics.py','reuse.py')]
    return digest('\n'.join(p.name+':'+digest(p.read_text(encoding='utf-8-sig')) for p in paths))


def population_behavior(population):
    profiles=[]
    errors=[]
    for policy in population:
        try:
            profiles.append(behavior_profile(policy))
        except Exception as exc:
            errors.append({'key':policy.key,'error':str(exc)})
    return {'distinct_valid_profiles':len(set(profiles)), 'profile_errors':errors,
            'profile_version':'all_histories_length_0_to_3_three_rng_replicates_v1'}
