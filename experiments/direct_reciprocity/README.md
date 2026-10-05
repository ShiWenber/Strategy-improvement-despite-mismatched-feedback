# Direct reciprocity experiments

## Active follow-up: feedback attribution

The living Chinese manuscript is
[FEEDBACK_ATTRIBUTION_DRAFT.md](../../docs/direct_reciprocity/FEEDBACK_ATTRIBUTION_DRAFT.md).
Put subsequent findings and interpretation in that manuscript; retain immutable
protocol snapshots and raw results separately. The earlier prompt matrix is prior
exploratory evidence, not the claimed novelty of this follow-up.

The first stage fixes parents and compares true, shuffled, hidden explicit scores,
and true scores plus behavioral diagnostics (120 requests, five seed clusters).
Use `python -m experiments.direct_reciprocity.feedback --workers 4 --env-file ../../.env`
and then `python -m experiments.direct_reciprocity.feedback_analysis`.
The first external generation launch was rejected by automatic approval review.
The user subsequently explicitly authorized sending the listed strategy code,
scores and behavioral diagnostics to DeepSeek for these 120 requests. This
authorization is recorded in the living draft and EXECUTION_STATUS.json.
Phase 1 is complete: 120 model responses, 119 valid policies, one invalid policy
retaining its parent, and all 120 outcomes recorded. See the manuscript for
paired seed-level estimates and the limits of the diagnostic-feedback signal.
No multi-generation feedback-attribution batch has been run.

## Original experiment

This worktree adds a bilateral repeated-PD experiment to the existing framework.
Read docs/direct_reciprocity/LITERATURE_REVIEW.md and EXPERIMENT_PLAN.md before interpreting results.

From this worktree:

```powershell
python -m unittest discover -s tests -p test_direct_reciprocity.py -v
python -m experiments.direct_reciprocity.run --dry-run --env-file ../../.env
python -m experiments.direct_reciprocity.run --env-file ../../.env --prompt minimal --selection paper_truncation --seed 0
```

The default is N=12, 10 evaluated generations, 100 rounds per match, five repeats,
R/S/T/P=3/0/5/1 and 60% peer + 40% archive average cumulative score.
Other prompt treatments: score, full.
The former tournament and Fermi selection rules were removed on 2026-10-03: the
manuscript reports fixed-parent single-step revisions and no multi-generation
run, so truncation selection is the only surviving rule and every refilled slot
uses the full-mutation operator.

An explicit --env-file loads existing configuration without copying credentials into
this worktree. Do not publish request secrets. The saved request records include model,
temperature, prompt, response, usage and the explicit disabled-thinking option for DeepSeek.
The provider's default thinking mode exhausted the first pilot's output limit without
producing code; that failed pilot remains in results/direct_reciprocity_pilot.

Outputs have config.json, requests/, generation_NNN.json and complete.json. Running the
same command resumes completed generations and reuses completed request records.
A pending or failed API request stops rather than automatically repeating a possibly
billed call. Inspect its record and provider outcome before deliberately moving it aside.
Invalid offspring remain recorded and leave the previous slot unchanged. Invalid initial
policies stop initialization; they are not silently replaced by human baselines.

The holdout panel is never included in prompts or used in selection. Report population,
archive, fixed-training-panel and holdout scores separately. Test scores are cumulative;
divide by that evaluation's rounds when comparing different match lengths.

Current completion status is in docs/direct_reciprocity/STATUS.md. A pilot, a dry run,
or unit tests alone are not evidence for the planned factorial research result.

## Random imports

Policies may now use `import random`, `import random as r`, and named
`from random import ...` at module or function level. The imported API is backed
by the same per-match stream as `rng`; it does not share process-global state.
`random.Random()` and `random.seed(None)` derive reproducible seeds from that stream.
SystemRandom, private APIs and other modules are not part of this interface.
The old main_v1 batch was stopped when this user-requested protocol change was applied.
Do not combine its evaluation results with a new implementation hash.

## Evaluation recovery and incremental controls

A holdout-only runtime failure can be recovered with:

```powershell
python -m experiments.direct_reciprocity.recover_evaluation results/direct_reciprocity_main_v2/minimal__paper_truncation__seed1 --env-file ../../.env
```

This records a separate recovery implementation hash. Failed holdout metrics are null;
training failures still stop the run. Report test failure rates with conditional score
summaries, which can be affected by survivorship bias. See the dated protocol amendment.

Use `control ROOT --seed 2 --available-only` (as a Python module) to evaluate currently
completed references. Rerun for missing references later; this mode is not evidence that
all controls are complete. Candidate generation and selection checkpoints are reused.

## Regenerating reports

The completed 45-run matrix and 45 matched controls are summarized in
[the final report](../../docs/direct_reciprocity/FINAL_REPORT.md).

Run from this worktree after the corresponding result files have been saved:

```powershell
python -m experiments.direct_reciprocity.analyze results/direct_reciprocity_main_v2
python -m experiments.direct_reciprocity.factor_report results/direct_reciprocity_main_v2
python -m experiments.direct_reciprocity.analyze_control results/direct_reciprocity_main_v2
python -m experiments.direct_reciprocity.trajectory_analysis results/direct_reciprocity_main_v2
python -m experiments.direct_reciprocity.plot_results results/direct_reciprocity_main_v2
python -m experiments.direct_reciprocity.usage_report results/direct_reciprocity_main_v2
python -m experiments.direct_reciprocity.audit results/direct_reciprocity_main_v2
```

`factor_report` reads `analysis.json`, so regenerate `analyze` first. Its 108
paired comparisons cover three test settings and score, cooperation, and worst-opponent
score. Missing tests remain explicit; bootstrap intervals are exploratory and unadjusted
for multiple comparisons. Partial reports are snapshots, not final experiment results.
The structural audit checks recorded protocol consistency; it is not a replay of every match.

## Diagnostic specificity follow-up (v2)

The frozen follow-up uses 20 new populations, 240 shared initialization requests,
and 600 proposals across scalar scores, accurate diagnostics, mismatched diagnostics,
length-matched background, and generic cooperation advice. See
[the execution protocol](../../docs/direct_reciprocity/SPECIFICITY_EXECUTION_PROTOCOL.md).
Unlike the original matrix's initialization rule, this protocol explicitly logs
invalid initial programs and substitutes ALLD without extra generation requests.
Candidates retain their parent when invalid. API failures remain missing and do
not trigger automatic retries.

```powershell
python -u -m experiments.direct_reciprocity.specificity all --workers 24 --api-workers 8 --env-file ../../.env
python -m experiments.direct_reciprocity.specificity_analysis
python -m experiments.direct_reciprocity.specificity_supplement
python -m experiments.direct_reciprocity.specificity_tables
python -m experiments.direct_reciprocity.plot_specificity
python -m experiments.direct_reciprocity.specificity_completion
```

The first command checks the frozen implementation and resumes completed stages.
Do not edit the frozen three specificity modules after generation starts. Final H
evaluations are gated on the complete sealed candidate and selection records.
Removing the tournament and Fermi rules (2026-10-03) changed `implementation_hash()`
(the `selection.py` contents and the dropped `evolution_rules.py` entry), which
`specificity.py` and `feedback.py` fold into their own `source_hash()`. Manifests
frozen before that change no longer validate, so `check_manifest` refuses to resume
them. To re-run those analyses, restore the pre-removal `selection.py` and
`evolution_rules.py` from git history and run them there.
Analysis and plots require the complete result set; partial progress is reported in
`results/feedback_specificity_v2/EXECUTION_STATUS.json`. Results and interpretation
continue in the existing feedback-attribution draft.

If Windows temporarily locks an output during local evaluation, the local-only
continuation is `python -u -m experiments.direct_reciprocity.specificity_resume_local
--workers 24` (one command). It reuses complete measurements and retries only
PermissionError while persisting files; it cannot make model requests. Do not
start a second primary runner while an existing one is active. The parallel-tail
helper uses a separate staging directory and verifies duplicate records; extra
work is reported separately in SUPPLEMENT.json and is never an extra sample.

COMPLETION_AUDIT.json checks the expected record sets, 900 sealed selection
decisions, analysis/figure linkage, measurement status counts and completed local
game counts. It does not claim an independent simulator or an exact count of
every attempted game, including interrupted and duplicated work. The sampled
deterministic replay uses the same frozen simulator.
