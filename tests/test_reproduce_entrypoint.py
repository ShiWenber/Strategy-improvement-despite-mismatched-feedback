"""Check offline workflow contracts independently of the archived statistics."""
from pathlib import Path

import pytest

from tools import reproduce
from experiments.direct_reciprocity.specificity_analysis import selected_seed_gains


def test_work_directory_is_used_by_every_data_consumer(tmp_path):
    plan = dict(reproduce.commands(tmp_path, tmp_path / "exports", "all"))
    for step in ("05_population", "06_opponents", "07_behavior", "09_cross_model", "12_main_figures"):
        command = plan[step]
        assert command[command.index("--work") + 1] == str(tmp_path)
    behavior = plan["07_behavior"]
    assert behavior[behavior.index("--off-root") + 1] == str(tmp_path / "results" / reproduce.RUNS[0])
    assert behavior[behavior.index("--on-root") + 1] == str(tmp_path / "results" / reproduce.RUNS[1])
    plotting = plan["12_main_figures"]
    assert "model_comparison_20260928" in plotting[plotting.index("--cross-model") + 1]


def test_offline_workflow_only_contains_analysis_and_rendering(tmp_path):
    modules = {command[2] for _, command in reproduce.commands(tmp_path, tmp_path / "exports", "all")}
    assert modules.isdisjoint({reproduce.PREFIX + name for name in
                              ("specificity", "paired_control", "condition_generation", "run")})
    assert len(modules) == 14


def test_preflight_fails_before_any_work_for_missing_archive(tmp_path):
    with pytest.raises(FileNotFoundError):
        reproduce.preflight(tmp_path)


def test_export_normalization_supports_output_outside_work_directory(tmp_path):
    work, output = tmp_path / 'work', tmp_path / 'exports'
    tables = output / 'tables'
    tables.mkdir(parents=True)
    generated = tables / 'tableI_reproduct.csv'
    generated.write_bytes(b'column\r\nvalue\r\n')
    original = tables / 'original.csv'
    original.write_bytes(b'original\r\n')
    reproduce.normalize_generated_outputs(work, output)
    assert generated.read_bytes() == b'column\nvalue\n'
    assert original.read_bytes() == b'original\r\n'


def test_latest_paper_snapshot_uses_continuous_numbering_and_valid_hashes():
    snapshot = reproduce.preflight(reproduce.ROOT)
    assert [row["number"] for row in snapshot["figures"]] == list(range(1, 8))
    assert [row["number"] for row in snapshot["tables"]] == ["I", "II", "III", "IV", "V"]


def test_bundle_includes_protocols_reference_exports_and_report_fixtures():
    from tools.package_reproduction import bundle_files
    files = {path.relative_to(reproduce.ROOT).as_posix() for path in bundle_files()}
    assert {
        'results/qwen3_8/PROTOCOL.md',
        'results/model_comparison_20260928/score_baseline_data_reproduct.json',
        'results/model_comparison_20260928/cross_model_mainline_data_reproduct.json',
        'results/model_comparison_20260928/candidate_gains_reproduct.csv',
        'results/mismatch_detection_jev/jev_recount_reproduct.json',
        'results/mismatch_detection_jev/REPORT.md',
        'results/mismatch_detection_jev/REPORT_reproduct.md',
        'docs/direct_reciprocity/MISMATCH_DISTANCE_ANALYSIS.md',
        'docs/direct_reciprocity/MISMATCH_DISTANCE_ANALYSIS_reproduct.md',
        'docs/direct_reciprocity/mismatch_distance/mismatch_distance_thinking_off_reproduct.json',
        'docs/direct_reciprocity/mismatch_distance/mismatch_distance_thinking_on_reproduct.json',
    } <= files
    assert not any(Path(name).name == '.env' or '.git' in Path(name).parts
                   or 'paper_interface_focus' in Path(name).parts for name in files)


def test_selected_output_mean_includes_retained_parent_slots_and_test_losses():
    winners = [{"seed": 200, "winner": "improved"}, {"seed": 200, "winner": None},
               {"seed": 200, "winner": "test_loss"}, {"seed": 201, "winner": None}]
    measured = {"improved": {"delta": {"default": {"score": 0.3}}},
                "test_loss": {"delta": {"default": {"score": -0.06}}}}
    assert selected_seed_gains(winners, measured, [200, 201], "default") == pytest.approx([0.08, 0.0])
    with pytest.raises(KeyError):
        selected_seed_gains(winners, {}, [200, 201], "default")
