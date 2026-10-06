"""Explore opponent-family payoffs from frozen H records, without new games.

Output: results/figure4_opponent_profiles_20260926/ANALYSIS.json.
The original population is the aggregation and bootstrap unit. These are
descriptive, post hoc comparisons, not new confirmatory hypothesis tests.
"""
from collections import defaultdict
import argparse
import json
from pathlib import Path
from statistics import mean

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
FAMILIES = ["recovery", "exploitation", "random", "memory"]
ARMS = ["accurate", "mismatched"]
SEEDS = list(range(200, 220))
STAGES = ["raw", "S3"]
BOOTSTRAP_SEED = 2026092604
N_BOOTSTRAP = 20000


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, default=ROOT)
    parser.add_argument('--analysis-suffix', default='')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    work = args.work.resolve()
    indices = np.random.default_rng(BOOTSTRAP_SEED).integers(
        0, len(SEEDS), size=(N_BOOTSTRAP, len(SEEDS))
    )

    def summarize(values):
        values = np.asarray(values, dtype=float)
        assert len(values) == len(SEEDS)
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
        "n_independent_populations": len(SEEDS),
        "seeds": SEEDS,
        "families": FAMILIES,
        "family_weights": {family: .25 for family in FAMILIES},
        "arms": ARMS,
        "bootstrap": {
            "resamples": N_BOOTSTRAP,
            "seed": BOOTSTRAP_SEED,
            "method": "population resampling with replacement; percentile intervals",
            "intervals": "unadjusted descriptive intervals; not simultaneous intervals or confirmatory significance tests",
        },
        "aggregation": {
            "raw": "For each arm, average two pre-generated candidate outputs within each parent, then equally average three parents per population, then 20 populations.",
            "S3": "Use frozen S3 winner per parent and arm, or parent if no winner; equally average three parents per population, then 20 populations.",
            "family": "Default H: three equally weighted opponents per family. Each family has weight 1/4 in overall H payoff. All values are payoff per round.",
            "fallback": "Use deployed.default, which substitutes the parent entire default record for invalid candidates or execution failure in default H. Keep these generation outputs in the summaries.",
        },
        "limits": [
            "Exploratory disaggregation of the same H records used by existing outcome analyses; not an independent replication.",
            "A family-specific contrast is not a causal mechanism or proof that the model repaired a particular behavioural deficit.",
            "No identified aggregate advantage is not equivalence, and an exploratory family pattern is not a confirmed matching benefit.",
            "OFF and ON comparisons are descriptive.",
            "The independent sampling unit is population; 60 parents, 120 candidates, and 12 opponents are not independent experimental replications.",
        ],
        "configs": {},
    }
    for mode, run in [
        ("non_thinking", "feedback_specificity_v2"),
        ("thinking", "feedback_specificity_thinking_384k_20260923"),
    ]:
        source = work / "results" / run
        manifest = read(source / "manifest.json")
        sealed = read(source / "SELECTIONS_SEALED.json")
        frozen = read(source / f"ANALYSIS{args.analysis_suffix}.json")
        expected = frozen["thinking"] if mode == "thinking" else frozen
        selection = {
            (row["context"], row["arm"]): row
            for row in sealed["rows"] if row["rule"] == "S3"
        }
        grouped = defaultdict(list)
        for job in manifest["jobs"]:
            if job["arm"] in ARMS:
                grouped[job["context"], job["arm"]].append(job)
        assert len(grouped) == 120
        rows = []
        failures = {arm: 0 for arm in ARMS}
        max_family_error = 0.0
        for (context, arm), jobs in sorted(grouped.items()):
            assert len(jobs) == 2
            parent = read(source / "holdout" / (context + ".json"))["measured"]["default"]
            children = {
                job["id"]: read(source / "holdout" / (job["id"] + ".json"))
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
                assert set(levels[stage]) == set(FAMILIES)
                error = abs(mean(levels[stage].values()) - overall[stage])
                max_family_error = max(max_family_error, error)
                assert error < 1e-12
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
        summaries, contrasts, validation = {}, {}, []
        for stage in STAGES:
            summaries[stage] = {}
            for arm in ARMS:
                summaries[stage][arm] = {}
                subset = [row for row in rows if row["arm"] == arm]
                assert len(subset) == 60
                assert all(sum(row["seed"] == seed for row in subset) == 3 for seed in SEEDS)
                for family in FAMILIES:
                    values = [
                        mean(row["family_gains"][stage][family] for row in subset if row["seed"] == seed)
                        for seed in SEEDS
                    ]
                    summaries[stage][arm][family] = summarize(values)
                values = [
                    mean(row["overall_gains"][stage] for row in subset if row["seed"] == seed)
                    for seed in SEEDS
                ]
                summaries[stage][arm]["overall"] = summarize(values)
                reference = (
                    expected["raw"][arm]["metrics"]["default/score"]["seed_values"]
                    if stage == "raw" else
                    expected["selected"]["S3/" + arm]["metrics"]["default"]["seed_values"]
                )
                error = float(np.max(abs(np.array(values) - np.array(reference))))
                assert error < 1e-12
                family_mean = np.mean([
                    summaries[stage][arm][family]["seed_values"] for family in FAMILIES
                ], axis=0)
                family_error = float(np.max(abs(family_mean - np.array(values))))
                assert family_error < 1e-12
                validation.append({
                    "stage": stage, "arm": arm,
                    "max_abs_difference_vs_frozen_overall_seed_values": error,
                    "max_abs_difference_family_mean_vs_overall_seed_values": family_error,
                })
            contrasts[stage] = {}
            for family in FAMILIES + ["overall"]:
                values = (
                    np.array(summaries[stage]["accurate"][family]["seed_values"])
                    - np.array(summaries[stage]["mismatched"][family]["seed_values"])
                )
                contrasts[stage][family] = summarize(values)
        result["configs"][mode] = {
            "source_root": source.relative_to(work).as_posix(),
            "source_files": ["manifest.json", "SELECTIONS_SEALED.json", "ANALYSIS.json", "holdout/<context>.json", "holdout/<candidate_id>.json"],
            "n_parents": 60, "n_pools_included": 120, "n_raw_slots_included": 240,
            "default_H_fallback_slots_by_arm": failures,
            "n_S3_retained_parent_by_arm": {
                arm: sum(row["winner"] is None for row in rows if row["arm"] == arm) for arm in ARMS
            },
            "summaries": summaries,
            "paired_accurate_minus_mismatched": contrasts,
            "pool_rows": rows,
            "validation": {
                "all_passed": True,
                "max_abs_family_average_difference_per_parent_pool": max_family_error,
                "checks": validation,
            },
        }
    destination = args.output or work / "results/figure4_opponent_profiles_20260926/ANALYSIS.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {destination}; all aggregation checks passed.")


if __name__ == "__main__":
    main()
