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
from .records import read_json, write_json
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
    regimes = []
    for name, relative in REGIMES.items():
        root = base / relative
        if not root.exists():
            print(json.dumps({'skipped': name, 'missing': str(root)}))
            continue
        analyze_regime(name, root, out_dir, args.output_suffix)
        regimes.append(name)
    print(json.dumps({'regimes': regimes, 'json_dir': str(out_dir)},
                     ensure_ascii=False))


if __name__ == '__main__':
    main()
