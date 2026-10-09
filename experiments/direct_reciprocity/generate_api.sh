#!/bin/sh
# Run the full API experiment and its analyses through the existing uv entry points.
set -eu
set -f

usage() {
    printf 'Usage: %s [--arms "score accurate mismatched"] [workspace]\n' "$0" >&2
    exit 2
}

arms='score accurate mismatched'
if [ "${1:-}" = "--arms" ]; then
    [ "$#" -ge 2 ] || usage
    arms=$2
    shift 2
fi
[ "$#" -le 1 ] || usage
case "${1:-}" in --*) usage ;; esac

cd "$(dirname "$0")/../.."
workspace=${1:-results/api_reproduct}
off_dir="$workspace/results/feedback_specificity_v2"
on_dir="$workspace/results/feedback_specificity_thinking_384k_20260923"
qwen_dir="$workspace/results/qwen3_8"
population_dir="$workspace/results/reciprocity_population_visuals_20260924"
comparison_dir="$workspace/results/model_comparison_20260928"

# DeepSeek OFF: new populations, parents and candidate responses.
# Split the condition list into arguments; freeze validates it before API calls.
uv run python -m experiments.direct_reciprocity.specificity freeze --output "$off_dir" --arms $arms
uv run python -m experiments.direct_reciprocity.specificity all --output "$off_dir" --workers 48 --api-workers 20 --env-file .env
uv run python -m experiments.direct_reciprocity.specificity_analysis "$off_dir" --output-suffix _reproduct
uv run python -m experiments.direct_reciprocity.role_analysis "$off_dir" --analysis-file ANALYSIS_reproduct.json --output-suffix _reproduct

# DeepSeek ON: the same newly generated OFF parents and prompts.
uv run python -m experiments.direct_reciprocity.paired_control prepare --provider deepseek --output "$on_dir" --source "$off_dir" --env-file .env
uv run python -m experiments.direct_reciprocity.paired_control first --provider deepseek --output "$on_dir" --source "$off_dir" --env-file .env
uv run python -m experiments.direct_reciprocity.paired_control all --provider deepseek --output "$on_dir" --source "$off_dir" --workers 12 --api-workers 8 --env-file .env
uv run python -m experiments.direct_reciprocity.thinking_control_analysis "$on_dir" --source "$off_dir" --source-analysis ANALYSIS_reproduct.json --output-suffix _reproduct

# Qwen OFF/ON: shared OFF parents and prompts, separate responses.
for mode in off on; do
    uv run python -m experiments.direct_reciprocity.paired_control prepare --provider qwen --output "$qwen_dir/$mode" --source "$off_dir" --env-file .env
    uv run python -m experiments.direct_reciprocity.paired_control first --provider qwen --output "$qwen_dir/$mode" --source "$off_dir" --env-file .env
    uv run python -m experiments.direct_reciprocity.paired_control all --provider qwen --output "$qwen_dir/$mode" --source "$off_dir" --workers 12 --api-workers 8 --env-file .env
done
uv run python -m experiments.direct_reciprocity.qwen_analysis --root "$qwen_dir" --source "$off_dir" --output-suffix _reproduct

# Downstream summaries and tables from the new records.
uv run python -m experiments.direct_reciprocity.analyze_population --work "$workspace" --analysis-suffix _reproduct --output "$population_dir/population_summary_reproduct.json"
uv run python -m experiments.direct_reciprocity.figures.analyze_opponent_profiles --work "$workspace" --analysis-suffix _reproduct --output "$workspace/results/figure4_opponent_profiles_20260926/ANALYSIS_reproduct.json"
uv run python -m experiments.direct_reciprocity.figures.plot_behavior_evidence --work "$workspace" --analysis-suffix _reproduct --output "$population_dir/behavior/ANALYSIS_reproduct.json"
uv run python -m experiments.direct_reciprocity.mismatch_distance --root "$workspace" --output-suffix _reproduct
uv run python -m experiments.direct_reciprocity.cross_model_summary --work "$workspace" --analysis-suffix _reproduct --output "$comparison_dir/cross_model_mainline_data_reproduct.json" --csv-dir "$comparison_dir" --output-suffix _reproduct
uv run python -m experiments.direct_reciprocity.export_paper_tables --work "$workspace" --analysis-suffix _reproduct --output "$workspace/results/reproduction/tables" --output-suffix _reproduct
