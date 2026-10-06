# Strategy improvement despite mismatched feedback

This repository accompanies *Strategy improvement despite mismatched feedback: evolving direct reciprocity with large language models*. The project repository is [ShiWenber/Strategy-improvement-despite-mismatched-feedback](https://github.com/ShiWenber/Strategy-improvement-despite-mismatched-feedback).

The paper compares **Accurate** and **Mismatched** reports while holding the parent strategy, population code, game rules and genuine training scores fixed. Accurate supplies the parent's own numerical behavioural report; Mismatched supplies another strategy's report from the same population. Candidate quality before selection is evaluated separately from the quality of externally selected outputs.

## Reproduce with uv

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) and Git, then run these commands from the project root:

```sh
git clone https://github.com/ShiWenber/Strategy-improvement-despite-mismatched-feedback.git
cd Strategy-improvement-despite-mismatched-feedback
uv sync --frozen
uv run --frozen python tools/reproduce.py
```

[`.python-version`](.python-version) selects Python 3.12. [`pyproject.toml`](pyproject.toml) defines the project and its dependencies, and [`uv.lock`](uv.lock) fixes their resolved versions. uv creates and manages the project environment; the same commands work on Windows, Linux and macOS without activating an environment or specifying its interpreter path. `--frozen` prevents changes to the lockfile during reproduction. See the [uv project documentation](https://docs.astral.sh/uv/guides/projects/).

The first sync may download Python, packages and build dependencies. After setup, add `--offline` to `uv run` to disable dependency downloads. The reproduction pipeline itself uses recorded model responses and blocks network access in its workers; it makes **no LLM API calls**.

The complete run verifies input hashes, recomputes statistics, exports data, regenerates figures and replays a sample of games. Inspect `results/reproduction/verification_reproduct.json`: `status` should be `passed`, all statistical comparisons should pass, and replay error should be at most `1e-12`.

Individual stages use the same uv environment:

```sh
uv run --frozen python tools/reproduce.py --stage prepare
uv run --frozen python tools/reproduce.py --stage statistics
uv run --frozen python tools/reproduce.py --stage figures
uv run --frozen python tools/reproduce.py --stage replay
```

Run `statistics` before `figures` because the figures consume the recomputed `_reproduct` summaries. Each invocation writes a report for that stage; run the command without `--stage` to obtain a complete verification report.

## Paper data and file structure

The data cover DeepSeek and Qwen in OFF/ON configurations, with Accurate and Mismatched reports in each configuration. Reproduction uses model requests and responses, candidate programs, selection decisions, test payoffs and independent behavioural measurements.

Each model/configuration uses the same 20 populations and 60 parents, with two candidates per parent and report condition: **240 candidates, 120 two-candidate pools and 360 S1/S2/S3 decisions**. The four configurations contain 960 candidate responses and share the 240 DeepSeek OFF initialization responses. Additional models or configurations do not increase the number of independent populations.

| Model/configuration | Data directory | Valid candidates / 240 | Request settings |
| --- | --- | ---: | --- |
| DeepSeek OFF | `results/feedback_specificity_v2/` | 232 | `deepseek-flash`; temperature=1; thinking disabled; max_tokens=6000 |
| DeepSeek ON | `results/feedback_specificity_thinking_384k_20260923/` | 237 | Same API identifier; thinking enabled; reasoning_effort=high; max_tokens=384000 |
| Qwen OFF | `results/qwen3_8/off/` | 224 | `qwen3.8-flash`; temperature=1; enable_thinking=false; max_tokens=6000 |
| Qwen ON | `results/qwen3_8/on/` | 221 | Same model; enable_thinking=true; reasoning_effort=high; max_tokens=131072 |

The paper names the DeepSeek model deepseek-v4.1-flash; recorded requests use the API identifier `deepseek-flash`. API aliases do not guarantee fixed model weights over time. OFF/ON differ in thinking settings, output budgets and collection times, so configuration differences do not isolate the thinking switch. Qwen is a follow-up model test using the same parents and evaluation panels.

### Record types

Paths below are relative to each experiment directory unless stated otherwise.

| File/directory | Contents and use |
| --- | --- |
| `manifest.json` | Population seeds, parent ranks, report conditions, candidate tasks and request settings |
| `requests_initial/`, `initial/` | 240 initialization requests/responses and validated strategies, stored in DeepSeek OFF |
| `populations/s200.json` ... `s219.json` | 12 strategies per population, training scores, feedback measurements and donor permutations without fixed points |
| `contexts/s200-rank1.json` and related files | 60 shared parents, donors, complete prompts for both conditions and length counts |
| `requests_candidates/<id>.json` | API parameters, responses, usage and validity; ON also includes visible reasoning |
| `candidates/<id>.json` | Candidate programs and validation results |
| `selection_scores/<id>.json` | Parent/candidate scores for S1, S2 and S3, independent of test outcomes |
| `SELECTIONS_SEALED.json` | 360 sealed decisions selecting a candidate or retaining the parent |
| `holdout/<id>.json` | Payoff and independent behaviour measurements, fallback outcomes and gains over parents |
| `ANALYSIS.json`, `AUDIT.json` | Paper statistics and record checks |

The ON and Qwen directories contain the supporting records for the shared parents. Reproduction reads these records in place.

## Experimental implementation and statistical definitions

The implementation is in `experiments/direct_reciprocity/`: `core.py` executes strategies, `baselines.py` defines reference strategies, `prompts.py` constructs prompts, `specificity.py` runs the two-condition experiment, `report_assignment.py` assigns donors, and `specificity_assets.py` defines reports and evaluation panels.

- Strategies implement `strategy(history, rng)` and return C or D. Payoffs for CC/CD/DC/DD are 3/0/5/1. The default match length is 100 rounds. Training weights the 11 population peers and 13 fixed references by 0.6 and 0.4, respectively.
- Population seeds are 200-219, with 12 strategies each. Parents are selected at training ranks 1, 3 and 6. Report donors follow a permutation of the 12 population members without fixed points, without selection by behavioural distance.
- Feedback probe F supplies 10 CC rounds, then measures 24 rounds over 10 repetitions. It covers temporary defection followed by TFT/ALLC, persistent defection and periodic defection, producing 36 features. Reports in both conditions contain 504 `cl100k_base` proxy tokens. In DeepSeek OFF, all 120 paired requests have equal provider-reported input lengths, totaling 1,052,774 input tokens per condition.
- S1 and S2 score against training opponents over 5 and 20 repetitions; S1 uses the first 5 repetitions of S2. S3 uses validation panel V: 4 families, 6 opponents per family and 20 repetitions. A valid candidate is adopted only if the highest candidate score strictly exceeds the parent's score. Parent ties retain the parent; candidate ties prefer draw0.
- Payoff panel H contains 4 families with 3 opponents each, evaluated over 20 repetitions. Records cover the default 100-round setting, action noise 0.01 and a 200-round setting. H does not enter prompts, eligibility checks or ranking. V and H represent recovery, exploitation, random and memory-one families with different parameter instances.
- Independent behavioural probe F′ uses 40 rounds and 20 repetitions, starting from either 7 CC rounds or an empty history. Unilateral cooperation during the final 5 rounds of persistent defection measures exposure. Recovery time counts rounds until 5 consecutive CC outcomes after defection ends; unrecovered cases are capped at the remaining window and retain an unrecovered indicator.
- Invalid candidates are not resampled. Candidate failures in a test setting deploy the parent and contribute zero gain; failures remain in the analysis. DeepSeek OFF has 8 invalid candidates and one additional execution failure of a valid candidate in the 200-round setting.

Raw averages the two candidates for each parent and condition. S1/S2/S3 use one selected candidate or the retained parent per pool. Outcomes are averaged over the three parents within each population, then equally over the 20 populations. Condition averages cover Accurate and Mismatched.

The prespecified confirmatory comparison is DeepSeek OFF Raw Accurate minus Mismatched: mean -0.000307986, 95% interval [-0.010014106, +0.009500625], two-sided exact sign-exchange p=0.951618. The test enumerates all 2^20 population sign exchanges and assumes exchangeability of paired-difference signs. Intervals use 20,000 population bootstrap draws with seed 2026091903. An interval crossing zero does not establish equivalence.

ON focused comparisons use a two-test Holm family. Qwen OFF, ON and ON-minus-OFF comparisons form a three-test Holm family. Selected outcomes, behaviour, fixed-pool policies and distance associations are exploratory; their intervals are not multiplicity-adjusted.

## Reproduce each analysis

`tools/reproduce.py` is the entry point. It invokes the scripts below through `tools/reproduce_worker.py`, which routes generated summaries to filenames with the `_reproduct` suffix beside their paper counterparts. Use the entry point to preserve the summaries used by the paper.

| Analysis | Computational script | Inputs and recomputed summaries |
| --- | --- | --- |
| OFF matching, Raw/S1/S2/S3 and sensitivity checks | `experiments.direct_reciprocity.specificity_analysis` | OFF requests, sealed decisions and H -> `ANALYSIS_reproduct.json` and `AUDIT_reproduct.json` |
| ON statistics and paired OFF/ON differences | `thinking_control_analysis.py` | OFF/ON H at shared parents -> ON `ANALYSIS_reproduct.json` |
| Qwen comparisons | `results/qwen3_8/analyze.py` | Qwen requests and H -> per-mode and combined `ANALYSIS_reproduct.json` |
| Fixed-pool N/G/U/B policies | `experiments.direct_reciprocity.role_analysis` | Selection scores and H from the same pools -> `role_analysis/ANALYSIS_reproduct.json` |
| Candidate distributions and selection outcomes | `tools/analyze_population.py` | 480 DeepSeek OFF/ON candidates and S3 decisions -> `population_summary_reproduct.json` |
| Opponent-family payoffs | `paper_zh_direct/tools/analyze_opponent_profiles.py` | Per-opponent H payoffs -> `figure4_opponent_profiles_20260926/ANALYSIS_reproduct.json` |
| Independent behavioural stages | `paper_zh_direct/tools/plot_behavior_evidence.py` | F′ and sealed S3 decisions -> `behavior/ANALYSIS_reproduct.json` |
| Mismatch distances and sensitivity | `experiments.direct_reciprocity.mismatch_distance` | F reports for 240 initial strategies, 60 parent/donor pairs and candidate H -> distance files with `_reproduct` appended to their stems |
| Cross-model summary | `results/model_comparison_20260928/cross_model_summary.py` | Four configurations and paired population vectors -> `cross_model_mainline_data_reproduct.json` |
| Visible-reasoning label checks | Cached recount in `tools/reproduce.py` | 240 labels in `results/mismatch_detection_jev/judgments/` -> `reproduct/jev_recount.json` |

Fixed-pool policy N randomly draws an existing candidate; G adds a parent gate to that draw; U randomly draws from eligible candidates; B selects the highest-scoring eligible candidate. Expectations average the two possible draws exactly, without new model calls. The analysis reconstructs sealed decisions pool by pool and verifies B-N=(G-N)+(U-G)+(B-U). Policy bootstrap uses seed 20260920 and 20,000 draws.

Opponent-family payoffs equally average the three opponents per family, then the four families, reconstructing total payoff for each population. Exploratory bootstrap uses seed 2026092604. Behaviour analysis joins Parent/Raw/S3 by parent and sealed decisions; it measures one-step revision.

Distances standardize F's 36 features across all 240 initial strategies and compute Euclidean parent-donor distances. The 60 pairs are compared with 2,640 ordered pairs of distinct members within populations. Excluding the closest third leaves 40 parents; OFF/ON Raw matching intervals still cross zero. Distance associations with payoff and behaviour are exploratory.

Visible-reasoning checks cover 120 DeepSeek ON traces per condition. Cached extraction chunks and Jev labels are in `summaries/` and `judgments/`. The strict rule is P(origin question)>=0.40 and confidence>=0.60: Mismatched 31/120, Accurate 0/120. Of those 31 traces, 30 continue using the report and 1 discards it. Automated labels do not establish a true recognition rate. Standard reproduction recounts cached labels; extraction or relabeling requires separate API calls.

## Figures, tables and exported data

`reproduct/` is a flat directory containing regenerated numerical data and figures. Source code and intermediate summaries stay in their normal project locations. Main figures use `fig2` and `fig3`; supplementary figures use `figS1`-`figS6`, each in PNG/PDF/SVG formats.

| Paper item | Reproduction output | Script and data |
| --- | --- | --- |
| Figure 1 | `paper_zh_direct/figures/figure1.pdf` and PNG | Method schematic with an editable PPTX source; use the supplied PDF to compile the paper |
| Figure 2 | `reproduct/fig2.*` | `plot_results_three_figures.py`; cross-model matching and paired population Raw/S3 gains |
| Figure 3 | `reproduct/fig3.*` | Same script; opponent-family payoffs and independent behaviour |
| Figure S1 | `reproduct/figS1.*` | `plot_camera_ready.py --figures 3`; both conditions, three selectors and OFF/ON |
| Figure S2 | `reproduct/figS2.*` | `build_interface_figures.py`; 240 candidates and 120 pools per configuration; recomputed histograms and Gaussian KDE with Scott's bandwidth |
| Figure S3 | `reproduct/figS3.*` | `plot_camera_ready.py --figures 5`; fixed-pool policies and decomposition |
| Figure S4 | `reproduct/figS4.*` | `plot_opponent_profiles.py`; four opponent-family payoffs for Raw/S3 |
| Figure S5 | `reproduct/figS5.*` | `plot_camera_ready.py --figures 4`; independent behavioural differences for OFF |
| Figure S6 | `reproduct/figS6.*` | `plot_mismatch_distance.py`; shared parent-donor distances |
| Table S1 | `tableS1_probe_parameters_reproduct.csv/.tex` | Fixed F′ probe parameters |
| Table S2 | `tableS2_primary_reproduct.csv/.tex` | Prespecified Raw matching comparison |
| Table S3 | `tableS3_sensitivity_reproduct.csv/.tex` | OFF noise and longer-match checks |
| Table S4 | `tableS4_selection_reproduct.csv/.tex` | S3-minus-N noise and longer-match checks |
| Table S5 | `tableS5_distance_reproduct.csv/.tex` | Matching differences after excluding closest donors |

The Chinese manuscript numbers appendices consecutively: Figures S1-S6 correspond to Figures 4-9, and Tables S1-S5 to Tables III-VII. `tools/export_paper_tables.py` writes tables to `results/reproduction/tables/`. Main Table 1 defines the report conditions; Table 2 defines S1/S2/S3 scoring and does not depend on API responses.

Reference mean payoff gains, equally averaging the two report conditions, are:

| Configuration | Raw | S3 |
| --- | ---: | ---: |
| DeepSeek OFF | 0.002475 | 0.025344 |
| DeepSeek ON | 0.068914 | 0.103851 |
| Qwen OFF | 0.020451 | 0.037118 |
| Qwen ON | 0.113492 | 0.157295 |

S3 exceeds Raw in 79/80 population/configuration pairs: 19/20 for DeepSeek OFF and 20/20 for each other configuration. These pairs share 20 populations and are not 80 independent samples.

`reproduct/candidate_gains.csv` contains 960 candidates across 3 test settings, or 2,880 rows. `population_gains.csv` contains 4 configurations x 2 conditions x 4 stages x 20 populations, or 640 rows. `condition_statistics.csv` contains 32 means and intervals.

## Game replay, dependencies and optional regeneration

Default replay chooses the lexicographically first parent and first candidate in each condition from every configuration: 12 objects, independently of validity or payoff direction. Each valid object replays 240 default-H games, checking mean payoff, cooperation rate and worst-opponent payoff. Invalid programs are recorded without execution. Replay uses the project's simulator.

To replay all default-H parent and candidate records:

```sh
uv run --frozen python tools/replay_worker.py --work . --output reproduct/replay.json --full
```

A full replay may take hours. It covers default H, rather than all noise, longer-match and F′ measurements. Program failures or discrepancies are reported without replacing the paper data.

Dependencies are managed exclusively through `pyproject.toml` and `uv.lock`. NumPy supports arrays and bootstrap calculations, SciPy supplies KDE, Matplotlib renders figures, pandas supports analysis, OpenAI/httpx support optional API calls, python-dotenv loads local credentials, and tiktoken checks report lengths.

To sample new strategies, copy `.env.example` to `.env` and configure the relevant API keys. Run generation in a new output directory:

```sh
uv run --frozen python -m experiments.direct_reciprocity.specificity freeze --output results/new_mainline_reproduct
uv run --frozen python -m experiments.direct_reciprocity.specificity all --output results/new_mainline_reproduct --env-file .env
```

A complete batch makes 240 initialization calls and 240 candidate calls. Offline reproduction does not require this step. Generation has no model sampling seed, and API aliases may change, so new API samples cannot guarantee identical text or numerical results. ON/Qwen generators accept `--source` pointing to a completed new OFF experiment and require distinct output directories. The optional Jev relabeling script annotates report-origin questions and handling; it does not generate strategy candidates.

## Compile the manuscripts and verify the project

The English main manuscript is `paper_interface_focus/main.tex`, with supplementary material in `paper_interface_focus/supplement.tex`. The Chinese manuscript is `paper_zh_direct/main.tex`. Both use the official figures in `paper_zh_direct/figures/`; reproduced figures remain in `reproduct/`.

Compiled copies are supplied as the [English main manuscript](paper_interface_focus/main.pdf), [English supplement](paper_interface_focus/supplement.pdf) and [Chinese manuscript](paper_zh_direct/main.pdf).

Install Tectonic or XeLaTeX separately from the Python environment. The Chinese manuscript requires SimSun/SimHei/KaiTi/FangSong; the English manuscript uses Times New Roman/Arial/Consolas. Tectonic may download TeX packages on its first run. `--only-cached` requires an existing TeX cache.

```sh
cd paper_interface_focus
tectonic main.tex
tectonic supplement.tex
tectonic main.tex
cd ../paper_zh_direct
tectonic main.tex
cd ..
```

The English supplement uses `xr` to reference main-manuscript labels; compile the main manuscript first and again after the supplement to refresh references in both directions. Author affiliations and the corresponding email remain TODO fields.

From the project root, install the locked test extra and run the tests through uv:

```sh
uv sync --frozen --extra test
uv run --frozen --extra test python -m pytest tests
```

Record checks validate request/program hashes, sealed records, shared parents, fallback arithmetic and reconstructed selections. Complete reproduction compares population vectors, means and intervals with the paper summaries. `results/reproduction/INPUT_MANIFEST.json` is checked before and after computation. Figure checks include minimum font size and text boundaries. Logs and verification reports use the `_reproduct` suffix under `results/reproduction/`.

Reference verification covers 5,658 input hashes, 23 comparisons comprising 26,477 numerical values, and 2,640 sampled games, with maximum error 0 and zero API calls. The test suite contains 80 passing tests and 1 skipped test. See the [complete reproduction report](results/reproduction/verification_reproduct.json), [uv workflow validation](results/reproduction/uv_validation_reproduct.json) and [isolated-clone validation](results/reproduction/clean_clone_validation_reproduct.json).
