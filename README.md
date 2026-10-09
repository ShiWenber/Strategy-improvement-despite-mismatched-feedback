# Strategy improvement despite mismatched feedback

This repository accompanies *Strategy improvement despite mismatched feedback: evolving direct reciprocity with large language models*. The project repository is [ShiWenber/Strategy-improvement-despite-mismatched-feedback](https://github.com/ShiWenber/Strategy-improvement-despite-mismatched-feedback).

The paper compares **Accurate** and **Mismatched** reports, with **Score** as a baseline, while holding the parent strategy, population code, game rules and genuine training scores fixed. Accurate supplies the parent's own numerical behavioural report; Mismatched supplies another strategy's report from the same population. Candidate quality before selection is evaluated separately from the quality of externally selected outputs.

## Run with uv

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) and Git, then run these commands from the project root:

```sh
git clone https://github.com/ShiWenber/Strategy-improvement-despite-mismatched-feedback.git
cd Strategy-improvement-despite-mismatched-feedback
uv sync
```

The analysis and figure/table commands below use recorded responses and cached labels, with **no LLM API calls**. Run them in order from the project root.

## Paper data and file structure

The data cover DeepSeek and Qwen in OFF/ON configurations, with **Score**, **Accurate** and **Mismatched** in each configuration. Score retains the population code, parent strategy, game rules and genuine cumulative training scores, with an empty behavioural-report block. Accurate versus Mismatched remains the prespecified matching comparison; comparisons with Score are exploratory supplementary evidence.

Each model/configuration uses the same 20 populations and 60 parents, with two candidates per parent and condition: **360 candidates, 180 two-candidate pools and 540 S1/S2/S3 decisions** across the three conditions. The four configurations contain 1,440 candidate responses (960 matching-condition candidates and 480 Score candidates) and share the 240 DeepSeek OFF initialization responses. Mainline pooled summaries and figures explicitly use Accurate and Mismatched only: 240 candidates, 120 pools and 360 decisions per configuration. Additional models or configurations do not increase the number of independent populations.

| Model/configuration | Data directory | Request settings |
| --- | --- | --- |
| DeepSeek OFF | `results/feedback_specificity_v2/` | `deepseek-flash`; temperature=1; thinking disabled; max_tokens=6000 |
| DeepSeek ON | `results/feedback_specificity_thinking_384k_20260923/` | Same API identifier; thinking enabled; reasoning_effort=high; max_tokens=384000 |
| Qwen OFF | `results/qwen3_8/off/` | `qwen3.8-flash`; temperature=1; enable_thinking=false; max_tokens=6000 |
| Qwen ON | `results/qwen3_8/on/` | Same model; enable_thinking=true; reasoning_effort=high; max_tokens=131072 |

The paper names the DeepSeek model deepseek-v4.1-flash; recorded requests use the API identifier `deepseek-flash`. API aliases do not guarantee fixed model weights over time. OFF/ON differ in thinking settings, output budgets and collection times, so configuration differences do not isolate the thinking switch. Qwen is a follow-up model test using the same parents and evaluation panels.

`experiments/direct_reciprocity/` contains all experiment code, including API generation, evaluation, record checks, analyses and figure/table exports. Reproduction runs these same entry points with explicit input and output parameters; `tools/` contains only the optional JSON-to-Markdown reader.

### Record types

Paths are relative to each experiment directory unless stated otherwise. ON and Qwen records use the shared parents.

| File/directory | Contents and use |
| --- | --- |
| `manifest.json` | Population seeds, parent ranks, report conditions, candidate tasks and request settings |
| `requests_initial/`, `initial/` | 240 initialization requests/responses and validated strategies, stored in DeepSeek OFF |
| `populations/s200.json` ... `s219.json` | 12 strategies per population, training scores, feedback measurements and donor permutations without fixed points |
| `contexts/s200-rank1.json` and related files | 60 shared parents, donors and complete prompts for all three conditions |
| `requests_candidates/<id>.json` | API parameters, responses and usage; ON also includes visible reasoning |
| `candidates/<id>.json` | Candidate programs |
| `selection_scores/<id>.json` | Parent/candidate scores for S1, S2 and S3, independent of test outcomes |
| `SELECTIONS_SEALED.json` | 540 sealed decisions selecting a candidate or retaining the parent |
| `holdout/<id>.json` | Payoff and independent behaviour measurements and gains over parents |
| `ANALYSIS.json`, `AUDIT.json` | Reference analysis summaries |
| `arm_logs/score.jsonl`, `arm_logs/accurate.jsonl`, `arm_logs/mismatched.jsonl` | One consolidated data log per condition and model/configuration: task identity, complete request/response, usage, candidate validity, selection scores and holdout data |

## Reproduce each analysis

`--output-suffix _reproduct` appends the suffix to generated filenames beside the paper data; `--analysis-suffix` or `--analysis-file` selects these outputs as downstream inputs. The table maps each command, in order, to its analysis and outputs.

```sh
uv run python -m experiments.direct_reciprocity.specificity_analysis results/feedback_specificity_v2 --output-suffix _reproduct
uv run python -m experiments.direct_reciprocity.thinking_control_analysis results/feedback_specificity_thinking_384k_20260923 --source results/feedback_specificity_v2 --source-analysis ANALYSIS_reproduct.json --output-suffix _reproduct
uv run python -m experiments.direct_reciprocity.qwen_analysis --root results/qwen3_8 --source results/feedback_specificity_v2 --output-suffix _reproduct
uv run python -m experiments.direct_reciprocity.role_analysis results/feedback_specificity_v2 --analysis-file ANALYSIS_reproduct.json --output-suffix _reproduct
uv run python -m experiments.direct_reciprocity.analyze_population --analysis-suffix _reproduct --output results/reciprocity_population_visuals_20260924/population_summary_reproduct.json
uv run python -m experiments.direct_reciprocity.figures.analyze_opponent_profiles --analysis-suffix _reproduct --output results/figure4_opponent_profiles_20260926/ANALYSIS_reproduct.json
uv run python -m experiments.direct_reciprocity.figures.plot_behavior_evidence --analysis-suffix _reproduct --output results/reciprocity_population_visuals_20260924/behavior/ANALYSIS_reproduct.json
uv run python -m experiments.direct_reciprocity.mismatch_distance --root . --output-suffix _reproduct
uv run python -m experiments.direct_reciprocity.cross_model_summary --analysis-suffix _reproduct --output results/model_comparison_20260928/cross_model_mainline_data_reproduct.json --csv-dir results/model_comparison_20260928 --output-suffix _reproduct
uv run python -m experiments.direct_reciprocity.judge_mismatch_detection_summary report --judgments-dir results/mismatch_detection_jev/judgments --threshold 0.40 --confidence 0.60 --output-json results/mismatch_detection_jev/jev_recount_reproduct.json
```

| Step / analysis | Inputs and outputs |
| --- | --- |
| 1. OFF matching, Raw/S1/S2/S3 and sensitivity | OFF requests, sealed decisions and holdout (H) -> `ANALYSIS_reproduct.json`, `AUDIT_reproduct.json` |
| 2. ON statistics and paired OFF/ON differences | Shared-parent OFF/ON H -> ON `ANALYSIS_reproduct.json` |
| 3. Qwen comparisons | Qwen requests and H -> per-mode and combined `ANALYSIS_reproduct.json` |
| 4. Fixed-pool N/G/U/B policies | Selection scores and H -> `role_analysis/ANALYSIS_reproduct.json` |
| 5. Candidate distributions and selection | DeepSeek OFF/ON candidates and S3 decisions -> `population_summary_reproduct.json` |
| 6. Opponent-family payoffs | Per-opponent H -> `figure4_opponent_profiles_20260926/ANALYSIS_reproduct.json` |
| 7. Independent behavioural stages | F′ measurements and S3 decisions -> `behavior/ANALYSIS_reproduct.json` |
| 8. Mismatch distances and sensitivity | F reports, parent/donor pairs and candidate H -> `docs/direct_reciprocity/mismatch_distance/` |
| 9. Cross-model summary | Four configurations and paired population vectors -> CSV/JSON in `results/model_comparison_20260928/` |
| 10. Visible-reasoning labels | Cached judgments -> JSON in `results/mismatch_detection_jev/` |

Step 9 exports the matching-comparison `cross_model_mainline_data_reproduct.json`, plus three-condition `candidate_gains_reproduct.csv`, `population_gains_reproduct.csv` and `condition_statistics_reproduct.csv`. It also exports `score_baseline_data_reproduct.json`, `score_baseline_statistics_reproduct.csv` and `score_baseline_population_pairs_reproduct.csv`. These contain Raw and S3 Accurate-minus-Score and Mismatched-minus-Score estimates paired within each of the 20 populations. Intervals are unadjusted population bootstrap intervals; no new confirmatory tests are introduced. Invalid candidates and evaluation failures retain the parent, with zero deployed gain, and are reported in the Score summary. Step 10 exports `jev_recount_reproduct.json` for Accurate and Mismatched.

Report-versus-Score contrasts compare adding a report, whereas Accurate versus Mismatched compares report attribution.

For an optional readable view of any analysis JSON, use the renderer below. It preserves stored values without running experiments or statistics, and writes Markdown beside the input with the same stem; `--output` selects another destination. The existing [distance narrative](docs/direct_reciprocity/MISMATCH_DISTANCE_ANALYSIS.md) and [Jev detail report](results/mismatch_detection_jev/REPORT.md) are retained as reference documents.

```sh
uv run python tools/render_report.py results/feedback_specificity_v2/ANALYSIS_reproduct.json
```

## Reproduce the figures and tables

Open the PNG links below; figure PDF/SVG versions share the same stems. `reproduct/` is a flat directory of viewable figures.

The API reproduction plotting entry point keeps every input and output path in
one shell script. It never falls back to the repository's historical
`results/` directories:

```sh
# Read the original data under ./results
bash experiments/direct_reciprocity/plot.sh --work .

# Read the API reproduction data under results/api_reproduct/results
bash experiments/direct_reciprocity/plot.sh results/api_reproduct
```

| Paper item | Reproduction output | Command / evidence |
| --- | --- | --- |
| Figure 1 | [figure1.png](assets/figure1.png) · [PDF](assets/figure1.pdf) | Method schematic; editable source in `assets/figure1_editable.pptx` |
| Figure 2 | [fig2.png](reproduct/fig2.png) | 1; cross-model matching and paired population Raw/S3 gains |
| Figure 3 | [fig3.png](reproduct/fig3.png) | 1; opponent-family payoffs and independent behaviour |
| Figure S1 | [figS1.png](reproduct/figS1.png) | 2 (`--figures 3`); both conditions, three selectors and OFF/ON |
| Figure S2 | [figS2.png](reproduct/figS2.png) | 3; candidate histograms and Gaussian KDE with Scott's bandwidth |
| Figure S3 | [figS3.png](reproduct/figS3.png) | 2 (`--figures 5`); fixed-pool policies and decomposition |
| Figure S4 | [figS4.png](reproduct/figS4.png) | 4; four opponent-family payoffs for Raw/S3 |
| Figure S5 | [figS5.png](reproduct/figS5.png) | 2 (`--figures 4`); independent behavioural differences for OFF |
| Figure S6 | [figS6.png](reproduct/figS6.png) | 5; shared parent-donor distances |
| Table S1 | `tableS1_probe_parameters_reproduct.csv/.tex` | 6; fixed F′ probe parameters |
| Table S2 | `tableS2_primary_reproduct.csv/.tex` | 6; prespecified Raw matching comparison |
| Table S3 | `tableS3_sensitivity_reproduct.csv/.tex` | 6; OFF noise and longer-match checks |
| Table S4 | `tableS4_selection_reproduct.csv/.tex` | 6; S3-minus-N noise and longer-match checks |
| Table S5 | `tableS5_distance_reproduct.csv/.tex` | 6; matching differences after excluding closest donors |
| Table S6 | `tableS6_score_baseline_reproduct.csv/.tex` | 6; exploratory Raw Accurate-minus-Score and Mismatched-minus-Score, four configurations |
| Table S7 | `tableS7_score_failures_reproduct.csv/.tex` | 6; invalid Score candidates and parent fallbacks by evaluation setting |

Command numbers refer to the block above. Main Tables I–II define the report conditions and S1/S2/S3 scoring; they contain fixed protocol definitions.

## Optional new API generation

Copy `.env.example` to `.env` and configure `DEEPSEEK_API_KEY`, `DEEPSEEK_API_BASE`, `QWEN_API_KEY` and `QWEN_API_BASE`, then run:

```sh
sh experiments/direct_reciprocity/generate_api.sh
```

Every configuration includes **Score, Accurate and Mismatched by default**. These information conditions are frozen experiment hyperparameters, recorded in `manifest.json` under `arms` and shared by DeepSeek OFF/ON and Qwen OFF/ON.

The run makes **1,680 planned API calls**: 240 initialization calls and 1,440 candidate calls. ON and Qwen reuse the new OFF parents and prompts. The script then runs the analyses and exports JSON, CSV and tables with `_reproduct` summary filenames.

Outputs stay in `results/api_reproduct/`. To collect independent samples, supply an empty workspace, for example `sh experiments/direct_reciprocity/generate_api.sh results/api_reproduct_new`. Re-running the same workspace resumes from recorded responses. New programs and results may differ from the published run.

Within **each model/configuration**, all **Score** requests finish before **Accurate**, followed by **Mismatched**. `--api-workers` controls concurrency within a condition; an API error prevents later conditions from starting. Parent and draw order is shared across conditions and shuffled within each batch. The manifest records `generation_order`. This fixed condition order differs from the historical randomized collection; historical IDs and collection records remain intact.

Each condition has one `arm_logs/<arm>.jsonl` file, refreshed after generation, selection and holdout. It contains one row per frozen task, including pending or failed requests. Per-request JSON and stream files remain the originals used by analyses; uncertain requests are never retried automatically.

Rebuild condition logs from existing records at any time, without API calls or changing recorded data:

```sh
uv run python -m experiments.direct_reciprocity.condition_generation --roots results/feedback_specificity_v2 results/feedback_specificity_thinking_384k_20260923 results/qwen3_8/off results/qwen3_8/on
```
