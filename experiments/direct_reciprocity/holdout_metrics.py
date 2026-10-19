"""Setting-specific missingness and matched-context population summaries.

A failed parent measurement makes a gain undefined for that setting. It is
never a zero-gain fallback; successful measurements in other settings survive.
"""
from collections import defaultdict
from statistics import mean
import math

PAYOFF_SETTINGS = ('default', 'noise01', 'long')
SETTINGS = (*PAYOFF_SETTINGS, 'behavior')


def parent_available(parent, setting):
    cell = parent.get('measured', {}).get(setting)
    payload = 'probes' if setting == 'behavior' else 'score'
    return isinstance(cell, dict) and cell.get('status', 'ok') == 'ok' and payload in cell


def delta_value(row, setting, metric='score'):
    cell = row.get('delta', {}).get(setting)
    return cell.get(metric) if isinstance(cell, dict) else None


def setting_available(row, setting):
    if setting == 'behavior':
        cell = row.get('deployed', {}).get(setting)
        return isinstance(cell, dict) and cell.get('status') == 'ok'
    value = delta_value(row, setting)
    return value is not None and math.isfinite(value)


def matched_contexts(rows, setting):
    """Keep complete parent pools shared by every recorded condition/draw."""
    groups = defaultdict(list)
    for row in rows:
        groups[row['context']].append(row)
    return {context for context, group in groups.items()
            if all(setting_available(row, setting) for row in group)}


def missing_details(rows, setting):
    return {row['context']: row.get('missing_reasons', {}).get(setting,
            {'reason': 'measurement_unavailable'})
            for row in rows if not setting_available(row, setting)}


def cluster_summary(rows, seeds, value, summarize, *, contexts=None,
                    missing_reasons=None, include_metadata=True):
    """Equal-weight available population means, with explicit sample accounting."""
    expected = {row['context'] for row in rows}
    included = [row for row in rows if contexts is None or row['context'] in contexts]
    groups = defaultdict(list)
    for row in included:
        number = value(row)
        if number is None or not math.isfinite(number):
            raise ValueError('An unavailable value reached a population estimator')
        groups[row['seed']].append(number)
    seed_ids = [seed for seed in seeds if groups[seed]]
    result = summarize([mean(groups[seed]) for seed in seed_ids])
    if not include_metadata:
        return result
    actual = {row['context'] for row in included}
    result.update(seed_ids=seed_ids, n_seeds=len(seed_ids), context_ids=sorted(actual),
                  n_contexts=len(actual), n_observations=len(included),
                  n_expected_contexts=len(expected), missing_contexts=sorted(expected - actual),
                  missing_reasons={cid: (missing_reasons or {}).get(cid,
                                   {'reason': 'excluded_to_preserve_matched_contexts'})
                                   for cid in sorted(expected - actual)})
    result['estimable'] = bool(seed_ids)
    return result


def audit_deltas(row, parent, identity):
    issues = []
    if row.get('status', 'complete') != 'complete':
        return [identity + ': unrecovered child holdout; rerun setting-specific evaluation']
    for setting in PAYOFF_SETTINGS:
        if not parent_available(parent, setting):
            if any(delta_value(row, setting, key) is not None
                   for key in ('score', 'cooperation', 'worst_score')):
                issues.append(identity + ': unavailable parent gain must be null: ' + setting)
            if (row.get('deployed', {}).get(setting) is not None
                    or row.get('fallback', {}).get(setting) is not None
                    or setting not in row.get('missing_reasons', {})):
                issues.append(identity + ': unavailable parent setting lacks explicit missingness: ' + setting)
            continue
        for key in ('score', 'cooperation', 'worst_score'):
            deployed = row.get('deployed', {}).get(setting)
            value = delta_value(row, setting, key)
            if not isinstance(deployed, dict) or value is None:
                issues.append(identity + ': available parent has missing child result: ' + setting)
                break
            difference = deployed[key] - parent['measured'][setting][key]
            if abs(difference - value) > 1e-10:
                issues.append(identity + ': delta arithmetic: ' + setting)
            if row['fallback'][setting] and abs(value) > 1e-10:
                issues.append(identity + ': fallback arithmetic: ' + setting)
    return issues


def availability(rows, parents):
    return {setting: {
        'n_parent_contexts': sum(parent_available(p, setting) for p in parents.values()),
        'n_expected_parent_contexts': len(parents),
        'n_candidate_observations': sum(setting_available(row, setting) for row in rows),
        'n_expected_candidate_observations': len(rows),
        'matched_contexts': sorted(matched_contexts(rows, setting)),
        'missing_reasons': missing_details(rows, setting),
    } for setting in SETTINGS}
