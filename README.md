# Strategy improvement despite mismatched feedback

Code and archived records for *Strategy improvement despite mismatched feedback: evolving direct reciprocity with large language models*.

This release includes Figures 1-7 and Tables I-V, with the appendix included in the same manuscript. Figure copies are in `assets/paper/`; the mapping below identifies their evidence and renderers.

## Reproduce the Paper

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then run from the repository root on Windows, Linux or macOS:

```sh
uv sync --locked                # reproduction only
uv sync --extra test --locked   # reproduction plus the test suite
uv run python -m tools.reproduce
uv run pytest
```

Reproduction reads **archived responses and game results**, makes **zero LLM API calls**, and requires **no API keys**. It recomputes statistics with the existing estimators and seeds, exports the tables, and redraws the figures. No `.env` file is required. A Python 3.12 environment with the dependencies in `pyproject.toml` can also run `python -m tools.reproduce` directly.

Dependency installation requires package access. Once dependencies are installed, archived-data reproduction and tests run offline. See [VALIDATION.md](docs/reproduction/VALIDATION.md) for the release checks and figure-audit scope.

Open `results/reproduction/latest/` for the collected outputs:

| Path | Contents |
| --- | --- |
| `figures/figure1.*` to `figure7.*` | Manuscript figures, PNG/PDF and editable SVG where available |
| `tables/tableI_*` to `tableV_*` | CSV/TeX with the manuscript's continuous numbering |
| `tables/extra_*` | Primary-test, Score-baseline and Score-failure evidence retained outside the compiled table sequence |
| `cached_labels.json` | Recount of the stored visible-reasoning judgments |
| `RUN_REPORT.json` | Step commands, exit codes and execution status |
| `logs/` | One complete log per step |

Recomputed analysis files use the suffix `_reproduct` beside the data; original `ANALYSIS.json` files remain the references. Frozen paper figures are in `assets/paper/` for direct comparison. Figure 1 is the original method schematic; the remaining figures are rendered from the recomputed summaries. Historical `figS*` names are retained inside plotting modules for compatibility; the collector exports `figure1` through `figure7` for this manuscript.

```sh
# Inspect the commands without changing any files.
uv run python -m tools.reproduce --dry-run

# Recompute statistics and export tables only.
uv run python -m tools.reproduce --steps analysis

# Redraw figures after the analysis outputs already exist.
uv run python -m tools.reproduce --steps figures

# Use a different complete dataset workspace or export location.
uv run python -m tools.reproduce --work results/api_reproduct --output results/api_reproduct/exports
```

The archived paper data contain all three conditions and 20 populations. Archived reasoning labels are recounted only when the chosen workspace contains them. Each stage reads its required inputs directly; missing inputs and execution errors appear in that stage's log.

`--work DIRECTORY` selects a complete alternative workspace containing `results/` and `docs/`; `--output DIRECTORY` changes the export destination. The Bash convenience command `bash tools/plot.sh --work .` runs the same complete offline workflow.

Audits run separately from generation, analysis and plotting. Default runs do not read audit certificates, write `AUDIT.json` or require `VALIDATION.json`. Missing data, failed requests and simulator errors still propagate through the stage that uses them.

```sh
# Inspect the archived input inventory without running the workflow.
uv run python -m tools.reproduce --steps audit

# Inspect new API records; print the audit report without changing RUN_STATUS.json.
uv run python -m tools.run_fresh_reproduction --output reproduction --steps audit

# Run a record audit with a separate output location.
uv run python -m experiments.direct_reciprocity.specificity_analysis results/feedback_specificity_v2 --audit-only --audit-output ../audit-results/deepseek-off.json
```

The paired DeepSeek and Qwen analysis modules also accept `--audit-only --audit-output PATH`. Figure layout checks remain available in `figures/results_plot_audit.py` for explicit use; normal renderers only export figures.

## Repository Layout

```text
experiments/direct_reciprocity/     Simulator, generation, selection and analysis
experiments/direct_reciprocity/figures/  Quantitative figure renderers
tools/reproduce.py                 Cross-platform offline workflow
tools/generate_api.sh              Explicit new API experiment
tools/package_reproduction.py      Code/data release packaging
tests/                            Simulator, workflow and archive checks
assets/paper/                     Latest-paper figure snapshots
docs/reproduction/                Release validation and reproduction notes
results/                          Archived experiments and derived summaries
results/reproduction/latest/      Collected current reproduction outputs
```

## Paper Mapping

| Paper item | Compiled label | Evidence and renderer |
| --- | --- | --- |
| Figure 1 | `fig_overview` | Exact method-schematic snapshot in `assets/paper/figure1.*`; copied, not statistically regenerated |
| Figure 2 | `fig_proposals`, `fig_selection` | Four configurations, Raw/S3 for Score/Accurate/Mismatched; paired Accurate-minus-Mismatched; 80 population pairs. `cross_model_summary` -> `figures.plot_results_three_figures` |
| Figure 3 | `fig_opponent_profiles` | Opponent-family payoffs and independent F-prime probes, DeepSeek OFF/ON. `figures.analyze_opponent_profiles` + `figures.plot_behavior_evidence` -> `figures.plot_results_three_figures` |
| Figure 4 | `fig_generation_selection_full` | Two-condition candidate distributions and sealed S3 outcomes. `analyze_population` -> `figures.build_interface_figures` |
| Figure 5 | `fig_all_selectors` | Accurate/Mismatched under S1/S2/S3, DeepSeek OFF/ON. `figures.plot_camera_ready --figures 3` |
| Figure 6 | `fig_policies` | Fixed-pool N/G/U/B means and S3 paired decomposition. `role_analysis` -> `figures.plot_camera_ready --figures 5` |
| Figure 7 | `fig_mismatch_distance` | Frozen 36-feature parent-donor and within-population distances. `mismatch_distance` -> `figures.plot_mismatch_distance` |
| Table I | `tab_selectors` | Fixed S1/S2/S3 protocol: scoring source, opponents, repeats, games and weights |
| Table II | `tab_probe` | Fixed F-prime probe parameters |
| Table III | `tab_decomposition` | S3 B-minus-N under noise and longer matches, `role_analysis` |
| Table IV | `tab_sensitivity` | Raw Accurate/Mismatched gains under noise and longer matches, `specificity_analysis` |
| Table V | `tab_mismatch_distance_sensitivity` | Raw matching contrasts after excluding the 20 closest parent-donor pairs, `mismatch_distance` |

The renderers follow the latest panel structure: Figure 3 places payoff panels on the left and behaviour panels on the right; Figure 4 has two panels; Figure 6a shows policy means without confidence intervals, and Figure 6b retains the decomposition intervals. The paper's exact graphic files are preserved under `assets/paper/` for comparison. Numerical reproduction uses the full-precision archives; exported file bytes can vary with PDF metadata, fonts and platform.

Plot sample counts, population seeds, result annotations and numeric axis limits are derived from the selected inputs. Rendering does not require a contrast interval to cross zero or a fixed number of improved pools. Equal-payoff selections are displayed when present, and constant candidate samples use their histogram without an unidentified KDE. Palette, physical layout, unit conversions and prespecified statistical-method parameters remain explicit configuration. Regression coverage is in `tests/test_data_driven_figures.py`.

Older supplementary opponent and behaviour plots, primary-test tables, Score tables and the unused generation-configuration table are not numbered as figures or tables of the compiled manuscript. Score remains required because it appears in Figure 2.

Git tracks only the current paper's figure inputs, frozen figure copies and statistical
reference summaries, listed with SHA256 hashes in `results/reproduction/INPUT_MANIFEST.json`.
`tools.reproduce.paper_input_paths` defines the files needed to recompute the figures;
`paper_reference_paths` defines the frozen comparison targets. API requests and streams,
duplicate condition logs, failed attempts, smoke tests, reasoning annotations, old exports
and the new `reproduction/` experiments stay local. Generated `_reproduct` files and
`results/reproduction/latest/` are rebuilt by the command above and are ignored by Git.

## Experimental Records

Each configuration below is generated by a specific entry point. The `Generation script` column gives the
module and stage that produced the archived records; `bash tools/generate_api.sh` runs exactly this sequence.

| Configuration | Records | Generation script | API identifier / recorded settings |
| --- | --- | --- | --- |
| DeepSeek OFF | `results/feedback_specificity_v2/` | `experiments.direct_reciprocity.specificity` stages `freeze` -> `all` | `deepseek-flash`, temperature 1, thinking disabled, 6,000 output tokens |
| DeepSeek ON | `results/feedback_specificity_thinking_384k_20260923/` | `experiments.direct_reciprocity.paired_control --provider deepseek` stages `prepare` -> `first` -> `all` | `deepseek-flash`, thinking enabled, high effort, 384,000 output tokens |
| Qwen OFF | `results/qwen3_8/off/` | `experiments.direct_reciprocity.paired_control --provider qwen` stages `prepare` -> `first` -> `all` | `qwen3.8-flash`, thinking disabled, 6,000 output tokens |
| Qwen ON | `results/qwen3_8/on/` | `experiments.direct_reciprocity.paired_control --provider qwen` stages `prepare` -> `first` -> `all` | `qwen3.8-flash`, thinking enabled, high effort, 131,072 output tokens |

DeepSeek OFF is the only configuration that creates populations and parents; it is the `--source` of the
other three, which reuse its parents, prompts and parent selection scores and call the API only for their own
candidates. The generation stages are `freeze` (write the manifest and job identities), `initialize` (240
population and parent responses), `prepare` (build prompts and contexts), `generate` (candidate responses),
`select` (seal the S1/S2/S3 decisions) and `holdout` (independent panel H). The `first` stage issues one
candidate request when requested; generation can also start directly and reuse any saved first response.

| Generated artifact | Written by |
| --- | --- |
| `manifest.json` (identities, settings, conditions) | `specificity` stage `freeze`; `paired_control` stage `prepare` |
| `contexts/`, `populations/` | `specificity` stages `initialize` and `prepare` |
| `requests_candidates/`, `candidates/` | `specificity` / `paired_control` stage `generate` |
| `selection_scores/`, `SELECTIONS_SEALED.json` | `specificity` / `paired_control` stage `select` |
| `holdout/` | `specificity` / `paired_control` stage `holdout` |
| `arm_logs/`, `requests_initial/` | `condition_generation.write_arm_logs` (shared by both generators) |
| `PROTOCOL.md` | `paired_control` stage `prepare`, when the source protocol document is available |

The analysis of these records is a separate step and makes no API calls:
`specificity_analysis` (DeepSeek OFF), `thinking_control_analysis` (DeepSeek ON), `qwen_analysis` (Qwen
OFF/ON), `role_analysis` (policy decomposition) and `analyze_population` (population summaries).

All configurations reuse the same **20 populations (seeds 200-219) and 60 parents (ranks 1, 3 and 6)**, and share the **240 DeepSeek OFF initialization responses**. Each configuration contains **360 candidates, 180 pools and 540 selector decisions** across Score, Accurate and Mismatched. The four configurations contain **1,440 candidate responses**. Accurate-versus-Mismatched comparisons use 240 candidates and 120 pools per configuration; population is the independent statistical unit, and the four configurations reuse the same independent units.

Score retains parent strategy, complete population code, game rules and genuine training scores, with no behavioural report. Accurate appends the parent's own report; Mismatched appends another population member's report. Matching comparisons hold the other inputs fixed. Raw evaluates both candidates before selection; S1/S2/S3 independently select from each fixed two-candidate pool or retain the parent. Selection is sealed before independent payoff panel H evaluates outputs.

`manifest.json` fixes the task identities, settings and condition assignments. The
collection paths above describe the full local experiment. The Git release retains
the subset consumed by the paper workflow: held-out outcomes and sealed selections
for all four configurations, required selection scores, and DeepSeek population,
context and matching-condition candidate records. Full API provenance audits and
optional reasoning-label/replay archive checks require the additional local records.
Invalid candidates and setting-specific execution failures use the frozen fallback
protocol; unavailable parent measurements remain explicitly undefined.

Model names in the paper and request aliases differ. The recorded DeepSeek API alias is `deepseek-flash`, while the paper names `deepseek-v4.1-flash`. New API responses need not reproduce historical backend weights or programs. OFF/ON also differ in output budgets and collection times.

The archived records predate the current module names. When the collection was first archived, the
generators were `experiments/direct_reciprocity/specificity.py` (DeepSeek OFF),
`experiments/direct_reciprocity/thinking_control.py` (DeepSeek ON) and
`experiments/direct_reciprocity/qwen38_control.py` (Qwen OFF/ON). A later refactor consolidated the shared
condition-generation path into `condition_generation.py` and replaced the two follow-up modules with
`paired_control.py`, which covers both the DeepSeek ON and the Qwen OFF/ON batches. The archived
`manifest.json` files still carry the original `version` strings (`specificity-v2`, `thinking-384k-v1`,
`qwen3.8-flash-v1`), while the current scripts write `specificity-v3`, `thinking-384k-v2` and
`<model>-v2`.

The archive tests compare original and recomputed scientific summaries at absolute tolerance `1e-12`, check candidate/selection completeness and trace condition logs back to their source files. A separate simulator replay is available:

```sh
uv run python -m experiments.direct_reciprocity.replay --work . --output results/reproduction/latest/replay.json --workers 4
```

This samples one parent and the first candidate in each of the three conditions in each configuration. `--full` replays all default-H records and may take many hours. Replay uses the project's simulator; it checks deterministic replay rather than an independent implementation.

## Optional New API Experiments

Create `.env` using the fields in `.env.example`, then explicitly run:

Set `DEEPSEEK_MODEL` and `QWEN_MODEL` to the model IDs you want to call. New API
experiments read these settings from `.env`; `tools.run_fresh_reproduction`
also accepts `--env-file path/to/.env`. File settings take precedence over
inherited environment variables. Missing or empty model settings stop new
requests. Resuming an API run requires the same models as its frozen manifest;
use a new output directory to change models. Offline analysis and figure labels
use the recorded model identities.

```sh
bash tools/generate_api.sh results/api_reproduct_new
uv run python -m tools.reproduce --work results/api_reproduct_new
```

The generation script plans **1,680 model calls**: 240 initialization calls and 1,440 candidate calls. It builds new DeepSeek OFF parents first, then reuses them for DeepSeek ON and Qwen OFF/ON. Within a configuration it generates Score, Accurate and Mismatched in that order. A reused workspace resumes recorded work; an empty workspace creates a new sample. New API samples may differ from the archived paper results. These are new experiments, separate from reproducing the paper's recorded results.

## Release Bundle

After successful offline reproduction:

```sh
uv run python -m tools.package_reproduction
```

This creates `dist/direct_reciprocity_paper_20261013.zip`. The same explicit paper
allowlist includes code, locked dependencies, tests, required figure data and frozen
paper references. Generated exports are rebuilt after extraction. The bundle can run
without Git or the private manuscript checkout. Credentials, local environments,
Git history and unrelated experiments are excluded. Packaging refuses to replace an
existing ZIP; choose a new `--output` path for another release.

When maintaining a later paper revision, rebuild the manuscript first and copy its figures with `uv run python -m tools.freeze_paper_snapshot --manuscript PATH`. This command copies figure files into `assets/paper/` after checking the compiled figure and table numbering.
