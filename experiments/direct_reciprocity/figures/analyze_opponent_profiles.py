"""Explore opponent-family payoffs from frozen H records, without new games.

Output: results/figure4_opponent_profiles_20260926/ANALYSIS.json.
The original population is the aggregation and bootstrap unit. These are
descriptive, post hoc comparisons, not new confirmatory hypothesis tests.
"""
from collections import defaultdict
import argparse
import json
from pathlib import Path
from ..records import read_json
from statistics import mean

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
FAMILIES = ["recovery", "exploitation", "random", "memory"]
ARMS = ["accurate", "mismatched"]
STAGES = ["raw", "S3"]
BOOTSTRAP_SEED = 2026092604
N_BOOTSTRAP = 20000


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, default=ROOT)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    work = args.work.resolve()
    runs = [('non_thinking', 'feedback_specificity_v2'),
            ('thinking', 'feedback_specificity_thinking_384k_20260923')]
    manifests = {mode: read_json(work / 'results' / run / 'manifest.json') for mode, run in runs}
    seeds = manifests[runs[0][0]]['seeds']
    if not seeds or any(manifest['seeds'] != seeds for manifest in manifests.values()):
        raise ValueError('Opponent profiles require matching nonempty population seed orders')
    indices = np.random.default_rng(BOOTSTRAP_SEED).integers(
        0, len(seeds), size=(N_BOOTSTRAP, len(seeds))
    )

    def summarize(values):
        values = np.asarray(values, dtype=float)
        if len(values) != len(seeds) or not np.isfinite(values).all():
            raise ValueError('Opponent profiles require one finite value per population')
        return {
            "mean": float(values.mean()),
            "seed_values": values.tolist(),
            "ci95_exploratory_unadjusted": np.quantile(
                values[indices].mean(axis=1), [.025, .975]
            ).tolist(),
            "positive_populations": int(np.sum(values > 1e-12)),
            "negative_populations": int(np.sum(values < -1e-12)),
            "zero_populations": int(np.sum(abs(values) <= 1e-12)),
        }

    result = {
        "status": "complete",
        "analysis_status": "post_hoc_exploratory",
        "purpose": "Assess whether similar overall Accurate and Mismatched payoff gains mask opponent-family heterogeneity.",
        "no_new_games_or_model_calls": True,
        "independent_unit": "original population",
        "n_independent_populations": len(seeds),
        "seeds": seeds,
        "families": FAMILIES,
        "family_weights": {family: 1 / len(FAMILIES) for family in FAMILIES},
        "arms": ARMS,
        "bootstrap": {
            "resamples": N_BOOTSTRAP,
            "seed": BOOTSTRAP_SEED,
            "method": "population resampling with replacement; percentile intervals",
            "intervals": "unadjusted descriptive intervals; not simultaneous intervals or confirmatory significance tests",
        },
        "aggregation": {
            "raw": "Average candidate outputs within each parent, parents within each population, then give each population equal weight.",
            "S3": "Use the sealed S3 winner or retain the parent; average parents within populations and weight populations equally.",
            "family": "Default H has equally weighted opponents and balanced families. Values are payoff per round.",
            "fallback": "Use deployed.default, which substitutes the parent entire default record for invalid candidates or execution failure in default H. Keep these generation outputs in the summaries.",
        },
        "limits": [
            "Exploratory disaggregation of the same H records used by existing outcome analyses; not an independent replication.",
            "A family-specific contrast is not a causal mechanism or proof that the model repaired a particular behavioural deficit.",
            "No identified aggregate advantage is not equivalence, and an exploratory family pattern is not a confirmed matching benefit.",
            "OFF and ON comparisons are descriptive.",
            "The independent sampling unit is population; parents, candidates and opponents are not independent experimental replications.",
        ],
        "configs": {},
    }
    for mode, run in runs:
        source = work / "results" / run
        manifest = read_json(source / "manifest.json")
        sealed = read_json(source / "SELECTIONS_SEALED.json")
        selection = {
            (row["context"], row["arm"]): row
            for row in sealed["rows"] if row["rule"] == "S3"
        }
        grouped = defaultdict(list)
        for job in manifest["jobs"]:
            if job["arm"] in ARMS:
                grouped[job["context"], job["arm"]].append(job)
        if len(grouped) != len(manifest['seeds']) * len(manifest['ranks']) * len(ARMS):
            raise ValueError('Opponent profiles require all parent and condition pools')
        rows = []
        failures = {arm: 0 for arm in ARMS}
        for (context, arm), jobs in sorted(grouped.items()):
            if len(jobs) != manifest['draws']:
                raise ValueError('Opponent profile candidate pool differs from the manifest draw count')
            parent = read_json(source / "holdout" / (context + ".json"))["measured"]["default"]
            children = {
                job["id"]: read_json(source / "holdout" / (job["id"] + ".json"))
                for job in jobs
            }
            winner = selection[context, arm]["winner"]
            deployed = [child["deployed"]["default"] for child in children.values()]
            selected = children[winner]["deployed"]["default"] if winner else parent
            fallback_count = sum(child["fallback"]["default"] for child in children.values())
            failures[arm] += fallback_count
            levels = {
                "parent": parent["families"],
                "raw": {family: mean(c["families"][family] for c in deployed) for family in FAMILIES},
                "S3": selected["families"],
            }
            overall = {
                "parent": parent["score"],
                "raw": mean(c["score"] for c in deployed),
                "S3": selected["score"],
            }
            for stage in levels:
                if set(levels[stage]) != set(FAMILIES):
                    raise ValueError('Opponent profiles require all opponent families')
            rows.append({
                "context": context, "seed": jobs[0]["seed"], "arm": arm,
                "winner": winner, "default_H_fallback_slots": fallback_count,
                "family_levels": levels,
                "family_gains": {
                    stage: {family: levels[stage][family] - levels["parent"][family] for family in FAMILIES}
                    for stage in STAGES
                },
                "overall_gains": {stage: overall[stage] - overall["parent"] for stage in STAGES},
            })
        summaries, contrasts = {}, {}
        for stage in STAGES:
            summaries[stage] = {}
            for arm in ARMS:
                summaries[stage][arm] = {}
                subset = [row for row in rows if row["arm"] == arm]
                if any(sum(row['seed'] == seed for row in subset) != len(manifest['ranks']) for seed in seeds):
                    raise ValueError('Opponent profiles require all parents within each population')
                for family in FAMILIES:
                    values = [
                        mean(row["family_gains"][stage][family] for row in subset if row["seed"] == seed)
                        for seed in seeds
                    ]
                    summaries[stage][arm][family] = summarize(values)
                values = [
                    mean(row["overall_gains"][stage] for row in subset if row["seed"] == seed)
                    for seed in seeds
                ]
                summaries[stage][arm]["overall"] = summarize(values)
            contrasts[stage] = {}
            for family in FAMILIES + ["overall"]:
                values = (
                    np.array(summaries[stage]["accurate"][family]["seed_values"])
                    - np.array(summaries[stage]["mismatched"][family]["seed_values"])
                )
                contrasts[stage][family] = summarize(values)
        result["configs"][mode] = {
            "source_root": source.relative_to(work).as_posix(),
            "source_files": ["manifest.json", "SELECTIONS_SEALED.json", "holdout/<context>.json", "holdout/<candidate_id>.json"],
            "n_parents": len({row['context'] for row in rows}),
            "n_pools_included": len(rows), "n_raw_slots_included": sum(len(jobs) for jobs in grouped.values()),
            "default_H_fallback_slots_by_arm": failures,
            "n_S3_retained_parent_by_arm": {
                arm: sum(row["winner"] is None for row in rows if row["arm"] == arm) for arm in ARMS
            },
            "summaries": summaries,
            "paired_accurate_minus_mismatched": contrasts,
            "pool_rows": rows,
        }
    destination = args.output or work / "results/figure4_opponent_profiles_20260926/ANALYSIS.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {destination}")


if __name__ == "__main__":
    main()
