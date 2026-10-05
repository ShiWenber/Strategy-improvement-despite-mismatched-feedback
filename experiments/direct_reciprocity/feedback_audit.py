"""Independent record-level arithmetic checks; no new model calls or score selection."""
import argparse
from collections import Counter
from pathlib import Path
from statistics import mean

from .core import Policy, digest
from .feedback import MIXTURES, source_hash
from .run import read_json, write_json


def audit(root):
    root = Path(root)
    manifest = read_json(root / 'manifest.json')
    issues = []
    expected = {j['id'] for j in manifest['jobs']}
    request_ids = {p.stem for p in (root / 'requests').glob('*.json')}
    outcomes = {p.stem for p in (root / 'outcomes').glob('*.json')}
    if len(expected) != 120 or len(manifest['jobs']) != 120:
        issues.append('Request plan is not exactly 120 unique jobs')
    if request_ids - expected or outcomes - expected:
        issues.append('Unexpected request or outcome identity')
    if source_hash() != manifest['implementation_hash']:
        issues.append('Frozen source hash mismatch')
    if digest((root / 'DRAFT_BEFORE_GENERATION.md').read_text(encoding='utf-8')) != manifest['draft_sha256_before_generation']:
        issues.append('Original draft snapshot changed')
    settings_checked = 0
    for cid in manifest['contexts']:
        c = read_json(root / 'contexts' / (cid + '.json'))
        source = Path(manifest['source']) / f'minimal__paper_truncation__seed{c["seed"]}' / 'generation_000.json'
        if digest(source.read_text(encoding='utf-8')) != c['source_generation_hash']:
            issues.append(cid + ': reference changed')
        p = read_json(root / 'parents' / (cid + '.json'))
        if abs(p['training']['score'] - c['assessment'][c['slot']]['fitness'] / c['cfg']['rounds']) > 1e-10:
            issues.append(cid + ': parent training replay mismatch')
        pop = [Policy(**x) for x in c['population']]
        if pop[c['slot']].key != c['parent_key']:
            issues.append(cid + ': parent key mismatch')
    models, statuses = Counter(), Counter()
    for rid in sorted(request_ids & expected):
        request = read_json(root / 'requests' / (rid + '.json'))
        statuses[request['status']] += 1
        models[request.get('returned_model', 'unavailable')] += 1
        if rid not in outcomes:
            continue
        row = read_json(root / 'outcomes' / (rid + '.json'))
        if row['valid']:
            code = request['content']
            if code.strip().startswith('```') and code.strip().splitlines()[-1].strip() == '```':
                code = '\n'.join(code.strip().splitlines()[1:-1])
            if row['child']['code'] != code or Policy(**row['child']).key != request['code_hash']:
                issues.append(rid + ': stored policy differs from response')
        parent = read_json(root / 'parents' / (row['context'] + '.json'))
        for setting, deployed in row['deployed'].items():
            if row['fallback'][setting]:
                if deployed != parent[setting]:
                    issues.append(rid + ': fallback differs from parent')
            elif deployed != row['measurements'][setting]:
                issues.append(rid + ': deployed outcome differs from measurement')
            if setting == 'training':
                continue
            rounds = deployed['rounds']
            opponents = deployed['opponents']
            checks = {'score': mean(r['score'] for r in opponents) / rounds,
                      'cooperation': mean(r['cooperation'] for r in opponents),
                      'worst_score': min(r['score'] for r in opponents) / rounds}
            for key, actual in checks.items():
                if abs(actual - deployed[key]) > 1e-10:
                    issues.append(rid + ':' + setting + ': arithmetic ' + key)
            for name, weights in MIXTURES.items():
                actual = sum(w * r['score'] / rounds for w, r in zip(weights, opponents))
                if abs(actual - deployed['mixtures'][name]) > 1e-10:
                    issues.append(rid + ':' + setting + ': mixture ' + name)
            settings_checked += 1
    result = {'complete': request_ids == expected and outcomes == expected and not issues,
              'issues': issues, 'expected': len(expected), 'requests': len(request_ids),
              'outcomes': len(outcomes), 'test_settings_checked': settings_checked,
              'returned_models': dict(models), 'statuses': dict(statuses),
              'historical_blocked_attempts': len(list((root / 'network_blocked_attempt_1').glob('*.json'))),
              'scope': 'source provenance, response-policy identity and payoff aggregation; not full independent game replay'}
    write_json(root / 'RECORD_AUDIT.json', result)
    print(result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', nargs='?', default='results/feedback_attribution_v1')
    audit(parser.parse_args().root)
