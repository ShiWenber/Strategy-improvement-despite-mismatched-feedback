"""Check offline workflow contracts independently of the archived statistics."""
from pathlib import Path

import pytest

from tools import reproduce
from experiments.direct_reciprocity.specificity_analysis import selected_seed_gains


def test_work_directory_is_used_by_every_data_consumer(tmp_path):
    plan = dict(reproduce.commands(tmp_path, tmp_path / "exports", "all"))
    for step in ("05_population", "06_opponents", "09_cross_model"):
        command = plan[step]
        assert command[command.index("--work") + 1] == str(tmp_path)
    behavior = plan["07_behavior"]
    assert behavior[behavior.index("--off-root") + 1] == str(tmp_path / "results" / reproduce.RUNS[0])
    assert behavior[behavior.index("--on-root") + 1] == str(tmp_path / "results" / reproduce.RUNS[1])
    plotting = plan["12_main_figures"]
    assert "--work" not in plotting and "--figure1" not in plotting
    assert "model_comparison_20260928" in plotting[plotting.index("--cross-model") + 1]


def test_offline_workflow_only_contains_analysis_and_rendering(tmp_path):
    plan = reproduce.commands(tmp_path, tmp_path / "exports", "all")
    modules = {command[2] for _, command in plan}
    assert modules.isdisjoint({reproduce.PREFIX + name for name in
                              ("specificity", "paired_control", "condition_generation", "run")})
    assert len(modules) == 14
    assert all("--audit-dir" not in command and "--audit-only" not in command for _, command in plan)


def test_reproduction_does_not_run_archive_audit(tmp_path, monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr("sys.argv", ["reproduce", "--work", str(tmp_path), "--steps", "analysis"])
    monkeypatch.setattr(reproduce, "commands", lambda *args: [("analysis", ["offline-analysis"])])
    monkeypatch.setattr(reproduce, "preflight", lambda *args: pytest.fail("archive audit ran"))
    monkeypatch.setattr(reproduce.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=0))

    reproduce.main()

    report = reproduce.read(tmp_path / "results/reproduction/latest/RUN_REPORT.json")
    assert report["status"] == "passed"


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


def test_preflight_uses_archive_without_manuscript_metadata(tmp_path, monkeypatch):
    work = reproduce.ROOT
    monkeypatch.setattr(reproduce, "ROOT", tmp_path)
    reproduce.preflight(work)


def test_package_accepts_step_report_and_writes_only_requested_zip(tmp_path, monkeypatch):
    import json
    import zipfile
    from tools import package_reproduction as package

    report = tmp_path / "results/reproduction/latest/RUN_REPORT.json"
    report.parent.mkdir(parents=True)
    report.write_text(json.dumps({"status": "passed", "requested_steps": "all"}), encoding="utf-8")
    source = tmp_path / "README.md"
    source.write_text("Example release\n", encoding="utf-8")
    destination = tmp_path / "release/bundle.zip"
    monkeypatch.setattr(package, "ROOT", tmp_path)
    monkeypatch.setattr(package, "bundle_files", lambda: [source])
    monkeypatch.setattr("sys.argv", ["package_reproduction", "--output", str(destination)])

    package.main()

    assert list(destination.parent.iterdir()) == [destination]
    with zipfile.ZipFile(destination) as archive:
        assert archive.namelist() == ["direct_reciprocity_paper_20261013/README.md"]
        assert archive.read(archive.namelist()[0]) == source.read_bytes()


def test_bundle_contains_exact_current_paper_inputs_and_frozen_references():
    from tools.package_reproduction import bundle_files
    files = {path.relative_to(reproduce.ROOT).as_posix() for path in bundle_files()}
    paper = reproduce.paper_input_paths(reproduce.ROOT) | reproduce.paper_reference_paths(reproduce.ROOT)
    expected_data = {path.relative_to(reproduce.ROOT).as_posix() for path in paper}
    expected_data.update(('results/reproduction/INPUT_MANIFEST.json', 'docs/reproduction/README.md',
                          'docs/reproduction/VALIDATION.md',
                          'docs/direct_reciprocity/MISMATCH_DISTANCE_ANALYSIS.md'))
    assert {name for name in files if name.startswith(('results/', 'assets/', 'docs/'))} == expected_data
    assert len(reproduce.paper_input_paths(reproduce.ROOT)) == 3110
    assert {'results/model_comparison_20260928/cross_model_mainline_data.json',
            'results/model_comparison_20260928/score_baseline_data.json',
            'results/qwen3_8/ANALYSIS.json',
            'docs/direct_reciprocity/mismatch_distance/mismatch_distance_thinking_off.json',
            'docs/direct_reciprocity/mismatch_distance/mismatch_distance_thinking_on.json'} <= files
    assert sum(name.startswith('assets/paper/figure') for name in files) == 20
    excluded_parts = {'requests_initial', 'requests_candidates', 'request_progress', 'attempt_history',
                      'initial', 'arm_logs', 'streams', 'mismatch_detection_jev', 'smoke', 'logs',
                      'competition', 'paper_interface_focus'}
    assert not any(set(Path(name).parts) & excluded_parts or '_reproduct.' in name
                   or name.startswith('reproduction/') for name in files)
    assert not any(Path(name).name == '.env' or '.git' in Path(name).parts
                   or Path(name).suffix in {'.key', '.pem'} for name in files)


def test_package_allowlist_excludes_adjacent_nonfigure_files(tmp_path, monkeypatch):
    """Exercise the real collector and ZIP writer against unwanted neighboring data."""
    import json
    import zipfile
    from tools import package_reproduction as package

    allowed = ['README.md', 'pyproject.toml', 'uv.lock', '.python-version', '.env.example',
               'experiments/example.py', 'tools/example.py', 'tests/test_example.py',
               'results/core/manifest.json', 'assets/paper/figure1.png',
               'results/reference/ANALYSIS.json', 'results/reproduction/INPUT_MANIFEST.json',
               'docs/reproduction/README.md', 'docs/reproduction/VALIDATION.md',
               'docs/direct_reciprocity/MISMATCH_DISTANCE_ANALYSIS.md']
    unwanted = ['.env', 'secret.key', '.git/config', 'reproduction/api_call/request.json',
                'results/core/requests_candidates/one.json', 'results/core/initial/one.json',
                'results/core/arm_logs/score.jsonl', 'results/core/ANALYSIS_reproduct.json',
                'results/mismatch_detection_jev/judgments/one.json', 'results/smoke/output.json',
                'results/reproduction/latest/logs/run.log', 'docs/private.json',
                'assets/paper/old_figure.png', 'competition/output.json']
    for name in allowed + unwanted:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('test fixture\n', encoding='utf-8')
    report = tmp_path / 'results/reproduction/latest/RUN_REPORT.json'
    report.write_text(json.dumps({'status': 'passed', 'requested_steps': 'all'}), encoding='utf-8')
    inputs = {tmp_path / name for name in ('results/core/manifest.json', 'assets/paper/figure1.png')}
    references = {tmp_path / 'results/reference/ANALYSIS.json'}
    monkeypatch.setattr(package, 'ROOT', tmp_path)
    monkeypatch.setattr(package, 'paper_input_paths', lambda work: inputs)
    monkeypatch.setattr(package, 'paper_reference_paths', lambda work: references)
    assert {p.relative_to(tmp_path).as_posix() for p in package.bundle_files()} == set(allowed)
    destination = tmp_path / 'release/paper.zip'
    monkeypatch.setattr('sys.argv', ['package_reproduction', '--output', str(destination)])
    package.main()
    with zipfile.ZipFile(destination) as archive:
        prefix = 'direct_reciprocity_paper_20261013/'
        assert set(archive.namelist()) == {prefix + name for name in allowed}
        assert all(archive.read(prefix + name) == (tmp_path / name).read_bytes() for name in allowed)


def test_selected_output_mean_includes_retained_parent_slots_and_test_losses():
    winners = [{"seed": 200, "winner": "improved"}, {"seed": 200, "winner": None},
               {"seed": 200, "winner": "test_loss"}, {"seed": 201, "winner": None}]
    measured = {"improved": {"delta": {"default": {"score": 0.3}}},
                "test_loss": {"delta": {"default": {"score": -0.06}}}}
    assert selected_seed_gains(winners, measured, [200, 201], "default") == pytest.approx([0.08, 0.0])
    with pytest.raises(KeyError):
        selected_seed_gains(winners, {}, [200, 201], "default")
