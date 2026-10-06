# Strategy improvement despite mismatched feedback

This repository accompanies *Strategy improvement despite mismatched feedback: evolving direct reciprocity with large language models*. The project repository is [ShiWenber/Strategy-improvement-despite-mismatched-feedback](https://github.com/ShiWenber/Strategy-improvement-despite-mismatched-feedback).

The paper compares **Accurate** and **Mismatched** reports while holding the parent strategy, population code, game rules and genuine training scores fixed. Accurate supplies the parent's own numerical behavioural report; Mismatched supplies another strategy's report from the same population. Candidate quality before selection is evaluated separately from the quality of externally selected outputs.

## Reproduce with uv

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) and Git, then run these commands from the project root:

```sh
git clone https://github.com/ShiWenber/Strategy-improvement-despite-mismatched-feedback.git
cd Strategy-improvement-despite-mismatched-feedback
uv sync --frozen
```

[`.python-version`](.python-version) selects Python 3.12. [`pyproject.toml`](pyproject.toml) defines the project and its dependencies, and [`uv.lock`](uv.lock) fixes their resolved versions. uv creates and manages the project environment; the same commands work on Windows, Linux and macOS without activating an environment or specifying its interpreter path. `--frozen` prevents changes to the lockfile during reproduction. See the [uv project documentation](https://docs.astral.sh/uv/guides/projects/).

The first sync may download Python, packages and build dependencies. After setup, add `--offline` to `uv run` to disable dependency downloads. The commands below read recorded model responses and cached labels; they make **no LLM API calls**. Run the analysis commands first, followed by the figure/table commands. All commands use the existing project scripts with explicit input and output arguments.

Generated intermediate filenames append `_reproduct` beside the corresponding paper files. Numerical summaries and CSV exports stay in their respective data directories. The flat `reproduct/` directory contains only regenerated figures: `fig2`, `fig3` and `figS1`-`figS6`, available as PNG, PDF and SVG. Figure 1 is the method schematic in `assets/`.

## Paper data and file structure

The data cover DeepSeek and Qwen in OFF/ON configurations, with Accurate and Mismatched reports in each configuration. Reproduction uses model requests and responses, candidate programs, selection decisions, test payoffs and independent behavioural measurements.

Each model/configuration uses the same 20 populations and 60 parents, with two candidates per parent and report condition: **240 candidates, 120 two-candidate pools and 360 S1/S2/S3 decisions**. The four configurations contain 960 candidate responses and share the 240 DeepSeek OFF initialization responses. Additional models or configurations do not increase the number of independent populations.

| Model/configuration | Data directory | Request settings |
| --- | --- | --- |
| DeepSeek OFF | `results/feedback_specificity_v2/` | `deepseek-flash`; temperature=1; thinking disabled; max_tokens=6000 |
| DeepSeek ON | `results/feedback_specificity_thinking_384k_20260923/` | Same API identifier; thinking enabled; reasoning_effort=high; max_tokens=384000 |
| Qwen OFF | `results/qwen3_8/off/` | `qwen3.8-flash`; temperature=1; enable_thinking=false; max_tokens=6000 |
| Qwen ON | `results/qwen3_8/on/` | Same model; enable_thinking=true; reasoning_effort=high; max_tokens=131072 |

The paper names the DeepSeek model deepseek-v4.1-flash; recorded requests use the API identifier `deepseek-flash`. API aliases do not guarantee fixed model weights over time. OFF/ON differ in thinking settings, output budgets and collection times, so configuration differences do not isolate the thinking switch. Qwen is a follow-up model test using the same parents and evaluation panels.

### Record types

Paths below are relative to each experiment directory unless stated otherwise.

| File/directory | Contents and use |
| --- | --- |
| `manifest.json` | Population seeds, parent ranks, report conditions, candidate tasks and request settings |
| `requests_initial/`, `initial/` | 240 initialization requests/responses and validated strategies, stored in DeepSeek OFF |
| `populations/s200.json` ... `s219.json` | 12 strategies per population, training scores, feedback measurements and donor permutations without fixed points |
| `contexts/s200-rank1.json` and related files | 60 shared parents, donors, complete prompts for both conditions and length counts |
| `requests_candidates/<id>.json` | API parameters, responses and usage; ON also includes visible reasoning |
| `candidates/<id>.json` | Candidate programs |
| `selection_scores/<id>.json` | Parent/candidate scores for S1, S2 and S3, independent of test outcomes |
| `SELECTIONS_SEALED.json` | 360 sealed decisions selecting a candidate or retaining the parent |
| `holdout/<id>.json` | Payoff and independent behaviour measurements and gains over parents |
| `ANALYSIS.json`, `AUDIT.json` | Reference analysis summaries |

The ON and Qwen directories contain the supporting records for the shared parents. Reproduction reads these records in place.

## Reproduce each analysis

Run these existing entry points in order from the project root. `--output-suffix` names generated files; `--analysis-suffix` or `--analysis-file` selects the recomputed inputs for downstream analyses.

```sh
uv run --frozen python -m experiments.direct_reciprocity.specificity_analysis results/feedback_specificity_v2 --output-suffix _reproduct
uv run --frozen python thinking_control_analysis.py results/feedback_specificity_thinking_384k_20260923 --source results/feedback_specificity_v2 --source-analysis ANALYSIS_reproduct.json --output-suffix _reproduct
uv run --frozen python results/qwen3_8/analyze.py --root results/qwen3_8 --source results/feedback_specificity_v2 --output-suffix _reproduct
uv run --frozen python -m experiments.direct_reciprocity.role_analysis results/feedback_specificity_v2 --analysis-file ANALYSIS_reproduct.json --output-suffix _reproduct
uv run --frozen python tools/analyze_population.py --analysis-suffix _reproduct --output results/reciprocity_population_visuals_20260924/population_summary_reproduct.json
uv run --frozen python tools/figures/analyze_opponent_profiles.py --analysis-suffix _reproduct --output results/figure4_opponent_profiles_20260926/ANALYSIS_reproduct.json
uv run --frozen python tools/figures/plot_behavior_evidence.py --analysis-suffix _reproduct --output results/reciprocity_population_visuals_20260924/behavior/ANALYSIS_reproduct.json
uv run --frozen python -m experiments.direct_reciprocity.mismatch_distance --root . --output-suffix _reproduct
uv run --frozen python results/model_comparison_20260928/cross_model_summary.py --analysis-suffix _reproduct --output results/model_comparison_20260928/cross_model_mainline_data_reproduct.json --csv-dir results/model_comparison_20260928 --output-suffix _reproduct
uv run --frozen python tools/judge_mismatch_detection_summary.py report --judgments-dir results/mismatch_detection_jev/judgments --threshold 0.40 --confidence 0.60 --output-json results/mismatch_detection_jev/jev_recount_reproduct.json --output-markdown results/mismatch_detection_jev/REPORT_reproduct.md
```

| Analysis | Computational script | Inputs and recomputed summaries |
| --- | --- | --- |
| OFF matching, Raw/S1/S2/S3 and sensitivity checks | `experiments.direct_reciprocity.specificity_analysis` | OFF requests, sealed decisions and H -> `ANALYSIS_reproduct.json` and `AUDIT_reproduct.json` |
| ON statistics and paired OFF/ON differences | `thinking_control_analysis.py` | OFF/ON H at shared parents -> ON `ANALYSIS_reproduct.json` |
| Qwen comparisons | `results/qwen3_8/analyze.py` | Qwen requests and H -> per-mode and combined `ANALYSIS_reproduct.json` |
| Fixed-pool N/G/U/B policies | `experiments.direct_reciprocity.role_analysis` | Selection scores and H from the same pools -> `role_analysis/ANALYSIS_reproduct.json` |
| Candidate distributions and selection outcomes | `tools/analyze_population.py` | 480 DeepSeek OFF/ON candidates and S3 decisions -> `population_summary_reproduct.json` |
| Opponent-family payoffs | `tools/figures/analyze_opponent_profiles.py` | Per-opponent H payoffs -> `figure4_opponent_profiles_20260926/ANALYSIS_reproduct.json` |
| Independent behavioural stages | `tools/figures/plot_behavior_evidence.py` | F′ and sealed S3 decisions -> `behavior/ANALYSIS_reproduct.json` |
| Mismatch distances and sensitivity | `experiments.direct_reciprocity.mismatch_distance` | F reports for 240 initial strategies, 60 parent/donor pairs and candidate H -> distance files with `_reproduct` appended to their stems |
| Cross-model summary | `results/model_comparison_20260928/cross_model_summary.py` | Four configurations and paired population vectors -> `cross_model_mainline_data_reproduct.json` |
| Visible-reasoning label checks | `tools/judge_mismatch_detection_summary.py report` | 240 labels in `results/mismatch_detection_jev/judgments/` -> `results/mismatch_detection_jev/jev_recount_reproduct.json` |

## Reproduce the figures and tables

`reproduct/` contains only human-viewable figures, with no subdirectories. Open the PNG links below to view them; PDF and SVG versions use the same filename stems. Plotting source code is in `tools/figures/`, and intermediate summaries stay beside the corresponding paper data.

Generate the figures and tables from the `_reproduct` analysis files:

```sh
uv run --frozen python tools/figures/plot_results_three_figures.py --analysis-suffix _reproduct --output-dir reproduct
uv run --frozen python tools/figures/plot_camera_ready.py --analysis-suffix _reproduct --figures 3 4 5 --output-dir reproduct
uv run --frozen python tools/figures/build_interface_figures.py --input results/reciprocity_population_visuals_20260924/population_summary_reproduct.json --display-output results/figure_rendering/frozen_generation_display_reproduct.json --output-dir reproduct
uv run --frozen python tools/figures/plot_opponent_profiles.py --input results/figure4_opponent_profiles_20260926/ANALYSIS_reproduct.json --output-dir reproduct
uv run --frozen python tools/figures/plot_mismatch_distance.py --inputs docs/direct_reciprocity/mismatch_distance/mismatch_distance_thinking_off_reproduct.json docs/direct_reciprocity/mismatch_distance/mismatch_distance_thinking_on_reproduct.json --output-dir reproduct
uv run --frozen python tools/export_paper_tables.py --work . --analysis-suffix _reproduct --output results/reproduction/tables --output-suffix _reproduct
```

| Paper item | Reproduction output | Script and data |
| --- | --- | --- |
| Figure 1 | [figure1.png](assets/figure1.png) · [PDF](assets/figure1.pdf) | Method schematic supplied as PDF/PNG, with editable source in `assets/figure1_editable.pptx` |
| Figure 2 | [fig2.png](reproduct/fig2.png) · PDF/SVG | `plot_results_three_figures.py`; cross-model matching and paired population Raw/S3 gains |
| Figure 3 | [fig3.png](reproduct/fig3.png) · PDF/SVG | Same script; opponent-family payoffs and independent behaviour |
| Figure S1 | [figS1.png](reproduct/figS1.png) · PDF/SVG | `plot_camera_ready.py --figures 3`; both conditions, three selectors and OFF/ON |
| Figure S2 | [figS2.png](reproduct/figS2.png) · PDF/SVG | `build_interface_figures.py`; 240 candidates and 120 pools per configuration; recomputed histograms and Gaussian KDE with Scott's bandwidth |
| Figure S3 | [figS3.png](reproduct/figS3.png) · PDF/SVG | `plot_camera_ready.py --figures 5`; fixed-pool policies and decomposition |
| Figure S4 | [figS4.png](reproduct/figS4.png) · PDF/SVG | `plot_opponent_profiles.py`; four opponent-family payoffs for Raw/S3 |
| Figure S5 | [figS5.png](reproduct/figS5.png) · PDF/SVG | `plot_camera_ready.py --figures 4`; independent behavioural differences for OFF |
| Figure S6 | [figS6.png](reproduct/figS6.png) · PDF/SVG | `plot_mismatch_distance.py`; shared parent-donor distances |
| Table S1 | `tableS1_probe_parameters_reproduct.csv/.tex` | Fixed F′ probe parameters |
| Table S2 | `tableS2_primary_reproduct.csv/.tex` | Prespecified Raw matching comparison |
| Table S3 | `tableS3_sensitivity_reproduct.csv/.tex` | OFF noise and longer-match checks |
| Table S4 | `tableS4_selection_reproduct.csv/.tex` | S3-minus-N noise and longer-match checks |
| Table S5 | `tableS5_distance_reproduct.csv/.tex` | Matching differences after excluding closest donors |

Both manuscripts use Figures 1–3 and Tables I–II in the main text, and Figures S1–S6 and Tables S1–S5 in the appendices. `tools/export_paper_tables.py` writes the supplementary tables to `results/reproduction/tables/`. Main Tables I and II define the report conditions and S1/S2/S3 scoring, respectively; both contain fixed protocol definitions and require no API calls.

CSV exports are in `results/model_comparison_20260928/`: `candidate_gains_reproduct.csv` contains candidate gains, `population_gains_reproduct.csv` contains population-level gains, and `condition_statistics_reproduct.csv` contains means and intervals. Cached reasoning-label summaries are written to `results/mismatch_detection_jev/jev_recount_reproduct.json`.

## Optional new API generation

The reproduction above uses recorded responses and requires no API credentials. For a small new API run, copy `.env.example` to `.env` and configure the DeepSeek key. Reuse population s200 and its rank-1 parent without copying the initialization records:

```sh
uv run --frozen python -m experiments.direct_reciprocity.specificity freeze --output results/api_smoke_reproduct --source results/feedback_specificity_v2 --seeds 200 --ranks 1
uv run --frozen python -m experiments.direct_reciprocity.specificity all --output results/api_smoke_reproduct --workers 4 --api-workers 1 --env-file .env
uv run --frozen python -m experiments.direct_reciprocity.specificity_analysis results/api_smoke_reproduct --output-suffix _reproduct
```

This run makes four candidate calls: two Accurate and two Mismatched. The same generation, selection, payoff evaluation and analysis code writes the new records and `ANALYSIS_reproduct.json` to `results/api_smoke_reproduct/`. Re-running a completed directory uses its recorded responses; choose a new output directory for additional API samples. A single population demonstrates the API-to-analysis workflow; recover the paper's statistics from the recorded-data commands above. New API outputs need not match the original generated programs.

For a complete new experiment, omit `--source`, `--seeds` and `--ranks` at the freeze stage and use a separate output directory. Defaults make 240 initialization calls and 240 candidate calls. ON/Qwen generators accept `--source` pointing to a completed new OFF experiment and require distinct output directories.
