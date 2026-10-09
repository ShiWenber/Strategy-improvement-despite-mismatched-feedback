#!/usr/bin/env bash
WORK="results/api_reproduct"
OUT="$WORK/figures"

mkdir -p "$OUT"

# 1. 重新生成 DeepSeek OFF 的主分析
uv run python -m experiments.direct_reciprocity.specificity_analysis \
  "$WORK/results/feedback_specificity_v2" \
  --output-suffix _reproduct

# 2. 重新生成角色分析
uv run python -m experiments.direct_reciprocity.role_analysis \
  "$WORK/results/feedback_specificity_v2" \
  --analysis-file ANALYSIS_reproduct.json \
  --output-suffix _reproduct

# 3. 如果其它配置已经存在，生成对应分析
if [ -d "$WORK/results/feedback_specificity_thinking_384k_20260923" ]; then
  uv run python -m experiments.direct_reciprocity.thinking_control_analysis \
    "$WORK/results/feedback_specificity_thinking_384k_20260923" \
    --source "$WORK/results/feedback_specificity_v2" \
    --source-analysis ANALYSIS_reproduct.json \
    --output-suffix _reproduct
fi

if [ -d "$WORK/results/qwen3_8" ]; then
  uv run python -m experiments.direct_reciprocity.qwen_analysis \
    --root "$WORK/results/qwen3_8" \
    --source "$WORK/results/feedback_specificity_v2" \
    --output-suffix _reproduct
fi

# 4. 生成跨模型汇总
if [ -d "$WORK/results/feedback_specificity_thinking_384k_20260923" ] \
   && [ -d "$WORK/results/qwen3_8" ]; then
  uv run python -m experiments.direct_reciprocity.cross_model_summary \
    --work "$WORK" \
    --analysis-suffix _reproduct \
    --output "$WORK/results/model_comparison/cross_model_mainline_data_reproduct.json" \
    --csv-dir "$WORK/results/model_comparison" \
    --output-suffix _reproduct
fi

# 5. 生成图片
uv run python -m experiments.direct_reciprocity.figures.plot_results_three_figures \
  --analysis-suffix _reproduct \
  --output-dir "$OUT"

uv run python -m experiments.direct_reciprocity.figures.plot_camera_ready \
  --analysis-suffix _reproduct \
  --figures 3 4 5 \
  --output-dir "$OUT"

# 6. 如果 opponent profile 分析已经存在，生成 Figure S4
if [ -f "$WORK/results/figure4_opponent_profiles_20260926/ANALYSIS_reproduct.json" ]; then
  uv run python -m experiments.direct_reciprocity.figures.plot_opponent_profiles \
    --input "$WORK/results/figure4_opponent_profiles_20260926/ANALYSIS_reproduct.json" \
    --output-dir "$OUT" \
    --audit-dir "$OUT/audit"
fi

echo
echo "Generated figures:"
find "$OUT" -maxdepth 1 -type f \
  \( -name '*.png' -o -name '*.pdf' -o -name '*.svg' \) \
  -print | sort
