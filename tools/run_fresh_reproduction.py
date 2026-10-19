"""Run new model calls, then analyze and plot only the new experiment records."""
from __future__ import annotations

import argparse
import ast
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time

from tools.reproduce import ROOT, RUNS, PREFIX, commands, read
from experiments.direct_reciprocity.records import write_json
from experiments.direct_reciprocity.holdout_metrics import (
    audit_deltas, availability, parent_available, setting_available,
)
from experiments.config.load_env import api_environment, require_model

FIGURES = (
    ("fig2", "fig1", "Paper Figure 2: four configurations, candidate and selected gains"),
    ("fig3", "fig2", "Paper Figure 3: opponent payoffs and behavior probes"),
    ("figS2", "fig3", "Paper Figure 4: candidate distributions and S3 selections"),
    ("figS1", "fig4", "Paper Figure 5: S1/S2/S3 selection comparisons"),
    ("figS3", "fig5", "Paper Figure 6: fixed-pool policies and selection decomposition"),
    ("figS6", "fig6", "Paper Figure 7: parent-donor mismatch distances"),
    ("figS4", "fig7", "Supplementary opponent-family profiles"),
    ("figS5", "fig8", "Supplementary behavior and recovery probes"),
)
RAW_FOLDERS = ("requests_initial", "initial", "populations", "contexts", "requests_candidates",
               "candidates", "selection_scores", "holdout", "arm_logs", "attempt_history",
               "evaluation_history")
INPUT_FILES = {"manifest.json", "PROMPTS_SEALED.json", "SELECTIONS_SEALED.json"}
GENERATION_ROUNDS = 4
RETRY_COOLDOWN_SECONDS = 60


def now():
    return datetime.now(timezone.utc).isoformat()


def write(path, payload):
    write_json(path, payload)


def manifest_model(manifest):
    model = manifest.get("api", manifest).get("model", "")
    if not isinstance(model, str) or not model.strip():
        raise ValueError("Frozen manifest is missing its model identity")
    return model.strip()


def recorded_models(results):
    models = {}
    for run in RUNS:
        provider = "qwen" if "qwen" in run else "deepseek"
        model = manifest_model(read(Path(results) / run / "manifest.json"))
        if provider in models and models[provider] != model:
            raise ValueError(f"Frozen {provider} OFF/ON runs must use the same model")
        models[provider] = model
    return models


class Workflow:
    def __init__(self, args):
        self.args = args
        self.root = args.output.resolve()
        self.api = self.root / "api_call"
        self.analysis = self.root / "analysis"
        self.plot = self.root / "plot"
        self.env_file = Path(getattr(args, "env_file", ROOT / ".env")).resolve()
        offline = getattr(args, "steps", "all") in ("analysis", "plot")
        self.env = dict(os.environ) if offline else api_environment(self.env_file)
        self.env.update(PYTHONUTF8="1", PYTHONIOENCODING="utf-8", MPLBACKEND="Agg",
                        DIRECT_RECIPROCITY_API_DIRECT="1")
        self.state_path = self.root / "RUN_STATUS.json"
        saved = read(self.state_path) if self.state_path.exists() else None
        if offline:
            self.models = (dict(saved["models"]) if saved else recorded_models(
                (self.analysis if args.steps == "plot" else self.api) / "results"))
        else:
            self.models = {provider: require_model(provider, self.env) for provider in ("deepseek", "qwen")}
        if saved is not None and saved["models"] != self.models:
            raise ValueError("Existing output was created for different models; use matching .env settings or a new output directory")
        self.env.update({provider.upper() + "_MODEL": model for provider, model in self.models.items()})
        for folder in (self.api, self.analysis, self.plot):
            folder.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self.simulation_lock = threading.Lock()
        self.stop_event = threading.Event()
        self.state = saved if saved is not None else {
            "created_at": now(), "models": self.models, "planned_model_responses": 1680, "steps": {},
            "completed_stages": []}
        if self.state_path.exists():
            history = self.api / "logs" / "run_state_history" / f"run_{time.time_ns()}.json"
            write(history, self.state)
        for name in list(self.state["steps"]):
            if name.endswith("_all"):
                old = self.state["steps"].pop(name)
                old["superseded_by_phase_split"] = True
                self.state.setdefault("step_history", {}).setdefault(name, []).append(old)
        for key in ("error", "failed_at", "finished_at", "completed_steps", "full_workflow_complete"):
            self.state.pop(key, None)
        self.state.update(status="running", process_id=os.getpid(), updated_at=now())
        self.state["execution"] = {"api_workers_per_configuration": getattr(args, "api_workers", 12),
                                   "simulation_workers": getattr(args, "workers", 36),
                                   "parallel_followup_configurations": 3,
                                   "parallel_simulation_configurations": 1,
                                   "api_transport": "direct",
                                   "generation_rounds": GENERATION_ROUNDS,
                                   "generation_retry_cooldown_seconds": RETRY_COOLDOWN_SECONDS}
        self.persist()

    def persist(self):
        self.state["updated_at"] = now()
        write(self.state_path, self.state)

    def run_command(self, name, command, stage, resume=True):
        with self.lock:
            if self.stop_event.is_set():
                raise RuntimeError(f"Stopped before {name}: another follow-up failed")
            if resume and self.state["steps"].get(name, {}).get("status") == "passed":
                print(f"[cached] {name}", flush=True)
                return
            log = self.root / stage / "logs" / (name + ".log")
            log.parent.mkdir(parents=True, exist_ok=True)
            previous = self.state["steps"].get(name)
            if previous is not None:
                snapshot = json.loads(json.dumps(previous))
                self.state.setdefault("step_history", {}).setdefault(name, []).append(snapshot)
                write(log.parent / "step_history" / f"{name}_{time.time_ns()}.json", snapshot)
            entry = {"status": "running", "started_at": now(), "command": command,
                     "log": str(log.relative_to(self.root)),
                     "attempt": (previous or {}).get("attempt", 1 if previous else 0) + 1}
            self.state["steps"][name] = entry
            self.persist()
        print(f"[start] {name}", flush=True)
        try:
            with log.open("a", encoding="utf-8") as handle:
                handle.write(f"\n--- {now()} ---\n")
                handle.flush()
                result = subprocess.run(command, cwd=ROOT, env=self.env, stdout=handle, stderr=subprocess.STDOUT)
        except BaseException as exc:
            with self.lock:
                entry.update(status="interrupted" if isinstance(exc, KeyboardInterrupt) else "failed",
                             exit_code=None, launch_error=type(exc).__name__, error=str(exc), finished_at=now())
                self.persist()
            raise
        with self.lock:
            entry.update(status="passed" if result.returncode == 0 else "failed",
                         exit_code=result.returncode, finished_at=now())
            self.persist()
        if result.returncode:
            raise RuntimeError(f"{name} failed; inspect {log}")
        print(f"[passed] {name}", flush=True)

    def module(self, name, module, *args, stage="api_call", resume=True):
        self.run_command(name, [sys.executable, "-u", "-m", PREFIX + module, *map(str, args)], stage, resume)

    def archive_generation_status(self, destination, name, round_number):
        paths = [destination / "EXECUTION_STATUS.json", destination / "PROCESS.json"]
        paths += sorted(destination.glob("generate_*_errors.json"))
        existing = [path for path in paths if path.is_file()]
        if not existing:
            return None
        target = self.api / "logs" / "generation_history" / f"{name}_round{round_number}_{time.time_ns()}"
        target.mkdir(parents=True)
        for path in existing:
            shutil.copyfile(path, target / path.name)
        return str(target.relative_to(self.root))

    @staticmethod
    def retryable_generation_failure(destination):
        """Only saved, identified transport failures permit another dispatch round."""
        import httpx

        try:
            status = read(destination / "EXECUTION_STATUS.json")
            if not status.get("stage", "").startswith("generate_") or not status.get("errors"):
                return False, "Failure is not a recorded generation error"
            records = {path.stem: read(path) for path in (destination / "requests_candidates").glob("*.json")}
            failed = {key: record for key, record in records.items() if record.get("status") == "api_error"}
            if not failed:
                return False, "No saved API failure records"
            for identity, record in records.items():
                if record.get("status") not in ("valid", "invalid", "api_error"):
                    return False, f"Uncertain or unknown saved request status: {identity}"
            for identity, record in failed.items():
                code = record.get("http_status")
                transient_status = code in (408, 409, 429) or isinstance(code, int) and code >= 500
                transport = any(
                    item.get("module", "").startswith("httpx")
                    and isinstance(cls := getattr(httpx, item.get("type", ""), None), type)
                    and issubclass(cls, httpx.TransportError)
                    for item in record.get("exception_chain", []))
                if not (transient_status or transport):
                    return False, f"API failure is not confirmed retryable: {identity}"
            for error in status["errors"]:
                task = ast.literal_eval(error.get("task", ""))
                identity = task[1]["id"]
                if identity not in failed:
                    return False, f"Generation failed outside a saved API transport error: {identity}"
        except (OSError, ValueError, TypeError, KeyError, IndexError, SyntaxError, AttributeError) as exc:
            return False, f"Cannot verify generation failure: {type(exc).__name__}"
        return True, "All failed tasks have confirmed retryable API records"

    def generate(self, name, module, destination, *options):
        workers = self.args.api_workers
        if self.state["steps"].get(name, {}).get("status") == "passed":
            self.module(name, module, "generate", *options, "--api-workers", workers,
                        "--workers", self.args.workers)
            return
        for round_number in range(1, GENERATION_ROUNDS + 1):
            history = self.archive_generation_status(destination, name, round_number)
            try:
                self.module(name, module, "generate", *options, "--api-workers", workers,
                            "--workers", self.args.workers, resume=round_number == 1)
            except Exception:
                entry = self.state["steps"].get(name, {})
                retryable, reason = self.retryable_generation_failure(destination)
                if entry.get("exit_code") is None or entry.get("exit_code", 0) < 0:
                    retryable, reason = False, "Command did not finish with an ordinary failure exit"
                another_round = retryable and round_number < GENERATION_ROUNDS
                with self.lock:
                    entry.update(generation_round=round_number, api_workers=workers,
                                 prior_execution_history=history, automatic_retry=another_round,
                                 retry_reason=reason)
                    if another_round:
                        entry.update(next_api_workers=max(1, workers // 2),
                                     retry_cooldown_seconds=RETRY_COOLDOWN_SECONDS)
                    self.persist()
                if not another_round:
                    raise
                print(f"[retry] {name}: round {round_number + 1}/{GENERATION_ROUNDS}, "
                      f"workers={max(1, workers // 2)}, cooldown={RETRY_COOLDOWN_SECONDS}s", flush=True)
                if self.stop_event.wait(RETRY_COOLDOWN_SECONDS):
                    raise RuntimeError(f"Stopped retrying {name}: another follow-up failed")
                workers = max(1, workers // 2)
            else:
                with self.lock:
                    self.state["steps"][name].update(generation_round=round_number, api_workers=workers,
                                                    prior_execution_history=history)
                    self.persist()
                return

    @staticmethod
    def holdout_needs_recovery(destination, manifest):
        for job in manifest["jobs"]:
            path = destination / "holdout" / (job["id"] + ".json")
            if not path.is_file():
                return True
            row = read(path)
            if row.get("status") == "skipped" and row.get("skip_reason") == "parent_holdout_failed":
                return True
        return False

    @staticmethod
    def validate_holdouts(directory, manifest, run):
        parents = {context: read(directory / "holdout" / (context + ".json"))
                   for context in {job["context"] for job in manifest["jobs"]}}
        for context, parent in parents.items():
            for setting in ("default", "noise01", "behavior"):
                if not parent_available(parent, setting):
                    raise ValueError(f"Required parent holdout setting is unavailable: {run}/{context}/{setting}")
            if not parent_available(parent, "long") and parent.get("measured", {}).get("long", {}).get("status") != "failed":
                raise ValueError(f"Unexplained missing parent long measurement: {run}/{context}")
        holdouts = []
        for job in manifest["jobs"]:
            row = read(directory / "holdout" / (job["id"] + ".json"))
            issues = audit_deltas(row, parents[job["context"]], job["id"])
            if issues:
                raise ValueError(f"Invalid holdout at {run}: {issues[0]}")
            for setting in ("default", "noise01", "behavior"):
                if not setting_available(row, setting):
                    raise ValueError(f"Required child holdout setting is unavailable: {run}/{job['id']}/{setting}")
            if (not parent_available(parents[job["context"]], "long")
                    and "long" not in row.get("unavailable_settings", [])):
                raise ValueError(f"Missing explicit long-setting unavailability: {run}/{job['id']}")
            holdouts.append(row)
        return {"holdout_availability": availability(holdouts, parents),
                "parent_runtime_failures": [
                    {"context": context, "failed_settings": parent.get("failed_settings", [])}
                    for context, parent in parents.items() if parent.get("status") == "runtime_failure"]}

    def api_calls(self):
        off = self.api / "results" / RUNS[0]
        shared = ("--output", off, "--env-file", self.env_file)
        self.module("01_freeze", "specificity", "freeze", *shared,
                    "--arms", "score", "accurate", "mismatched")
        manifest = read(off / "manifest.json")
        if manifest_model(manifest) != self.models["deepseek"]:
            raise ValueError("Frozen initialization model differs from requested model")
        for phase in ("initialize", "prepare", "generate", "select", "holdout"):
            name = "02_deepseek_off_" + phase
            if phase == "generate":
                self.generate(name, "specificity", off, *shared)
            else:
                recover = phase == "holdout" and self.holdout_needs_recovery(off, manifest)
                self.module(name, "specificity", phase, *shared,
                            "--api-workers", self.args.api_workers, "--workers", self.args.workers,
                            resume=not recover)

        def followup(run, provider):
            destination = self.api / "results" / run
            label = run.replace("/", "_")
            options = ("--provider", provider, "--output", destination, "--source", off,
                       "--env-file", self.env_file)
            self.module(label + "_prepare", "paired_control", "prepare", *options)
            manifest = read(destination / "manifest.json")
            if manifest["api"]["model"] != self.models[provider]:
                raise ValueError("Frozen follow-up model differs from requested model")
            protocol = destination / "PROTOCOL.md"
            historical = destination / "HISTORICAL_PROTOCOL.md"
            if protocol.exists() and not historical.exists():
                shutil.copyfile(protocol, historical)
            protocol.write_text(
                f"# Fresh paired experiment\n\nModel: `{manifest['api']['model']}`.\n"
                f"Mode: `{manifest.get('mode', 'on')}`.\n"
                "20 populations, 60 parents, 360 candidate responses across Score, Accurate, Mismatched.\n"
                "All parents and prompts come from the new DeepSeek OFF run in this reproduction.\n"
                "S1/S2/S3 selections are sealed before independent H evaluation.\n"
                "Each request permits up to three transport retries. Generation permits at most four\n"
                "dispatch rounds with fewer workers and at least 60 seconds between failed rounds;\n"
                "only confirmed transport/status failures are retried. Failed attempts are archived.\n"
                "The frozen manifest records exact API settings. HISTORICAL_PROTOCOL.md is reference only.\n",
                encoding="utf-8")
            self.module(label + "_first", "paired_control", "first", *options)
            self.generate(label + "_generate", "paired_control", destination, *options)
            with self.simulation_lock:
                for phase in ("select", "holdout"):
                    recover = phase == "holdout" and self.holdout_needs_recovery(destination, manifest)
                    self.module(label + "_" + phase, "paired_control", phase, *options,
                                "--workers", self.args.workers, resume=not recover)

        with ThreadPoolExecutor(max_workers=3) as executor:
            pending = [executor.submit(followup, run, provider)
                       for run, provider in zip(RUNS[1:], ("deepseek", "qwen", "qwen"))]
            for future in as_completed(pending):
                try:
                    future.result()
                except BaseException:
                    self.stop_event.set()
                    for other in pending:
                        other.cancel()
                    raise
    @classmethod
    def audit_api(cls, api):
        """Inspect completed API records without creating or changing workflow state."""
        api = Path(api)
        models = recorded_models(api / "results")
        summaries = []
        total = 0
        for run in RUNS:
            directory = api / "results" / run
            manifest = read(directory / "manifest.json")
            read(directory / "COMPLETE.json")
            expected = models["qwen" if "qwen" in run else "deepseek"]
            requests = []
            for folder in ("requests_initial", "requests_candidates"):
                for path in sorted((directory / folder).glob("*.json")):
                    record = read(path)
                    if record["status"] not in ("valid", "invalid"):
                        raise ValueError(f"Unfinished API request: {path}")
                    if record.get("model") != expected or record.get("returned_model") != expected:
                        raise ValueError(f"Unexpected requested/returned model: {path}")
                    if record["started_at"] < manifest["frozen_at"]:
                        raise ValueError(f"Request predates this new manifest: {path}")
                    requests.append(record)
            wanted = 600 if run == RUNS[0] else 360
            if len(requests) != wanted:
                raise ValueError(f"Expected {wanted} new responses for {run}, found {len(requests)}")
            if len(read(directory / "SELECTIONS_SEALED.json")["rows"]) != 540:
                raise ValueError("Incomplete sealed selection decisions")
            for job in manifest["jobs"]:
                for folder in ("candidates", "selection_scores", "holdout"):
                    read(directory / folder / (job["id"] + ".json"))
            holdout_audit = cls.validate_holdouts(directory, manifest, run)
            total += len(requests)
            summaries.append({"run": run, "model": expected, "new_responses": len(requests),
                              "valid": sum(r["status"] == "valid" for r in requests),
                              "invalid": sum(r["status"] == "invalid" for r in requests),
                              **holdout_audit})
        if total != 1680:
            raise ValueError("Expected 1680 new model responses")
        return {"status": "passed", "new_responses": total,
              "checked_at": now(), "runs": summaries,
              "completion_note": "COMPLETE records task completion; unavailable parent long settings remain null with explicit reasons."}

    def analyze(self):
        for run in RUNS:
            source = self.api / "results" / run
            target = self.analysis / "results" / run
            target.mkdir(parents=True, exist_ok=True)
            for path in source.rglob("*"):
                relative = path.relative_to(source)
                if not path.is_file() or not (relative.parts[0] in RAW_FOLDERS
                        or relative.as_posix() in INPUT_FILES):
                    continue
                destination = target / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, destination)
        for name, command in commands(self.analysis, self.analysis, "analysis"):
            self.run_command(name, command, "analysis", resume=False)

    def plots(self):
        render = self.plot / "rendered"
        for name, command in commands(self.analysis, self.plot, "figures"):
            command = [str(render) if item == str(self.plot / "figures") else item for item in command]
            if name == "14_selection":
                pos = command.index("--figures")
                command.insert(pos + 2, "4")
            self.run_command(name, command, "plot", resume=False)
        self.module("16_opponent_supplement", "figures.plot_opponent_profiles", "--input",
                    self.analysis / "results/figure4_opponent_profiles_20260926/ANALYSIS_reproduct.json",
                    "--output-dir", render, stage="plot", resume=False)
        exports = []
        for source, stem, description in FIGURES:
            files = []
            for extension in ("png", "pdf", "svg"):
                path = render / f"{source}.{extension}"
                if not path.is_file() or path.stat().st_size == 0:
                    raise FileNotFoundError(path)
                target = self.plot / f"{stem}.{extension}"
                shutil.copyfile(path, target)
                files.append({"path": target.name})
            exports.append({"figure": stem, "source_stem": source, "description": description, "files": files})
        write(self.plot / "FIGURES_MANIFEST.json", {"status": "passed", "models": self.models,
              "created_at": now(), "new_data_only": True, "figures": exports,
              "excluded": "The original Paper Figure 1 is a static method diagram, not a data plot."})

    def document(self):
        text = f"""# Full new API reproduction

Models: `{self.models['deepseek']}` and `{self.models['qwen']}`, each with thinking OFF/ON.
New API runs read `DEEPSEEK_MODEL` and `QWEN_MODEL` from `--env-file` (default `.env`).
File settings take precedence over inherited environment settings; missing model
configuration is an error. Existing API runs must retain their frozen models.
Full design: 20 populations (seeds 200–219), 60 parents, 240 initialization
responses and 1,440 candidate responses; 1,680 planned model responses.
Conditions: Score, Accurate, Mismatched. Invalid programs retain the parent
according to the original protocol; API errors do not count as responses.
If a parent cannot be measured in one test setting, its paired gain in that
setting is undefined. Other settings remain available. Analysis and tables
report the evaluable matched contexts; undefined gains are never set to zero.

- `api_call/`: canonical new requests, responses, streams, programs, games,
  sealed selections and execution logs.
- `analysis/`: analysis results, CSV/TeX tables and local raw
  input copies needed by the existing analyzers.
- `plot/fig1.*` through `fig8.*`: all new-data plots in PNG/PDF/SVG.
  `FIGURES_MANIFEST.json` maps these to the paper and supplementary plots.
- `RUN_STATUS.json`: actual stage status; `passed` confirms completion.

The internal `results/qwen3_8` and date-stamped folder names are compatibility
paths used by the original analysis code. The frozen manifests and request
records identify the actual models above. No archived responses or figures
are substituted. The paper's static method schematic is excluded.

Run or resume from the repository root:

```powershell
uv run python -m tools.run_fresh_reproduction --output reproduction
```

Use `--steps api_call`, `--steps analysis` or `--steps plot` to run one stage.
Audits run separately with `--steps audit`; their JSON report is printed to stdout
without changing the running experiment's files or stage status.
Successful requests are reused on resume. Inspect uncertain requests before
retrying; transport retries can make the actual attempt count exceed 1,680.
API generation starts with 12 workers per configuration. Confirmed generation
failures permit at most four rounds (12, 6, 3, 1 workers), with at least 60
seconds of cooldown. Follow-up generation can overlap; selection and holdout
run one configuration at a time using all 36 simulation workers by default.
If a parent fails only the long-match setting, that setting remains explicitly
unavailable; successful default, noise and behavior measurements are retained.
"""
        (self.root / "README.md").write_text(text, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "reproduction")
    parser.add_argument("--steps", choices=("all", "api_call", "analysis", "plot", "audit"), default="all")
    parser.add_argument("--api-workers", type=int, default=12)
    parser.add_argument("--workers", type=int, default=36)
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    args = parser.parse_args()
    if args.steps == "audit":
        print(json.dumps(Workflow.audit_api(args.output.resolve() / "api_call"), indent=2))
        return
    if min(args.workers, args.api_workers) < 1:
        parser.error("Worker counts must be positive")
    workflow = Workflow(args)
    workflow.document()
    try:
        for stage, operation in (("api_call", workflow.api_calls), ("analysis", workflow.analyze),
                                 ("plot", workflow.plots)):
            if args.steps in ("all", stage):
                workflow.state["current_stage"] = stage
                workflow.persist()
                operation()
                completed = set(workflow.state.get("completed_stages", []))
                completed.add(stage)
                workflow.state["completed_stages"] = sorted(completed)
                workflow.persist()
        workflow.state.update(status="passed", completed_steps=args.steps, finished_at=now(),
                              full_workflow_complete=set(workflow.state.get("completed_stages", []))
                              == {"api_call", "analysis", "plot"})
    except BaseException as exc:
        workflow.state.update(status="interrupted" if isinstance(exc, KeyboardInterrupt) else "failed",
                              error=str(exc) or type(exc).__name__, failed_at=now())
        raise
    finally:
        workflow.persist()


if __name__ == "__main__":
    main()
