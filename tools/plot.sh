#!/usr/bin/env bash
set -euo pipefail

if [[ $# -eq 1 ]]; then
  WORK_INPUT="$1"
elif [[ $# -eq 2 && "$1" == "--work" ]]; then
  WORK_INPUT="$2"
else
  printf 'Usage: %s [--work] WORK_DIRECTORY\n' "$0" >&2
  printf 'Example: %s --work results/api_reproduct\n' "$0" >&2
  exit 2
fi

REPO="$(git rev-parse --show-toplevel)"
if [[ ! -d "$WORK_INPUT" ]]; then
  printf 'Work directory does not exist: %s\n' "$WORK_INPUT" >&2
  exit 2
fi
WORK="$(realpath "$WORK_INPUT")"
DATA_ROOT="$WORK/results"
OUT="$WORK/figures"
AUDIT="$OUT/audit"

OFF="$DATA_ROOT/feedback_specificity_v2"
ON="$DATA_ROOT/feedback_specificity_thinking_384k_20260923"
QWEN="$DATA_ROOT/qwen3_8"

OFF_ANALYSIS="$OFF/ANALYSIS_reproduct.json"
OFF_ROLE="$OFF/role_analysis/ANALYSIS_reproduct.json"
ON_ANALYSIS="$ON/ANALYSIS_reproduct.json"
CROSS_MODEL="$DATA_ROOT/model_comparison/cross_model_mainline_data_reproduct.json"
OPPONENTS="$DATA_ROOT/figure4_opponent_profiles_20260926/ANALYSIS_reproduct.json"
BEHAVIOR="$DATA_ROOT/reciprocity_population_visuals_20260924/behavior/ANALYSIS_reproduct.json"
QWEN_OFF_MANIFEST="$QWEN/off/manifest.json"
QWEN_OFF_ANALYSIS="$QWEN/off/ANALYSIS_reproduct.json"
QWEN_ON_MANIFEST="$QWEN/on/manifest.json"
QWEN_ON_ANALYSIS="$QWEN/on/ANALYSIS_reproduct.json"

mkdir -p "$OUT" "$AUDIT"

uv run python -m experiments.direct_reciprocity.specificity_analysis \
  "$OFF" --output-suffix _reproduct

uv run python -m experiments.direct_reciprocity.role_analysis \
  "$OFF" --analysis-file ANALYSIS_reproduct.json --output-suffix _reproduct

uv run python -m experiments.direct_reciprocity.thinking_control_analysis \
  "$ON" --source "$OFF" --source-analysis ANALYSIS_reproduct.json \
  --output-suffix _reproduct

uv run python -m experiments.direct_reciprocity.qwen_analysis \
  --root "$QWEN" --source "$OFF" --output-suffix _reproduct

uv run python -m experiments.direct_reciprocity.cross_model_summary \
  --work "$WORK" --analysis-suffix _reproduct \
  --output "$CROSS_MODEL" --csv-dir "$DATA_ROOT/model_comparison" \
  --output-suffix _reproduct

uv run python -m experiments.direct_reciprocity.figures.plot_results_three_figures \
  --work "$REPO" --output-dir "$OUT" --audit-dir "$AUDIT" \
  --figure1 "$REPO/assets/figure1.png" \
  --cross-model "$CROSS_MODEL" \
  --deepseek-off "$OFF_ANALYSIS" --deepseek-on "$ON_ANALYSIS" \
  --qwen-off-manifest "$QWEN_OFF_MANIFEST" --qwen-off-analysis "$QWEN_OFF_ANALYSIS" \
  --qwen-on-manifest "$QWEN_ON_MANIFEST" --qwen-on-analysis "$QWEN_ON_ANALYSIS" \
  --opponent-profiles "$OPPONENTS" --behavior-analysis "$BEHAVIOR"

uv run python -m experiments.direct_reciprocity.figures.plot_camera_ready \
  --work "$REPO" --analysis-suffix _reproduct --figures 3 4 5 \
  --output-dir "$OUT" --audit-dir "$AUDIT" \
  --off-analysis "$OFF_ANALYSIS" --off-role-analysis "$OFF_ROLE" \
  --on-analysis "$ON_ANALYSIS"

uv run python -m experiments.direct_reciprocity.figures.plot_opponent_profiles \
  --input "$OPPONENTS" --output-dir "$OUT" --audit-dir "$AUDIT"
