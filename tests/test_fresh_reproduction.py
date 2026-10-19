"""Fresh-run provenance and Windows record durability; no network requests."""
from argparse import Namespace
import json
from pathlib import Path
import threading
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from experiments.direct_reciprocity import records
from tools.run_fresh_reproduction import Workflow
from tools import run_fresh_reproduction as fresh


def test_atomic_record_rename_retries_without_repeating_generation(tmp_path):
    path = tmp_path / "response.json"
    original = Path.replace
    calls = []

    def temporarily_locked(source, target):
        calls.append(target)
        if len(calls) < 3:
            raise PermissionError("File is temporarily locked")
        return original(source, target)

    with patch.object(Path, "replace", temporarily_locked), patch.object(records.time, "sleep"):
        records.write_json(path, {"status": "valid", "response_id": "already-paid-response"})
    assert records.read_json(path)["response_id"] == "already-paid-response"
    assert len(calls) == 3
    assert not path.with_suffix(".json.tmp").exists()


def test_plot_stage_refuses_missing_analysis_instead_of_using_archives(tmp_path):
    workflow = Workflow(Namespace(output=tmp_path / "fresh"))
    with patch("tools.run_fresh_reproduction.subprocess.run") as execute:
        with pytest.raises(RuntimeError, match="Complete the analysis"):
            workflow.plots()
    execute.assert_not_called()


def test_fresh_validation_rejects_incomplete_api_before_analysis(tmp_path):
    workflow = Workflow(Namespace(output=tmp_path / "fresh"))
    with patch("tools.run_fresh_reproduction.subprocess.run") as execute:
        with pytest.raises(FileNotFoundError):
            workflow.analyze()
    execute.assert_not_called()
    assert not (workflow.analysis / "VALIDATION.json").exists()


def arguments(tmp_path):
    return Namespace(output=tmp_path / "fresh", api_workers=12, workers=36,
                     env_file=tmp_path / ".env")


def save_generation_error(destination, *, code=429, chain=None, stage="generate_score", identity="retry"):
    records.write_json(destination / "requests_candidates/retry.json", {
        "status": "api_error", "http_status": code, "exception_chain": chain or []})
    errors = [{"type": "RuntimeError", "message": "offline request failure",
               "task": repr((str(destination), {"id": identity}))}]
    records.write_json(destination / "EXECUTION_STATUS.json", {
        "stage": stage, "completed": 0, "total": 120, "errors": errors})
    records.write_json(destination / "generate_score_errors.json", errors)


def test_resume_archives_old_failure_and_preserves_step_history(tmp_path):
    args = arguments(tmp_path)
    first = Workflow(args)
    first.state.update(status="failed", error="old failure", failed_at="yesterday")
    first.state["steps"]["example"] = {"status": "failed", "exit_code": 1, "log": "api_call/logs/example.log"}
    first.persist()
    workflow = Workflow(args)
    assert workflow.state["status"] == "running"
    assert "error" not in workflow.state and "failed_at" not in workflow.state
    assert workflow.state["steps"]["example"]["status"] == "failed"
    snapshots = list((workflow.api / "logs/run_state_history").glob("*.json"))
    assert len(snapshots) == 1 and records.read_json(snapshots[0])["error"] == "old failure"
    with patch.object(fresh.subprocess, "run", return_value=SimpleNamespace(returncode=0)):
        workflow.run_command("example", ["offline"], "api_call")
    assert workflow.state["step_history"]["example"][0]["status"] == "failed"
    assert workflow.state["steps"]["example"]["status"] == "passed"
    assert {path.name for path in workflow.root.iterdir() if path.is_dir()} == {"api_call", "analysis", "plot"}
    assert workflow.env["DIRECT_RECIPROCITY_API_DIRECT"] == "1"
    assert workflow.state["execution"]["api_transport"] == "direct"


@pytest.mark.parametrize("failures", [3, 4])
def test_generation_rounds_reduce_workers_and_keep_failures(tmp_path, monkeypatch, failures):
    workflow = Workflow(arguments(tmp_path))
    destination = workflow.api / "results/offline"
    save_generation_error(destination)
    for identity, status in (("valid", "valid"), ("invalid", "invalid")):
        records.write_json(destination / f"requests_candidates/{identity}.json", {"status": status, "paid": True})
    originals = {path: path.read_bytes() for path in (destination / "requests_candidates").glob("*.json")
                 if path.stem != "retry"}
    worker_counts, cooldowns = [], []

    def execute(command, **kwargs):
        worker_counts.append(int(command[command.index("--api-workers") + 1]))
        assert kwargs["env"]["DIRECT_RECIPROCITY_API_DIRECT"] == "1"
        assert all(path.read_bytes() == content for path, content in originals.items())
        kwargs["stdout"].write(f"offline round {len(worker_counts)}\n")
        if len(worker_counts) <= failures:
            save_generation_error(destination)
            return SimpleNamespace(returncode=1)
        records.write_json(destination / "requests_candidates/retry.json", {"status": "valid"})
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(fresh.subprocess, "run", execute)
    monkeypatch.setattr(workflow.stop_event, "wait", lambda seconds: cooldowns.append(seconds) or False)
    if failures == 4:
        with pytest.raises(RuntimeError, match="generate failed"):
            workflow.generate("generate", "paired_control", destination, "--output", destination)
    else:
        workflow.generate("generate", "paired_control", destination, "--output", destination)
    assert worker_counts == [12, 6, 3, 1]
    assert cooldowns == [60, 60, 60]
    assert len(workflow.state["step_history"]["generate"]) == 3
    assert all(row["status"] == "failed" for row in workflow.state["step_history"]["generate"])
    assert len(list((workflow.api / "logs/generation_history").glob("*/EXECUTION_STATUS.json"))) == 4
    assert (workflow.api / "logs/generate.log").read_text().count("offline round") == 4
    final = workflow.state["steps"]["generate"]
    assert final["generation_round"] == 4
    assert final["status"] == ("failed" if failures == 4 else "passed")
    if failures == 4:
        assert final["automatic_retry"] is False


@pytest.mark.parametrize("code", [408, 409, 429, 503])
def test_generation_retry_accepts_only_confirmed_http_failures(tmp_path, code):
    save_generation_error(tmp_path, code=code)
    assert Workflow.retryable_generation_failure(tmp_path)[0]


def test_generation_retry_accepts_wrapped_httpx_transport_error(tmp_path):
    save_generation_error(tmp_path, code=None, chain=[
        {"module": "openai", "type": "APIConnectionError"},
        {"module": "httpx", "type": "ReadError"}])
    assert Workflow.retryable_generation_failure(tmp_path)[0]


@pytest.mark.parametrize("case", ["400", "unknown_type", "requested", "received", "wrong_stage", "missing_task", "no_failure"])
def test_generation_retry_rejects_uncertain_or_unrelated_failure(tmp_path, case):
    save_generation_error(tmp_path)
    if case in ("400", "unknown_type"):
        save_generation_error(tmp_path, code=400 if case == "400" else None,
                              chain=[{"module": "httpx", "type": "HTTPStatusError"}])
    elif case in ("requested", "received"):
        records.write_json(tmp_path / "requests_candidates/uncertain.json", {"status": case})
    elif case == "wrong_stage":
        save_generation_error(tmp_path, stage="select")
    elif case == "missing_task":
        save_generation_error(tmp_path, identity="unsaved")
    elif case == "no_failure":
        records.write_json(tmp_path / "requests_candidates/retry.json", {"status": "valid"})
    assert Workflow.retryable_generation_failure(tmp_path)[0] is False


def test_command_launch_failure_keeps_accurate_status_and_does_not_retry(tmp_path, monkeypatch):
    workflow = Workflow(arguments(tmp_path))
    destination = workflow.api / "results/offline"
    save_generation_error(destination)
    with patch.object(fresh.subprocess, "run", side_effect=OSError("offline launch failure")) as execute:
        with patch.object(workflow.stop_event, "wait") as cooldown:
            with pytest.raises(OSError, match="launch failure"):
                workflow.generate("generate", "paired_control", destination)
    assert execute.call_count == 1
    cooldown.assert_not_called()
    entry = workflow.state["steps"]["generate"]
    assert entry["status"] == "failed" and entry["exit_code"] is None
    assert entry["automatic_retry"] is False and entry["launch_error"] == "OSError"


def test_completed_generation_resumes_without_dispatch_or_changing_original_metadata(tmp_path):
    workflow = Workflow(arguments(tmp_path))
    previous = {"status": "passed", "api_workers": 80, "attempt": 1, "command": ["old invocation"]}
    workflow.state["steps"]["generate"] = previous.copy()
    with patch.object(fresh.subprocess, "run") as execute:
        workflow.generate("generate", "paired_control", workflow.api / "results/offline")
    execute.assert_not_called()
    assert workflow.state["steps"]["generate"] == previous
    assert not (workflow.api / "logs/generation_history").exists()


def test_followup_generation_overlaps_but_simulation_is_serial(tmp_path, monkeypatch):
    workflow = Workflow(arguments(tmp_path))
    off = workflow.api / "results" / fresh.RUNS[0]
    manifest = {"seeds": list(range(200, 220)), "jobs": [
        {"id": f"child{i}", "context": "parent"} for i in range(360)]}
    records.write_json(off / "manifest.json", manifest)
    records.write_json(off / "holdout/child0.json", {"status": "skipped", "skip_reason": "parent_holdout_failed"})
    workflow.state["steps"]["02_deepseek_off_holdout"] = {"status": "passed"}
    for run, provider in zip(fresh.RUNS[1:], ("deepseek", "qwen", "qwen")):
        records.write_json(workflow.api / "results" / run / "manifest.json",
                           {**manifest, "api": {"model": fresh.MODELS[provider]}})
    barrier, lock = threading.Barrier(3), threading.Lock()
    calls, generating, simulating = [], [], []

    def generate(name, module, destination, *options):
        if name.startswith("02_"):
            return
        with lock:
            generating.append(name)
        barrier.wait(timeout=5)

    def module(name, module_name, phase, *options, **kwargs):
        with lock:
            calls.append((name, module_name, phase, options, kwargs))
        if module_name == "paired_control" and phase in ("select", "holdout"):
            with lock:
                simulating.append(name)
                assert len(simulating) == 1
            assert int(options[options.index("--workers") + 1]) == 36
            threading.Event().wait(.01)
            with lock:
                simulating.remove(name)

    monkeypatch.setattr(workflow, "generate", generate)
    monkeypatch.setattr(workflow, "module", module)
    monkeypatch.setattr(workflow, "validate_api", lambda: None)
    workflow.api_calls()
    assert len(generating) == 3
    assert all(phase != "all" for _, _, phase, _, _ in calls)
    holdout = next(row for row in calls if row[0] == "02_deepseek_off_holdout")
    assert holdout[4]["resume"] is False
    for run in fresh.RUNS[1:]:
        label = run.replace("/", "_")
        assert [phase for name, _, phase, _, _ in calls if name.startswith(label)] == ["prepare", "first", "select", "holdout"]


def holdout_fixture(tmp_path):
    manifest = {"jobs": [{"id": "child", "context": "parent"}]}
    metric = {"status": "ok", "score": 2., "cooperation": .5, "worst_score": 1.}
    parent = {"status": "runtime_failure", "failed_settings": ["long"],
              "measured": {"default": metric, "noise01": metric,
                           "long": {"status": "failed", "error_type": "PolicyError"},
                           "behavior": {"status": "ok", "probes": {}}}}
    child = {"id": "child", "context": "parent", "seed": 200, "status": "complete",
             "deployed": {"default": metric, "noise01": metric, "long": None,
                          "behavior": {"status": "ok", "probes": {}}},
             "fallback": {"default": False, "noise01": False, "long": None},
             "delta": {setting: {key: None if setting == "long" else 0.
                                  for key in ("score", "cooperation", "worst_score")}
                       for setting in ("default", "noise01", "long")},
             "missing_reasons": {"long": {"reason": "parent_measurement_failed"}},
             "unavailable_settings": ["long"]}
    records.write_json(tmp_path / "holdout/parent.json", parent)
    records.write_json(tmp_path / "holdout/child.json", child)
    return manifest, parent, child


def test_holdout_validation_keeps_partial_parent_failure_and_reports_counts(tmp_path):
    manifest, parent, _ = holdout_fixture(tmp_path)
    before = (tmp_path / "holdout/parent.json").read_bytes()
    result = Workflow.validate_holdouts(tmp_path, manifest, "offline")
    assert result["holdout_availability"]["default"]["n_candidate_observations"] == 1
    assert result["holdout_availability"]["long"]["n_candidate_observations"] == 0
    assert result["parent_runtime_failures"] == [{"context": "parent", "failed_settings": ["long"]}]
    assert (tmp_path / "holdout/parent.json").read_bytes() == before
    assert Workflow.holdout_needs_recovery(tmp_path, manifest) is False
    assert "evaluation_history" in fresh.RAW_FOLDERS


@pytest.mark.parametrize("case", ["skipped", "missing_default", "zero_long", "missing_unavailable", "bad_delta"])
def test_holdout_validation_rejects_unrecovered_or_misrepresented_data(tmp_path, case):
    manifest, parent, child = holdout_fixture(tmp_path)
    if case == "skipped":
        child.update(status="skipped", skip_reason="parent_holdout_failed")
    elif case == "missing_default":
        parent["measured"]["default"] = {"status": "failed"}
    elif case == "zero_long":
        child["delta"]["long"]["score"] = 0.
    elif case == "missing_unavailable":
        child["unavailable_settings"] = []
    else:
        child["delta"]["default"]["score"] = 1.
    records.write_json(tmp_path / "holdout/parent.json", parent)
    records.write_json(tmp_path / "holdout/child.json", child)
    with pytest.raises(ValueError):
        Workflow.validate_holdouts(tmp_path, manifest, "offline")
    if case == "skipped":
        assert Workflow.holdout_needs_recovery(tmp_path, manifest)


def test_plot_plan_collects_all_eight_new_data_figures_in_three_formats(tmp_path, monkeypatch):
    """Exercise the real command plan/collector without running models or renderers."""
    workflow = Workflow(arguments(tmp_path))
    records.write_json(workflow.analysis / "VALIDATION.json", {"status": "passed"})
    commands = []
    sources = {
        "12_main_figures": ("fig2", "fig3"),
        "13_candidate_distribution": ("figS2",),
        "14_selection": ("figS1", "figS5", "figS3"),
        "15_distance_figure": ("figS6",),
        "16_opponent_supplement": ("figS4",),
    }
    data_arguments = ("--work", "--cross-model", "--deepseek-off", "--deepseek-on",
                      "--qwen-off-manifest", "--qwen-off-analysis", "--qwen-on-manifest",
                      "--qwen-on-analysis", "--opponent-profiles", "--behavior-analysis",
                      "--input", "--off-analysis", "--off-role-analysis", "--on-analysis")

    def execute(name, command, stage, resume=True):
        commands.append(name)
        assert stage == "plot" and resume is False
        output = Path(command[command.index("--output-dir") + 1])
        assert output == workflow.plot / "rendered"
        assert Path(command[command.index("--audit-dir") + 1]) == workflow.plot / "audit"
        for flag in data_arguments:
            if flag in command:
                assert Path(command[command.index(flag) + 1]).is_relative_to(workflow.analysis)
        if "--inputs" in command:
            index = command.index("--inputs")
            assert all(Path(path).is_relative_to(workflow.analysis) for path in command[index + 1:index + 3])
        if name == "14_selection":
            assert command[command.index("--figures") + 1:command.index("--output-dir")] == ["3", "4", "5"]
        output.mkdir(parents=True, exist_ok=True)
        for stem in sources[name]:
            for extension in ("png", "pdf", "svg"):
                (output / f"{stem}.{extension}").write_bytes(f"new-data-{stem}-{extension}".encode())

    monkeypatch.setattr(workflow, "run_command", execute)
    workflow.plots()
    assert commands == list(sources)
    report = records.read_json(workflow.plot / "FIGURES_MANIFEST.json")
    assert report["status"] == "passed" and report["new_data_only"] is True
    assert report["models"] == {"deepseek": "deepseek-flash", "qwen": "qwen3.7-flash"}
    assert [row["figure"] for row in report["figures"]] == [f"fig{i}" for i in range(1, 9)]
    assert sum(len(row["files"]) for row in report["figures"]) == 24
    for source, target, _ in fresh.FIGURES:
        for extension in ("png", "pdf", "svg"):
            assert (workflow.plot / f"{target}.{extension}").read_bytes() == f"new-data-{source}-{extension}".encode()
