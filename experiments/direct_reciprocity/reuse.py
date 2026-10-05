"""Reuse only initial raw responses, with explicit provenance and new validation."""
from pathlib import Path
import json
from dataclasses import replace
from .core import Policy, match, digest
from .baselines import TRAIN


def reuse_initial(source_directory, destination, request_id, cfg, provider, model, read_json, write_json):
    destination=Path(destination)
    if destination.exists():
        record=read_json(destination)
        if record.get('reused_from'):
            return Policy(request_id,record['policy_code'])
        return None
    if source_directory is None:
        return None
    source_directory=Path(source_directory)
    candidates=[]
    for path in source_directory.glob(request_id+'*.json'):
        # Prevent initial-1 from accidentally matching initial-10.
        if path.name!=request_id+'.json' and not path.name.startswith(request_id+'.'):
            continue
        record=read_json(path)
        if record.get('provider')!=provider or record.get('model')!=model:
            continue
        if record.get('content') and record.get('finish_reason')!='length':
            candidates.append((record.get('started_at',0),path,record))
    for _,path,record in sorted(candidates,key=lambda item:(item[0],str(item[1]))):
        code=record['content']
        if code.strip().startswith('```'):
            lines=code.strip().splitlines()
            if lines[-1].strip()=='```':
                code='\n'.join(lines[1:-1])
        policy=Policy(request_id,code)
        try:
            policy.compile()
            for opponent in TRAIN:
                match(policy,opponent,replace(cfg,repeats=1),12345)
        except Exception:
            continue
        copied={**record,'status':'valid','original_status':record.get('status'),
                'reused_from':str(path.resolve()),'source_file_sha256':digest(path.read_text(encoding='utf-8-sig')),
                'policy_code':code,'code_hash':policy.key,
                'reuse_note':'No new API request. Original prompt/response/usage preserved; initial policy revalidated under random-import interface.'}
        write_json(destination,copied)
        return policy
    return None
