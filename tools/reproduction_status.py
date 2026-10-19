"""Refresh an offline reproduction checkpoint without changing experiment records."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import time

ROOT = Path(__file__).resolve().parents[1]
CONFIGURATIONS = {
    "DeepSeek/OFF": "feedback_specificity_v2",
    "DeepSeek/ON": "feedback_specificity_thinking_384k_20260923",
    "Qwen/OFF": "qwen3_8/off",
    "Qwen/ON": "qwen3_8/on",
}


def read_json(path, warnings, *, optional=False):
    """A writer or Windows scanner can briefly hide an atomically replaced file."""
    error_name = None
    for attempt in range(4):
        try:
            return json.loads(path.read_text(encoding="utf-8-sig"))
        except (FileNotFoundError, PermissionError, json.JSONDecodeError) as exc:
            error_name = type(exc).__name__
            if attempt < 3:
                time.sleep(.02 * 2 ** attempt)
    if not optional:
        warnings.append({"path": str(path), "error": error_name})
    return None


def pid_alive(pid):
    if not isinstance(pid, int) or pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
        kernel.GetExitCodeProcess.restype = wintypes.BOOL
        kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
        handle = kernel.OpenProcess(0x1000, False, pid)  # QUERY_LIMITED_INFORMATION
        if not handle:
            return False if ctypes.get_last_error() == 87 else None
        try:
            exit_code = wintypes.DWORD()
            return exit_code.value == 259 if kernel.GetExitCodeProcess(handle, ctypes.byref(exit_code)) else None
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return None
    return True


def request_statuses(directory, warnings):
    counts = Counter()
    try:
        paths = list(directory.glob("*.json"))
    except (FileNotFoundError, PermissionError) as exc:
        warnings.append({"path": str(directory), "error": type(exc).__name__})
        paths = []
    for path in paths:
        record = read_json(path, warnings)
        if record is not None:
            counts[record.get("status", "unknown")] += 1
    return counts


def checkpoint(output):
    warnings = []
    state = read_json(output / "RUN_STATUS.json", warnings) or {}
    configurations, totals = {}, Counter()
    for label, relative in CONFIGURATIONS.items():
        root = output / "api_call/results" / relative
        manifest = read_json(root / "manifest.json", warnings, optional=True) or {}
        folders, combined = {}, Counter()
        for folder in ("requests_initial", "requests_candidates"):
            counts = request_statuses(root / folder, warnings)
            folders[folder] = dict(counts)
            combined.update(counts)
        totals.update(combined)
        initial_plan = len(manifest.get("init_jobs", [])) if label == "DeepSeek/OFF" else 0
        planned = (initial_plan or (240 if label == "DeepSeek/OFF" else 0)) + len(manifest.get("jobs", []))
        if "jobs" not in manifest:
            planned += 360
        execution = read_json(root / "EXECUTION_STATUS.json", warnings, optional=True) or {}
        configurations[label] = {
            "path": relative,
            "model": manifest.get("api", {}).get("model") or manifest.get("model"),
            "planned_responses": planned,
            "requests_saved": sum(combined.values()),
            "terminal_responses": combined["valid"] + combined["invalid"],
            "response_statuses": dict(combined),
            "requests_initial": folders["requests_initial"],
            "requests_candidates": folders["requests_candidates"],
            "execution_status": {"stage": execution.get("stage"), "completed": execution.get("completed"),
                                 "total": execution.get("total"), "errors": len(execution.get("errors", []))},
        }
    figures = {}
    for number in range(1, 9):
        stem = f"fig{number}"
        formats = {}
        for extension in ("png", "pdf", "svg"):
            path = output / "plot" / f"{stem}.{extension}"
            try:
                formats[extension] = path.is_file()
            except (FileNotFoundError, PermissionError) as exc:
                formats[extension] = False
                warnings.append({"path": str(path), "error": type(exc).__name__})
        figures[stem] = {"formats": formats, "all_formats_exist": all(formats.values())}
    partial = read_json(output / "plot/PARTIAL_FIGURES_MANIFEST.json", warnings, optional=True) or {}
    final = read_json(output / "plot/FIGURES_MANIFEST.json", warnings, optional=True) or {}
    all_files = all(row["all_formats_exist"] for row in figures.values())
    final_passed = final.get("status") == "passed"
    ready = [name for name, row in figures.items() if row["all_formats_exist"]]
    terminal = totals["valid"] + totals["invalid"]
    planned = state.get("planned_model_responses", 1680)
    runner_pid = state.get("process_id")
    return {
        "status": state.get("status", "unknown"),
        "updated_at": datetime.now(timezone(timedelta(hours=8))).isoformat(),
        "updated_at_epoch": time.time(),
        "planned_experimental_responses": planned,
        "experimental_responses_saved": terminal,
        "remaining_experimental_responses": max(0, planned - terminal),
        "requests_saved": sum(totals.values()),
        "response_statuses": {name: totals[name] for name in ("valid", "invalid", "requested", "received", "api_error")}
                             | {name: count for name, count in totals.items()
                                if name not in ("valid", "invalid", "requested", "received", "api_error")},
        "configurations": configurations,
        "current_stages": [name for name, step in state.get("steps", {}).items() if step.get("status") == "running"],
        "runner": {"process_id": runner_pid, "alive": pid_alive(runner_pid),
                   "state_updated_at": state.get("updated_at"), "execution": state.get("execution", {})},
        "plot": {"delivery_status": "final" if final_passed and all_files else "partial" if ready else "pending",
                 "ready_figures": ready, "planned_figures": 8, "figures": figures,
                 "partial_manifest_status": partial.get("status"),
                 "final_manifest_status": final.get("status"), "final_manifest_passed": final_passed,
                 "all_formats_exist": all_files},
        "final_figures_exist": final_passed and all_files,
        "read_warnings": warnings,
        "note": "Counts use latest experimental request records; archived retry attempts are excluded. "
                "Valid and invalid are terminal responses. Figure files remain partial until the final manifest passes.",
    }


def write_checkpoint(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for attempt in range(8):
        try:
            temporary.replace(path)
            return
        except (FileNotFoundError, PermissionError):
            if attempt == 7:
                raise
            time.sleep(min(.02 * 2 ** attempt, .5))


def refresh(output):
    snapshot = checkpoint(output)
    write_checkpoint(output / "api_call/CHECKPOINT.json", snapshot)
    print(json.dumps({"status": snapshot["status"], "responses": snapshot["experimental_responses_saved"],
                      "planned": snapshot["planned_experimental_responses"], "statuses": snapshot["response_statuses"],
                      "runner_alive": snapshot["runner"]["alive"], "figures": snapshot["plot"]["ready_figures"],
                      "figure_delivery": snapshot["plot"]["delivery_status"]}), flush=True)
    return snapshot


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "reproduction")
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--interval", type=float, default=60.)
    args = parser.parse_args()
    if args.interval <= 0:
        parser.error("interval must be positive")
    output = args.output.resolve()
    try:
        while True:
            snapshot = refresh(output)
            if not args.watch:
                return
            if snapshot["status"] != "running" or snapshot["runner"]["alive"] is not True:
                refresh(output)
                return
            time.sleep(args.interval)
    except KeyboardInterrupt:
        refresh(output)


if __name__ == "__main__":
    main()
