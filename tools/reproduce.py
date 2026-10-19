"""Recompute archived paper results and export figures without model requests."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
PREFIX = "experiments.direct_reciprocity."
RUNS = (
    "feedback_specificity_v2",
    "feedback_specificity_thinking_384k_20260923",
    "qwen3_8/off",
    "qwen3_8/on",
)


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def commands(work, output, steps):
    off, on = [work / "results" / name for name in RUNS[:2]]
    qwen = work / "results/qwen3_8"
    population = work / "results/reciprocity_population_visuals_20260924"
    comparison = work / "results/model_comparison_20260928"
    opponents = work / "results/figure4_opponent_profiles_20260926/ANALYSIS_reproduct.json"
    behavior = population / "behavior/ANALYSIS_reproduct.json"
    distance = work / "docs/direct_reciprocity/mismatch_distance"
    figures = output / "figures"
    plan = []

    def add(name, module, *args):
        plan.append((name, [sys.executable, "-m", PREFIX + module, *map(str, args)]))

    if steps in ("all", "analysis"):
        add("01_deepseek_off", "specificity_analysis", off, "--output-suffix", "_reproduct")
        add("02_deepseek_on", "thinking_control_analysis", on, "--source", off,
            "--output-suffix", "_reproduct")
        add("03_qwen", "qwen_analysis", "--root", qwen, "--output-suffix", "_reproduct")
        add("04_policies", "role_analysis", off, "--output-suffix", "_reproduct")
        add("05_population", "analyze_population", "--work", work,
            "--output", population / "population_summary_reproduct.json")
        add("06_opponents", "figures.analyze_opponent_profiles", "--work", work,
            "--output", opponents)
        add("07_behavior", "figures.plot_behavior_evidence",
            "--off-root", off, "--on-root", on, "--output", behavior)
        add("08_distance", "mismatch_distance", "--root", work, "--output-suffix", "_reproduct")
        add("09_cross_model", "cross_model_summary", "--work", work,
            "--analysis-suffix", "_reproduct", "--output", comparison / "cross_model_mainline_data_reproduct.json",
            "--csv-dir", comparison, "--output-suffix", "_reproduct")
        if (work / "results/mismatch_detection_jev/judgments").is_dir():
            add("10_cached_labels", "judge_mismatch_detection_summary", "report",
                "--judgments-dir", work / "results/mismatch_detection_jev/judgments",
                "--threshold", "0.40", "--confidence", "0.60",
                "--output-json", output / "cached_labels.json")
        add("11_tables", "export_paper_tables", "--work", work, "--analysis-suffix", "_reproduct",
            "--output", output / "tables", "--output-suffix", "_reproduct", "--numbering", "manuscript")

    if steps in ("all", "figures"):
        add("12_main_figures", "figures.plot_results_three_figures",
            "--output-dir", figures,
            "--cross-model", comparison / "cross_model_mainline_data_reproduct.json",
            "--deepseek-off", off / "ANALYSIS_reproduct.json", "--deepseek-on", on / "ANALYSIS_reproduct.json",
            "--qwen-off-manifest", qwen / "off/manifest.json", "--qwen-off-analysis", qwen / "off/ANALYSIS_reproduct.json",
            "--qwen-on-manifest", qwen / "on/manifest.json", "--qwen-on-analysis", qwen / "on/ANALYSIS_reproduct.json",
            "--opponent-profiles", opponents, "--behavior-analysis", behavior)
        add("13_candidate_distribution", "figures.build_interface_figures",
            "--input", population / "population_summary_reproduct.json",
            "--display-output", output / "generation_display.json", "--output-dir", figures)
        add("14_selection", "figures.plot_camera_ready", "--figures", "3", "5",
            "--output-dir", figures, "--off-analysis", off / "ANALYSIS_reproduct.json",
            "--off-role-analysis", off / "role_analysis/ANALYSIS_reproduct.json", "--on-analysis", on / "ANALYSIS_reproduct.json")
        add("15_distance_figure", "figures.plot_mismatch_distance", "--inputs",
            distance / "mismatch_distance_thinking_off_reproduct.json",
            distance / "mismatch_distance_thinking_on_reproduct.json", "--output-dir", figures)
    return plan


def paper_input_paths(work):
    """Exact recorded inputs consumed by the current seven-figure workflow."""
    work = Path(work)
    paths = {work / f"assets/paper/figure1.{extension}" for extension in ("pdf", "png")}
    for run in RUNS:
        root = work / "results" / run
        manifest = read(root / "manifest.json")
        if set(manifest["arms"]) != {"score", "accurate", "mismatched"}:
            raise ValueError(f"Latest-paper reproduction requires all three conditions: {root}")
        if manifest['seeds'] != list(range(200, 220)) or len(manifest['jobs']) != 360:
            raise ValueError(f"Latest-paper reproduction requires the complete 20-population design: {root}")
        paths.update(root / name for name in ("manifest.json", "SELECTIONS_SEALED.json"))
        contexts = {job["context"] for job in manifest["jobs"]}
        paths.update(root / "holdout" / (identity + ".json")
                     for identity in contexts | {job["id"] for job in manifest["jobs"]})
        score_ids = {job["id"] for job in manifest["jobs"] if job["arm"] == "score"}
        if run == RUNS[0]:
            score_ids = contexts | {job["id"] for job in manifest["jobs"]}
        paths.update(root / "selection_scores" / (identity + ".json") for identity in score_ids)
        if run in RUNS[:2]:
            paths.update(root / "contexts" / (identity + ".json") for identity in contexts)
            paths.update(root / "populations" / f"s{seed}.json" for seed in manifest["seeds"])
            paths.update(root / "candidates" / (job["id"] + ".json") for job in manifest["jobs"]
                         if job["arm"] in ("accurate", "mismatched"))
    return paths


def paper_reference_paths(work):
    """Frozen paper graphics and full-precision statistical comparison targets."""
    work = Path(work)
    paths = {work / f"assets/paper/figure{number}.{extension}"
             for number in range(1, 8) for extension in ("pdf", "png", "svg")
             if number != 1 or extension != "svg"}
    names = [f"results/{run}/ANALYSIS.json" for run in RUNS]
    names += [
        "results/feedback_specificity_v2/role_analysis/ANALYSIS.json",
        "results/figure4_opponent_profiles_20260926/ANALYSIS.json",
        "results/reciprocity_population_visuals_20260924/behavior/ANALYSIS.json",
        "results/model_comparison_20260928/cross_model_mainline_data.json",
        "results/model_comparison_20260928/score_baseline_data.json",
        "results/qwen3_8/ANALYSIS.json",
    ]
    names += [f"docs/direct_reciprocity/mismatch_distance/mismatch_distance_thinking_{mode}.json"
              for mode in ("off", "on")]
    return paths | {work / name for name in names}


def preflight(work):
    for path in sorted(paper_input_paths(work)):
        if not path.is_file():
            raise FileNotFoundError(path)


def collect_figures(output):
    figures = output / "figures"
    mapping = {"figS2": "figure4", "figS1": "figure5", "figS3": "figure6", "figS6": "figure7",
               "fig2": "figure2", "fig3": "figure3"}
    for old, new in mapping.items():
        for extension in ("png", "pdf", "svg"):
            shutil.copy2(figures / f"{old}.{extension}", figures / f"{new}.{extension}")
    for extension in ("png", "pdf"):
        shutil.copy2(ROOT / f"assets/paper/figure1.{extension}", figures / f"figure1.{extension}")


def normalize_generated_outputs(work, output):
    # Use one newline convention for generated text exports on every platform.
    roots = [work / 'results' / name for name in RUNS]
    roots += [work / 'results' / name for name in ('qwen3_8', 'model_comparison_20260928',
              'reciprocity_population_visuals_20260924', 'figure4_opponent_profiles_20260926')]
    roots += [work / 'docs/direct_reciprocity/mismatch_distance', output / 'tables']
    for root in roots:
        for path in root.rglob('*_reproduct.*'):
            if path.is_file() and path.suffix in ('.json', '.csv', '.tex'):
                content = path.read_bytes()
                normalized = content.replace(b'\r\n', b'\n')
                if normalized != content:
                    path.write_bytes(normalized)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, default=ROOT, help="Directory containing results/ and docs/.")
    parser.add_argument("--output", type=Path, help="Default: WORK/results/reproduction/latest.")
    parser.add_argument("--steps", choices=("all", "analysis", "figures", "audit"), default="all")
    parser.add_argument("--dry-run", action="store_true", help="Print commands without writing outputs.")
    args = parser.parse_args()
    work = args.work.resolve()
    if args.steps == "audit":
        preflight(work)
        print("Archived input inventory passed.")
        return
    output = (args.output or work / "results/reproduction/latest").resolve()
    plan = commands(work, output, args.steps)
    if args.dry_run:
        for name, command in plan:
            print(name + ": " + subprocess.list2cmdline(command))
        return
    logs = output / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    report = {"status": "running", "requested_steps": args.steps,
              "steps": [], "live_api_calls": 0}
    environment = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8", MPLBACKEND="Agg")
    report_path = output / "RUN_REPORT.json"
    try:
        for index, (name, command) in enumerate(plan, 1):
            print(f"[{index}/{len(plan)}] {name}", flush=True)
            with (logs / f"{name}.log").open("w", encoding="utf-8") as handle:
                process = subprocess.run(command, cwd=ROOT, env=environment, stdout=handle, stderr=subprocess.STDOUT)
            report["steps"].append({"name": name, "command": command, "exit_code": process.returncode})
            if process.returncode:
                raise RuntimeError(f"{name} failed; see {logs / (name + '.log')}")
        if args.steps in ("all", "figures"):
            collect_figures(output)
        report["status"] = "passed"
    except Exception as exc:
        report.update(status="failed", error=str(exc))
        raise
    finally:
        normalize_generated_outputs(work, output)
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Complete: {output}", flush=True)


if __name__ == "__main__":
    main()
