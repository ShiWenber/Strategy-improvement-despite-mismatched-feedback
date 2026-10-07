#!/bin/sh
# Run the full API experiment and its analyses through the existing uv entry points.
set -eu

with_score=false
if [ "${1:-}" = "--with-score" ]; then
    with_score=true
    shift
fi
if [ "$#" -gt 1 ]; then
    printf 'Usage: %s [--with-score] [workspace]\n' "$0" >&2
    exit 2
fi

cd "$(dirname "$0")/../.."
workspace=${1:-results/api_reproduct}
if [ "$with_score" = true ]; then
    workspace=${1:-results/api_reproduct_score}
fi
off_dir="$workspace/results/feedback_specificity_v2"
on_dir="$workspace/results/feedback_specificity_thinking_384k_20260923"
qwen_dir="$workspace/results/qwen3_8"
population_dir="$workspace/results/reciprocity_population_visuals_20260924"
comparison_dir="$workspace/results/model_comparison_20260928"

# DeepSeek OFF: new populations, parents and candidate responses.
if [ "$with_score" = true ]; then
    uv run python -m experiments.direct_reciprocity.specificity freeze --output "$off_dir" --arms accurate mismatched score
else
    uv run python -m experiments.direct_reciprocity.specificity freeze --output "$off_dir" --arms accurate mismatched
fi
uv run python -m experiments.direct_reciprocity.specificity all --output "$off_dir" --workers 12 --api-workers 8 --env-file .env
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
