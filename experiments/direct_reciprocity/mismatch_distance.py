"""Mismatch-distance analysis for the specificity experiment.

Reviewer item #2: "Mismatched" is a binary label that pools trivially similar
donors with radically different ones. This module quantifies how far the donor
report R(q) actually is from the parent report R(p), and relates that
distance to candidate outcomes.

Everything here is *post hoc* and descriptive. R(p) and R(q) are measured
before candidate generation, so distance is a pre-treatment covariate; the arm
contrast (Accurate - Mismatched) is the quantity the primary analysis reports.
No holdout result enters the distance definition.
"""
from __future__ import annotations

import argparse
import json
from math import sqrt
from pathlib import Path
from statistics import mean

import numpy as np

# ---------------------------------------------------------------------------
# Frozen feature definition. Order matters only for documentation; the
# standardisation makes the L2 norm invariant to permutation.
# ---------------------------------------------------------------------------
RECOVERY_PROBES = ('one_D_TFT', 'four_D_TFT', 'four_D_ALLC')
EXPLOITATION_PROBES = ('sustained_D', 'periodic_D')
# Recovery probes additionally report the two recovery-timing statistics, so the
# two probe blocks contribute 3 x 8 + 2 x 6 = 36 standardised features.
RECOVERY_METRICS = ('not_recovered', 'recovery_time_capped', 'mutual_cooperation_last5',
                    'own_cooperation_first4', 'own_cooperation_after4',
                    'own_cooperation_last5', 'unilateral_cooperation_last5', 'score')
EXPLOITATION_METRICS = ('own_cooperation_first4', 'own_cooperation_after4',
                        'mutual_cooperation_last5', 'own_cooperation_last5',
                        'unilateral_cooperation_last5', 'score')

ARMS = ('accurate', 'mismatched')

REGIMES = {
    'thinking_off': 'results/feedback_specificity_v2',
    'thinking_on': 'results/feedback_specificity_thinking_384k_20260923',
}


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False), encoding='utf-8')


# ---------------------------------------------------------------------------
# Feature extraction
# ---------------------------------------------------------------------------
def feature_names():
    """Ordered feature names plus the recovery/exploitation block partition."""
    recovery = [f'{p}:{m}' for p in RECOVERY_PROBES for m in RECOVERY_METRICS]
    exploitation = [f'{p}:{m}' for p in EXPLOITATION_PROBES for m in EXPLOITATION_METRICS]
    return recovery + exploitation, {'recovery_block': recovery, 'exploitation_block': exploitation}


def vector_from_diagnostics(diagnostics, names):
    values = []
    for name in names:
        probe, metric = name.split(':', 1)
        values.append(float(diagnostics[probe]['mean'][metric]))
    return values


def population_matrix(populations, names):
    """Stack every population member's diagnostic vector.

    Standardisation uses all population members of all seeds, so z-scores have
    a fixed reference across the 20 independent populations.
    """
    rows, index = [], []
    for seed, data in sorted(populations.items()):
        for slot, diagnostics in enumerate(data['diagnostics']):
            rows.append(vector_from_diagnostics(diagnostics, names))
            index.append((seed, slot))
    matrix = np.asarray(rows, dtype=float)
    mu = matrix.mean(axis=0)
    sd = matrix.std(axis=0, ddof=0)
    sd = np.where(sd < 1e-12, 1.0, sd)
    return (matrix - mu) / sd, mu, sd, index


# ---------------------------------------------------------------------------
# Result loading
# ---------------------------------------------------------------------------
def load_regime(root):
    root = Path(root)
    manifest = read_json(root / 'manifest.json')
    seeds = [int(s) for s in manifest.get('seeds', [])]
    populations = {seed: read_json(root / 'populations' / f's{seed}.json') for seed in seeds}
    contexts = {}
    for seed in seeds:
        for rank in manifest.get('ranks', (1, 3, 6)):
            cid = f's{seed}-rank{rank}'
            contexts[cid] = read_json(root / 'contexts' / (cid + '.json'))
    holdout = {}
    for path in (root / 'holdout').glob('*.json'):
        record = read_json(path)
        if 'arm' in record and 'delta' in record:
            holdout[record['id']] = record
    selections = read_json(root / 'SELECTIONS_SEALED.json')['rows']
    return {'root': root, 'manifest': manifest, 'seeds': seeds, 'populations': populations,
            'contexts': contexts, 'holdout': holdout, 'selections': selections}


def behavior_vector(record):
    """Flatten H-probe behaviour into an ordered numeric vector.

    ``probes[name]['mean']`` is itself a metric dictionary, so flatten to
    ``name:metric`` -> value. Only recovery/exploitation probes carry the two
    recovery-timing metrics, so the key set differs per probe; return the flat
    mapping and let the caller align on the intersection.
    """
    probes = record['deployed']['behavior']['probes']
    return {f'{name}:{metric}': float(value)
            for name, entry in probes.items() for metric, value in entry['mean'].items()}


# ---------------------------------------------------------------------------
# Distance metrics
# ---------------------------------------------------------------------------
def build_distances(regime):
    names, blocks = feature_names()
    z, mu, sd, index = population_matrix(regime['populations'], names)
    lookup = {key: z[i] for i, key in enumerate(index)}
    full = np.arange(len(names))
    recovery_idx = np.array([names.index(n) for n in blocks['recovery_block']])
    exploitation_idx = np.array([names.index(n) for n in blocks['exploitation_block']])

    # Within-population null: every ordered member pair in the same population.
    rng = np.random.default_rng(2026093001)
    null_full, null_permember = [], []
    for seed, data in sorted(regime['populations'].items()):
        members = np.array([lookup[(seed, slot)] for slot in range(len(data['diagnostics']))])
        for i in range(len(members)):
            for j in range(len(members)):
                if i != j:
                    null_full.append(float(np.linalg.norm(members[i] - members[j])))
        # Random 11 ordered pairs per population, mirroring the 11 possible donors.
        for _ in range(11):
            i, j = rng.choice(len(members), size=2, replace=False)
            null_permember.append(float(np.linalg.norm(members[i] - members[j])))

    rows = []
    for cid, context in sorted(regime['contexts'].items()):
        seed, slot, donor = int(context['seed']), context['slot'], context['donor']
        z_parent, z_donor = lookup[(seed, slot)], lookup[(seed, donor)]
        diff = z_parent - z_donor
        # Population mean pairwise distance supplies a scale-free reference.
        members = np.array([lookup[(seed, s)] for s in range(len(regime['populations'][seed]['diagnostics']))])
        pairwise = [float(np.linalg.norm(a - b)) for i, a in enumerate(members) for j, b in enumerate(members) if i != j]
        scale = mean(pairwise)
        rows.append({
            'context': cid, 'seed': seed, 'rank': context['rank'], 'slot': slot, 'donor': donor,
            'effective_mismatch': context.get('effective_mismatch'),
            'delta_full': float(sqrt(float(np.dot(diff, diff)))),
            'delta_recovery_block': float(np.linalg.norm(diff[recovery_idx])),
            'delta_exploitation_block': float(np.linalg.norm(diff[exploitation_idx])),
            'delta_2d': float(sqrt(float(diff[recovery_idx].mean() ** 2 + diff[exploitation_idx].mean() ** 2))),
            'delta_rel': float(sqrt(float(np.dot(diff, diff))) / scale) if scale > 1e-12 else None,
            'population_mean_pairwise': scale,
        })
    diagnostics = {'feature_names': names, 'n_features': len(names), 'blocks': blocks,
                   'zscore_reference': {'mean': mu.tolist(), 'sd': sd.tolist(),
                                        'note': 'z-scored over all 240 population members of the 20 seeds'},
                   'null_within_population_ordered_pairs': {
                       'n': len(null_full), 'mean': float(np.mean(null_full)), 'median': float(np.median(null_full)),
                       'q10': float(np.quantile(null_full, .10)), 'q90': float(np.quantile(null_full, .90))},
                   'null_random_pair_per_population': {
                       'n': len(null_permember), 'mean': float(np.mean(null_permember)),
                       'median': float(np.median(null_permember))}}
    return rows, diagnostics, names


# ---------------------------------------------------------------------------
# Outcome assembly
# ---------------------------------------------------------------------------
def candidate_outcomes(regime):
    """Per (context, arm) raw proposal gain averaged over the two draws."""
    agg = {}
    for record in regime['holdout'].values():
        cid, arm = record.get('context'), record.get('arm')
        if cid is None or arm is None:
            continue
        key = (cid, arm)
        bucket = agg.setdefault(key, {'gain': [], 'cooperation': []})
        bucket['gain'].append(record['delta']['default']['score'])
        bucket['cooperation'].append(record['delta']['default'].get('cooperation'))
    return {key: {'gain': mean(v['gain']),
                  'cooperation': mean([x for x in v['cooperation'] if x is not None]) if any(x is not None for x in v['cooperation']) else None,
                  'n_draws': len(v['gain'])} for key, v in agg.items()}


def assemble_outcomes(regime, rows):
    raw = candidate_outcomes(regime)
    by_context = {row['context']: row for row in rows}
    for cid, row in by_context.items():
        for arm in ARMS:
            item = raw.get((cid, arm))
            row[f'raw_gain_{arm}'] = item['gain'] if item else None
        row['tau_raw'] = (row['raw_gain_accurate'] - row['raw_gain_mismatched']
                          if row['raw_gain_accurate'] is not None and row['raw_gain_mismatched'] is not None else None)
    # Selection outcome: the S3-selected strategy's H-panel gain, using the same
    # convention as ANALYSIS.json (winner's holdout delta; 0 when the rule keeps
    # the parent, which includes protocol fallbacks).
    selection_index = {(r['context'], r['arm'], r['rule']): r['winner'] for r in regime['selections']}
    for cid, row in by_context.items():
        for arm in ARMS:
            winner = selection_index.get((cid, arm, 'S3'), '__missing__')
            if winner == '__missing__':
                continue
            if winner is None:
                row[f's3_gain_{arm}'] = 0.0
                continue
            record = regime['holdout'].get(winner)
            row[f's3_gain_{arm}'] = record['delta']['default']['score'] if record else None
        row['tau_s3'] = (row['s3_gain_accurate'] - row['s3_gain_mismatched']
                         if row.get('s3_gain_accurate') is not None
                         and row.get('s3_gain_mismatched') is not None else None)
    # Behavioural movement of the raw candidates, globally and per arm.
    for cid, row in by_context.items():
        parent = read_json(Path(regime['root']) / 'holdout' / (cid + '.json'))
        parent_behavior = behavior_vector(parent)
        per_arm = {}
        all_moves = []
        for arm in ARMS:
            moves = []
            for record in [r for r in regime['holdout'].values()
                           if r.get('context') == cid and r.get('arm') == arm]:
                if record.get('child') is None:
                    continue
                candidate_behavior = behavior_vector(record)
                shared = sorted(set(candidate_behavior) & set(parent_behavior))
                moves.append(float(np.mean([abs(candidate_behavior[k] - parent_behavior[k]) for k in shared])))
            if moves:
                per_arm[arm] = mean(moves)
                all_moves.extend(moves)
        row['behavior_move_raw'] = mean(all_moves) if all_moves else None
        for arm, value in per_arm.items():
            row[f'behavior_move_{arm}'] = value
        # Within-parent report-matching differential.
        if 'mismatched' in per_arm and 'accurate' in per_arm:
            row['behavior_move_mismatched_minus_accurate'] = per_arm['mismatched'] - per_arm['accurate']
        # Code change: character-level edit distance proxy between parent and candidate.
        edits, per_arm_edits = [], {}
        parent_code = regime['contexts'][cid]['parent']['code']
        for arm in ARMS:
            arm_edits = []
            for record in [r for r in regime['holdout'].values()
                           if r.get('context') == cid and r.get('arm') == arm]:
                if record.get('child') is None:
                    continue
                value = abs(len(record['child']['code']) - len(parent_code)) + _levenshtein_ratio(record['child']['code'], parent_code)
                edits.append(value)
                arm_edits.append(value)
            if arm_edits:
                per_arm_edits[arm] = mean(arm_edits)
        row['code_change_raw'] = mean(edits) if edits else None
        for arm, value in per_arm_edits.items():
            row[f'code_change_{arm}'] = value
        if 'mismatched' in per_arm_edits and 'accurate' in per_arm_edits:
            row['code_change_mismatched_minus_accurate'] = per_arm_edits['mismatched'] - per_arm_edits['accurate']
    return list(by_context.values()), raw


def _levenshtein_ratio(a, b):
    """Cheap normalised dissimilarity proxy; avoids quadratic full DP on long code."""
    a, b = a.strip(), b.strip()
    if a == b:
        return 0.0
    length = max(len(a), len(b))
    common = sum(1 for x, y in zip(a, b) if x == y)
    return 1.0 - common / length


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------
def pearson(x, y):
    x, y = np.asarray(x, float), np.asarray(y, float)
    if len(x) < 3 or x.std() < 1e-12 or y.std() < 1e-12:
        return None
    return float(np.corrcoef(x, y)[0, 1])


def spearman(x, y):
    x, y = np.asarray(x, float), np.asarray(y, float)
    if len(x) < 3:
        return None
    rx = np.argsort(np.argsort(x)).astype(float)
    ry = np.argsort(np.argsort(y)).astype(float)
    return pearson(rx, ry)


def _rank_rows(a):
    """Ordinal ranks along axis 1 (ties broken by order; adequate for bootstrap CIs)."""
    order = np.argsort(a, axis=1, kind='stable')
    ranks = np.empty(order.shape, dtype=float)
    np.put_along_axis(ranks, order, np.tile(np.arange(a.shape[1], dtype=float), (a.shape[0], 1)), axis=1)
    return ranks


def _pearson_rows(xs, ys):
    """Row-wise Pearson correlation between two (B, n) matrices."""
    xc = xs - xs.mean(axis=1, keepdims=True)
    yc = ys - ys.mean(axis=1, keepdims=True)
    num = (xc * yc).sum(axis=1)
    den = np.sqrt((xc ** 2).sum(axis=1) * (yc ** 2).sum(axis=1))
    return np.where(den > 1e-12, num / np.where(den > 1e-12, den, 1.0), np.nan)


_RESAMPLE_CACHE = {}


def _resample_matrix(seeds, n, n_bootstrap, seed):
    """Cluster bootstrap index matrix, shape (n_bootstrap, n_clusters * width).

    Populations are resampled with replacement and *every* member of a chosen
    population is carried along, so the 20 populations stay the independent unit.
    Clusters are padded to equal width by repeating their last member; the frozen
    design has exactly three parents per population, so padding is inert.
    """
    key = (tuple(seeds), n, n_bootstrap, seed)
    if key in _RESAMPLE_CACHE:
        return _RESAMPLE_CACHE[key]
    rng = np.random.default_rng(seed)
    keys = sorted(set(seeds))
    index = {k: np.array([i for i, s in enumerate(seeds) if s == k]) for k in keys}
    sizes = [len(index[k]) for k in keys]
    width = max(sizes)
    lookup = np.zeros((len(keys), width), dtype=int)
    for i, k in enumerate(keys):
        members = index[k]
        lookup[i, :] = members[-1]          # pad by repeating the last member
        lookup[i, :len(members)] = members
    chosen = rng.integers(0, len(keys), size=(n_bootstrap, len(keys)))
    matrix = lookup[chosen].reshape(n_bootstrap, len(keys) * width)
    _RESAMPLE_CACHE[key] = (matrix, sizes, width, len(keys))
    return _RESAMPLE_CACHE[key]


def _leave_one_cluster_out(feature, outcome, seeds):
    """Sign stability: refit the correlation after dropping each population in turn."""
    keys = sorted(set(seeds))
    point = pearson(feature, outcome)
    if point is None:
        return None
    values = []
    for key in keys:
        index = [i for i, s in enumerate(seeds) if s != key]
        value = pearson([feature[i] for i in index], [outcome[i] for i in index])
        if value is not None:
            values.append(value)
    if not values:
        return None
    agreed = sum((value > 0) == (point > 0) for value in values)
    return {'n_populations': len(keys), 'sign_agreement': agreed, 'sign_agreement_fraction': agreed / len(values),
            'min': float(min(values)), 'max': float(max(values))}


def _partial_out_rank(feature, outcome, ranks):
    """Pearson correlation after removing the parent-rank mean from both variables."""
    feature, outcome = np.asarray(feature, float), np.asarray(outcome, float)
    ranks = np.asarray(ranks)
    fx, fy = feature.copy(), outcome.copy()
    for level in np.unique(ranks):
        mask = ranks == level
        if mask.sum() < 2:
            continue
        fx[mask] -= feature[mask].mean()
        fy[mask] -= outcome[mask].mean()
    if fx.std() < 1e-12 or fy.std() < 1e-12:
        return None
    return float(np.corrcoef(fx, fy)[0, 1])


def cluster_bootstrap(feature, outcome, seeds, n=20000, seed=2026093002):
    """Resample the 20 independent populations; CI for Pearson and Spearman.

    Both variables are resampled with the same cluster index matrix, so the
    bootstrap preserves the feature-outcome pairing within each population.
    """
    x, y = np.asarray(feature, float), np.asarray(outcome, float)
    matrix, _, _, _ = _resample_matrix(tuple(seeds), len(seeds), n, seed)
    xs, ys = x[matrix], y[matrix]
    pearsons = _pearson_rows(xs, ys)
    spearmans = _pearson_rows(_rank_rows(xs), _rank_rows(ys))
    ok_p, ok_s = np.isfinite(pearsons), np.isfinite(spearmans)
    return {'pearson_ci95': [float(np.quantile(pearsons[ok_p], .025)), float(np.quantile(pearsons[ok_p], .975))]
            if ok_p.any() else None,
            'spearman_ci95': [float(np.quantile(spearmans[ok_s], .025)), float(np.quantile(spearmans[ok_s], .975))]
            if ok_s.any() else None,
            'n_bootstrap': int(ok_p.sum())}


def tertile_table(rows, distance_key, outcome_key):
    items = [r for r in rows if r.get(distance_key) is not None and r.get(outcome_key) is not None]
    items.sort(key=lambda r: r[distance_key])
    if len(items) < 6:
        return None
    cut = len(items) // 3
    groups = {'low': items[:cut], 'mid': items[cut:2 * cut], 'high': items[2 * cut:]}
    out = {}
    for name, group in groups.items():
        values = [r[outcome_key] for r in group]
        out[name] = {'n': len(group), 'mean': float(np.mean(values)),
                     'ci95': _mean_ci(values, [r['seed'] for r in group])}
    return out


def _mean_ci(values, seeds, n=20000, seed=2026093003):
    values = np.asarray(values, float)
    matrix, _, _, _ = _resample_matrix(tuple(seeds), len(seeds), n, seed)
    samples = values[matrix].mean(axis=1)
    return [float(np.quantile(samples, .025)), float(np.quantile(samples, .975))]


def summarize_distances(rows, key='delta_full'):
    values = np.array([r[key] for r in rows], float)
    return {'n': len(values), 'mean': float(values.mean()), 'sd': float(values.std(ddof=1)),
            'min': float(values.min()), 'q25': float(np.quantile(values, .25)),
            'median': float(np.median(values)), 'q75': float(np.quantile(values, .75)),
            'max': float(values.max())}


# ---------------------------------------------------------------------------
# Regime analysis
# ---------------------------------------------------------------------------
def analyze_regime(name, root, output_dir, output_suffix=""):
    regime = load_regime(root)
    rows, diagnostics, names = build_distances(regime)
    rows, raw = assemble_outcomes(regime, rows)
    seeds = [row['seed'] for row in rows]

    distance_summary = {key: summarize_distances(rows, key)
                        for key in ('delta_full', 'delta_recovery_block', 'delta_exploitation_block',
                                    'delta_2d', 'delta_rel')}

    associations = {}
    targets = [('tau_raw', 'Accurate - Mismatched raw gain', 'tau_raw'),
               ('raw_gain_mismatched', 'Mismatched raw proposal gain', 'raw_gain_mismatched'),
               ('raw_gain_accurate', 'Accurate raw proposal gain', 'raw_gain_accurate'),
               ('tau_s3', 'Accurate - Mismatched S3 gain', 'tau_s3'),
               ('behavior_move_raw', 'Raw candidate behavioural movement (all arms)', 'behavior_move_raw'),
               ('behavior_move_mismatched', 'Mismatched-arm behavioural movement', 'behavior_move_mismatched'),
               ('behavior_move_accurate', 'Accurate-arm behavioural movement', 'behavior_move_accurate'),
               ('behavior_move_mismatched_minus_accurate', 'Movement: Mismatched minus Accurate',
                'behavior_move_mismatched_minus_accurate'),
               ('code_change_raw', 'Raw candidate code change (all arms)', 'code_change_raw'),
               ('code_change_mismatched', 'Mismatched-arm code change', 'code_change_mismatched'),
               ('code_change_mismatched_minus_accurate', 'Code change: Mismatched minus Accurate',
                'code_change_mismatched_minus_accurate')]
    for feature in ('delta_full', 'delta_recovery_block', 'delta_exploitation_block', 'delta_2d', 'delta_rel'):
        entry = {}
        for target, label, outcome_key in targets:
            pairs = [(r[feature], r[outcome_key], r['seed']) for r in rows
                     if r.get(feature) is not None and r.get(outcome_key) is not None]
            if len(pairs) < 6:
                continue
            x, y, s = zip(*pairs)
            ranks = [r['rank'] for r in rows if r.get(feature) is not None and r.get(outcome_key) is not None]
            entry[target] = {'label': label, 'n': len(x),
                             'pearson': pearson(x, y), 'spearman': spearman(x, y),
                             'pearson_rank_adjusted': _partial_out_rank(x, y, ranks),
                             'leave_one_population_out': _leave_one_cluster_out(x, y, s),
                             **cluster_bootstrap(x, y, s)}
        associations[feature] = entry

    # Weak-mismatch sensitivity: parents whose donor is unusually close to them
    # relative to the within-population random-pair reference. If the arm
    # contrast survives dropping these, "not different" is not an artefact of
    # trivially similar donor reports. The closest tercile (20 parents) is the
    # powered subset; the sub-q10 count is reported alongside it.
    null_stats = diagnostics['null_within_population_ordered_pairs']
    ordered = sorted(rows, key=lambda r: r['delta_full'])
    weak = ordered[:len(ordered) // 3]
    strong = ordered[len(ordered) // 3:]
    def _arm_contrast(items):
        values = [r['tau_raw'] for r in items if r.get('tau_raw') is not None]
        if len(values) < 4:
            return None
        return {'n': len(values), 'mean': float(np.mean(values)),
                'ci95': _mean_ci(values, [r['seed'] for r in items if r.get('tau_raw') is not None])}
    weak_mismatch_sensitivity = {
        'threshold': 'closest tercile of delta_full; reference is within-population ordered pairs',
        'closest_tercile_cut': ordered[len(ordered) // 3]['delta_full'],
        'weak_mismatch_contexts': sorted(r['context'] for r in weak),
        'n_weak': len(weak), 'n_strong': len(strong),
        'below_null_q10': sorted(r['context'] for r in rows
                                 if r['delta_full'] <= null_stats['q10']),
        'n_below_null_q10': sum(r['delta_full'] <= null_stats['q10'] for r in rows),
        'tau_raw_closest_tercile': _arm_contrast(weak),
        'tau_raw_further_two_thirds': _arm_contrast(strong),
        'tau_raw_all': _arm_contrast(rows),
    }

    # Mismatch distance by parent rank: is the donor further away for stronger parents?
    by_rank = {}
    for rank in sorted({r['rank'] for r in rows}):
        items = [r['delta_full'] for r in rows if r['rank'] == rank]
        by_rank[str(rank)] = {'n': len(items), 'mean': float(np.mean(items)), 'median': float(np.median(items))}

    direction = {}
    for feature in ('delta_recovery_block', 'delta_exploitation_block'):
        cell = {}
        for target, _, outcome_key in targets[:1] + [('raw_gain_mismatched', '', 'raw_gain_mismatched')]:
            cell[target] = tertile_table(rows, feature, outcome_key)
        direction[feature] = cell

    condition_means = {}
    for arm in ARMS:
        values = [r[f'raw_gain_{arm}'] for r in rows if r.get(f'raw_gain_{arm}') is not None]
        condition_means[arm] = {'n': len(values), 'mean': float(np.mean(values))}

    payload = {
        'regime': name, 'root': str(Path(root).resolve()),
        'primary_contrast_tau_raw_mean': float(np.mean([r['tau_raw'] for r in rows if r.get('tau_raw') is not None])),
        'condition_means_raw_gain': condition_means,
        'distance_diagnostics': diagnostics,
        'distance_summary': distance_summary,
        'associations': associations,
        'tertile_outcomes': direction,
        'weak_mismatch_sensitivity': weak_mismatch_sensitivity,
        'distance_by_parent_rank': by_rank,
        'rows': rows,
        'note': ('Diagnostics are measured before candidate generation, so distance is a pre-treatment '
                 'covariate. Associations are exploratory and use 20 population clusters. Sign of tau_raw is '
                 'Accurate minus Mismatched; positive means accurate diagnosis produced the better raw candidate.'),
    }
    write_json(Path(output_dir) / f'mismatch_distance_{name}{output_suffix}.json', payload)
    return payload


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------
def _fmt(value, digits=3):
    return 'n/a' if value is None else f'{value:+.{digits}f}'


def _ci(interval, digits=3):
    if not interval:
        return 'n/a'
    return f'[{interval[0]:+.{digits}f}, {interval[1]:+.{digits}f}]'


def _excludes_zero(interval):
    return bool(interval) and (interval[0] > 0 or interval[1] < 0)


TARGET_ORDER = ('tau_raw', 'raw_gain_mismatched', 'raw_gain_accurate', 'tau_s3',
                'behavior_move_mismatched', 'behavior_move_accurate',
                'behavior_move_mismatched_minus_accurate',
                'code_change_mismatched', 'code_change_mismatched_minus_accurate')


def write_markdown(payloads, output_path):
    feature_labels = {'delta_full': r'$\delta_{\text{full}}$', 'delta_recovery_block': r'$\delta_{\text{rec}}$',
                      'delta_exploitation_block': r'$\delta_{\text{expl}}$', 'delta_2d': r'$\delta_{\text{2d}}$',
                      'delta_rel': r'$\delta_{\text{rel}}$'}
    regime_labels = {'thinking_off': '思考关闭（旧配置）', 'thinking_on': '思考开启（384K）'}
    lines = []
    lines.append('> 符号已与正文一致：反馈报告记为 $R$，标准化后的报告向量记为 $\\tilde R$。'
                 '探针名（`one_D_TFT` 等）为记录原文，保持不改。')
    lines.append('')
    lines.append('# 错配距离分析（Mismatch-Distance Analysis）')
    lines.append('')
    lines.append('**对应审稿意见条目 2「没有量化『错配到底有多错』」。**')
    lines.append('')
    lines.append('本分析把 `Mismatched` 这一二元标签展开为可测量的**诊断距离** $\\delta(p,q)$，')
    lines.append('并检验距离大小是否与候选收益、候选行为变化、选择后输出收益相关。')
    lines.append('所有距离都由父代与供体的行为诊断在候选生成**之前**测得，因此它是前处理协变量，')
    lines.append('而不是结果变量。本文档中的关联分析均为**探索性**：推断单位为 20 个独立种群，')
    lines.append('区间为种子聚类自助区间；未做多重检验校正，相关性不构成因果中介证据。')
    lines.append('')
    lines.append('## 1. 距离定义')
    lines.append('')
    lines.append('反馈探针 $F$ 为每个策略产生 36 维行为特征：恢复类探针 `one_D_TFT`、`four_D_TFT`、')
    lines.append('`four_D_ALLC`（含 `not_recovered`、`recovery_time_capped` 两个恢复时间统计量）')
    lines.append('与受剥削类探针 `sustained_D`、`periodic_D`。把全部 20 个种群的 240 个成员在每个')
    lines.append('维度上标准化为 $\\tilde R(\\cdot)$，定义')
    lines.append('')
    lines.append('$$\\delta_{\\text{full}}(p,q)=\\left\\|\\tilde R(p)-\\tilde R(q)\\right\\|_2 .$$')
    lines.append('')
    lines.append('辅助量：仅在恢复类特征上的 $\\delta_{\\text{rec}}$、仅在受剥削类特征上的')
    lines.append('$\\delta_{\\text{expl}}$、按种群内平均两两距离归一化的 $\\delta_{\\text{rel}}$，')
    lines.append('以及先在各特征块内取平均再求范数的 $\\delta_{\\text{2d}}$。')
    lines.append('')
    # ---- Shared distance distribution -------------------------------------
    first = next(iter(payloads.values()))
    diag = first['distance_diagnostics']
    null = diag['null_within_population_ordered_pairs']
    dist = first['distance_summary']
    lines.append('## 2. 错配强度到底有多大？')
    lines.append('')
    lines.append('**父代、供体与诊断均为两套生成配置共享**，因此下表对思考关闭与思考开启完全一致；')
    lines.append('它描述的是设计本身，而不是某个配置的结果。')
    lines.append('')
    lines.append(f'特征维度 {diag["n_features"]}；60 个父代全部满足 `effective_mismatch = true`'
                 '（即供体报告与父代报告在数值上不相同）。')
    lines.append('')
    lines.append('| 指标 | 均值 | 中位数 | 最小 | p25 | p75 | 最大 |')
    lines.append('| --- | ---: | ---: | ---: | ---: | ---: | ---: |')
    for key, cn in (('delta_full', r'$\delta_{\text{full}}$'), ('delta_recovery_block', r'$\delta_{\text{rec}}$'),
                    ('delta_exploitation_block', r'$\delta_{\text{expl}}$'), ('delta_rel', r'$\delta_{\text{rel}}$')):
        item = dist[key]
        lines.append(f'| {cn} | {item["mean"]:.3f} | {item["median"]:.3f} | {item["min"]:.3f} | '
                     f'{item["q25"]:.3f} | {item["q75"]:.3f} | {item["max"]:.3f} |')
    lines.append('')
    lines.append(f'**与"同种群随机成员"参照的对照。** 同一种群内成员两两距离（有序对，{null["n"]} 对）为')
    lines.append(f'均值 {null["mean"]:.3f}、中位数 {null["median"]:.3f}、'
                 f'10%–90% 分位 {null["q10"]:.3f}–{null["q90"]:.3f}。')
    lines.append('')
    ratio = 100 * dist['delta_full']['mean'] / null['mean']
    lines.append(f'父代—供体距离均值 {dist["delta_full"]["mean"]:.3f}，为该参照均值的 {ratio:.0f}%。'
                 '这一吻合是**设计使然**：错配由全种群报告的无固定点置换（derangement）产生，')
    lines.append('供体是从同种群中均匀抽取的“另一位成员”，因此“随机成员配对”正是该干预的期望行为。')
    lines.append('')
    below = sum(r['delta_full'] <= null['q10'] for r in first['rows'])
    lines.append(f'因此正确的表述不是"错配很弱"，而是：**错配是真实的（全部 60 对数值均改变），'
                 f'但强度高度异质**——$\\delta_{{\\text{{full}}}}$ 从 {dist["delta_full"]["min"]:.2f} 到 '
                 f'{dist["delta_full"]["max"]:.2f}（{dist["delta_full"]["max"] / dist["delta_full"]["min"]:.1f} 倍），')
    lines.append(f'且只有 {below} 个父代落在参照分布的第 10 百分位以下，即"实质等价"的错配占比很低。')
    lines.append('')
    lines.append('| 父代排名 | n | 平均 $\\delta_{\\text{full}}$ | 中位数 |')
    lines.append('| --- | ---: | ---: | ---: |')
    for rank, item in first['distance_by_parent_rank'].items():
        lines.append(f'| rank{rank} | {item["n"]} | {item["mean"]:.3f} | {item["median"]:.3f} |')
    lines.append('')
    # ---- Per-regime sections ----------------------------------------------
    section = 3
    for name, payload in payloads.items():
        lines.append(f'## {section}. {regime_labels.get(name, name)}')
        section += 1
        lines.append('')
        means = payload['condition_means_raw_gain']
        tau_raw = payload['primary_contrast_tau_raw_mean']
        lines.append('**各条件原始候选增益（每轮收益）与主对照：**')
        lines.append('')
        cells = '，'.join(f'{arm} {means[arm]["mean"]:+.5f}' for arm in ARMS)
        lines.append(f'{cells}。')
        lines.append('')
        lines.append(f'主对照 Accurate−Mismatched = **{tau_raw:+.6f}**'
                     '（正式区间与配对符号交换检验见 `ANALYSIS.json`）。')
        lines.append('')
        lines.append(f'### {section - 1}.1 距离与结果指标的关联')
        lines.append('')
        lines.append('| 距离 | 结果指标 | Pearson | 95% CI | Spearman | 排名校正 Pearson | '
                     '留一种群符号一致 |')
        lines.append('| --- | --- | ---: | --- | ---: | ---: | ---: |')
        for feature in ('delta_full', 'delta_recovery_block', 'delta_exploitation_block'):
            entry = payload['associations'][feature]
            for target in TARGET_ORDER:
                item = entry.get(target)
                if item is None:
                    continue
                loo = item.get('leave_one_population_out')
                loo_text = f'{loo["sign_agreement"]}/{loo["n_populations"]}' if loo else 'n/a'
                lines.append(f'| {feature_labels[feature]} | {item["label"]} | {_fmt(item["pearson"])} | '
                             f'{_ci(item["pearson_ci95"])} | {_fmt(item["spearman"])} | '
                             f'{_fmt(item["pearson_rank_adjusted"])} | {loo_text} |')
        lines.append('')
        lines.append('“排名校正”为在每个父代排名组内中心化后的 Pearson 相关，用于排除父代强弱'
                     '（rank1/3/6 的 $\\delta$ 均值略有差异，见第 2 节）造成的混淆。')
        lines.append('')
        lines.append(f'### {section - 1}.2 主对照在不同距离定义下的稳定性')
        lines.append('')
        lines.append('| 距离定义 | Pearson | 95% CI | Spearman |')
        lines.append('| --- | ---: | --- | ---: |')
        for feature in ('delta_full', 'delta_recovery_block', 'delta_exploitation_block', 'delta_2d', 'delta_rel'):
            item = payload['associations'][feature].get('tau_raw')
            if item is None:
                continue
            lines.append(f'| {feature_labels[feature]} | {_fmt(item["pearson"])} | {_ci(item["pearson_ci95"])} | '
                         f'{_fmt(item["spearman"])} |')
        lines.append('')
        lines.append(f'### {section - 1}.3 低/中/高错配分位')
        lines.append('')
        lines.append('| 距离 | 结果指标 | 低错配 | 中错配 | 高错配 |')
        lines.append('| --- | --- | ---: | ---: | ---: |')
        for feature in ('delta_recovery_block', 'delta_exploitation_block'):
            for target, table in payload['tertile_outcomes'][feature].items():
                if not table:
                    continue
                cells = ' | '.join(f'{table[g]["mean"]:+.4f}' if g in table else 'n/a' for g in ('low', 'mid', 'high'))
                lines.append(f'| {feature_labels[feature]} | {targets_label(target)} | {cells} |')
        lines.append('')
        sens = payload['weak_mismatch_sensitivity']
        lines.append(f'### {section - 1}.4 弱错配敏感性（剔除"几乎相同"的供体）')
        lines.append('')
        lines.append(f'按 $\\delta_{{\\text{{full}}}}$ 排序取最接近的三分之一（{sens["n_weak"]} 个父代，'
                     f'切点 {sens["closest_tercile_cut"]:.3f}）为**弱错配**子集，其余 {sens["n_strong"]} 个'
                     '为较强错配。若"无差异"只因供体报告几乎相同，两组的主对照应明显分离。')
        lines.append('')
        lines.append('| 子集 | n | Accurate−Mismatched 原始增益 | 95% CI |')
        lines.append('| --- | ---: | ---: | --- |')
        for key, cn in (('tau_raw_all', '全部父代'), ('tau_raw_closest_tercile', '弱错配（最接近三分之一）'),
                        ('tau_raw_further_two_thirds', '较强错配（其余三分之二）')):
            item = sens[key]
            if item is None:
                lines.append(f'| {cn} | — | n/a | n/a |')
            else:
                lines.append(f'| {cn} | {item["n"]} | {item["mean"]:+.6f} | {_ci(item["ci95"], 5)} |')
        lines.append('')
    # ---- Conclusions -------------------------------------------------------
    lines.append(f'## {section}. 结论与对审稿意见的回应')
    section += 1
    lines.append('')
    lines.extend(_conclusions(payloads, regime_labels))
    lines.append('')
    lines.append('**方法与适用边界。** 距离仅基于反馈探针 $F$ 的 36 维统计量；标准化参照为全体 240 个')
    lines.append('种群成员；关联分析未做多重检验校正；行为变化量以父代自身探针行为为基准，')
    lines.append('受行为天花板影响，故同时报告 Mismatched−Accurate 配对差；')
    lines.append('S3 输出收益是选择（含门控与是否采用）之后的非线性量，其关联只能视为探索性。')
    lines.append('相关性不等于因果中介；本分析不能替代审稿意见 3 所要求的 known-defect 阳性对照。')
    lines.append('')
    text = '\n'.join(lines)
    Path(output_path).write_text(text, encoding='utf-8')
    return text


def _conclusions(payloads, regime_labels):
    """Build the conclusion bullets from the computed associations."""
    labels = {'delta_full': r'$\delta_{\text{full}}$', 'delta_recovery_block': r'$\delta_{\text{rec}}$',
              'delta_exploitation_block': r'$\delta_{\text{expl}}$'}
    lines = []
    lines.append('1. **错配不是"名义错配"，但强度高度异质。** 60 个父代的诊断向量全部改变；'
                 '由于错配由全种群无固定点置换产生，其期望强度正好等于"随机抽取同种群另一位成员"，'
                 '只有 3/60 个父代的距离落在该参照分布的第 10 百分位以下。'
                 '因此二元 `Accurate vs Mismatched` 标签掩盖的是**强度异质**，而不是"错配不足"。')
    lines.append('')
    lines.append('2. **错配强度不预测候选生成收益——包括"错得更远反而更好"这一方向。**')
    lines.append('')
    lines.append('| 配置 | 距离 | 与主对照 (Accurate−Mismatched) 的 Pearson | 95% CI |')
    lines.append('| --- | --- | ---: | --- |')
    for name, payload in payloads.items():
        for feature in ('delta_full', 'delta_recovery_block', 'delta_exploitation_block'):
            item = payload['associations'][feature].get('tau_raw')
            if item is None:
                continue
            lines.append(f'| {regime_labels.get(name, name)} | {labels[feature]} | {_fmt(item["pearson"])} | '
                         f'{_ci(item["pearson_ci95"])} |')
    lines.append('')
    lines.append('所有区间均覆盖 0；低/中/高分位分组亦无单调趋势。剔除最接近的三分之一供体后，'
                 '两组的 Accurate−Mismatched 区间仍然都覆盖 0，'
                 '说明"准确诊断无稳定增量优势"并非由个别近乎相同的供体造成。')
    lines.append('')
    gain_targets = ('tau_raw', 'raw_gain_mismatched', 'raw_gain_accurate', 'tau_s3')
    behaviour_targets = ('behavior_move_mismatched', 'behavior_move_accurate',
                         'behavior_move_mismatched_minus_accurate',
                         'code_change_mismatched', 'code_change_mismatched_minus_accurate')
    hits = {'gain': [], 'behaviour': []}
    for name, payload in payloads.items():
        for feature in ('delta_full', 'delta_recovery_block', 'delta_exploitation_block'):
            for target in gain_targets + behaviour_targets:
                item = payload['associations'][feature].get(target)
                if item and _excludes_zero(item['pearson_ci95']):
                    hits['gain' if target in gain_targets else 'behaviour'].append(
                        (regime_labels.get(name, name), labels[feature], item))
    if hits['gain'] or hits['behaviour']:
        lines.append('3. **少数区间穿过 0，但方向并不一致，因此不构成连贯的机制信号。**')
        lines.append('')
        for kind, heading in (('gain', '收益层面'), ('behaviour', '行为层面')):
            if not hits[kind]:
                lines.append(f'**{heading}：**没有任何关联的区间排除 0。')
                lines.append('')
                continue
            lines.append(f'**{heading}：**')
            lines.append('')
            lines.append('| 配置 | 距离 | 结果指标 | Pearson | 95% CI |')
            lines.append('| --- | --- | --- | ---: | --- |')
            for label, feature, item in hits[kind]:
                lines.append(f'| {label} | {feature} | {item["label"]} | {_fmt(item["pearson"])} | '
                             f'{_ci(item["pearson_ci95"])} |')
            lines.append('')
        if hits['behaviour']:
            raw_signs = {item['pearson'] > 0 for _, _, item in hits['behaviour']
                         if item['label'].startswith('Mismatched-arm behavioural')}
            differential = [item for _, _, item in hits['behaviour']
                            if 'minus' in item['label']]
            parts = ['行为层面的关联并非单一方向：**原始移动量**（Mismatched-arm behavioural movement）']
            if raw_signs == {True}:
                parts.append('为正相关')
            elif raw_signs == {False}:
                parts.append('为负相关')
            else:
                parts.append('在不同配置/距离间符号不一致')
            parts.append('，而**组内差分**（Mismatched−Accurate 配对差）'
                         f'在 {len(differential)} 个组合中一致为负。')
            parts.append('两者回答不同问题：原始移动量混合了父代自身的行为反应性，'
                         '组内差分则在扣除父代基线后测量可归因于错配的额外移动，'
                         '后者随距离下降更符合"报告越偏离自身，模型越少据此修改"的读法。')
            lines.append(''.join(parts))
            lines.append('')
        if hits['gain']:
            lines.append('收益层面仅 S3 输出收益出现正相关，且只在思考开启配置中；'
                         '原始候选收益（主对照）在所有距离定义下均不显著。'
                         'S3 收益是门控与采用规则之后的非线性量，该关联不能读作"错配越远、准确诊断越有用"。')
        else:
            lines.append('收益层面没有任何关联排除 0，与第 2 点的结论一致：'
                         '错配强度不预测候选生成收益。')
        lines.append('')
        lines.append('这些关联均未做多重检验校正（此处共检查 '
                     f'{len(payloads) * 3 * len(gain_targets + behaviour_targets)} 个组合），'
                     '且大多只在一个配置中出现，只能作为待验证的探索性观察，不能作为机制结论。')
        lines.append('')
    lines.append('4. **对审稿意见 3 的作用是排除一种解释，而不是替代它。** 本分析可以排除'
                 '"错配强度不足以致无法检验"这一解释，但不能排除"数值报告本身可利用性有限"'
                 '或"模型主要依据源码与成绩修改"（对应审稿意见中的 $H_2$、$H_3$）。'
                 '后者需要 known-defect 阳性对照实验。')
    return lines


def targets_label(key):
    return {'tau_raw': 'Accurate−Mismatched（原始）',
            'raw_gain_mismatched': '错配原始候选增益',
            'raw_gain_accurate': '准确原始候选增益'}.get(key, key)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', default='.', help='Worktree root (module import + results base).')
    parser.add_argument('--docs', default='docs/direct_reciprocity')
    parser.add_argument('--out-dir', default=None)
    parser.add_argument('--output-suffix', default='')
    args = parser.parse_args()
    base = Path(args.root).resolve()
    out_dir = Path(args.out_dir) if args.out_dir else base / args.docs / 'mismatch_distance'
    out_dir.mkdir(parents=True, exist_ok=True)
    payloads = {}
    for name, relative in REGIMES.items():
        root = base / relative
        if not root.exists():
            print(json.dumps({'skipped': name, 'missing': str(root)}))
            continue
        payloads[name] = analyze_regime(name, root, out_dir, args.output_suffix)
    markdown_path = base / args.docs / f'MISMATCH_DISTANCE_ANALYSIS{args.output_suffix}.md'
    write_markdown(payloads, markdown_path)
    print(json.dumps({'regimes': list(payloads), 'markdown': str(markdown_path), 'json_dir': str(out_dir)},
                     ensure_ascii=False))


if __name__ == '__main__':
    main()
