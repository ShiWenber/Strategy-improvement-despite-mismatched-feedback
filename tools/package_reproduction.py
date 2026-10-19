"""Package an explicit allowlist of paper code, records and outputs."""
import argparse
import json
from pathlib import Path
import zipfile

from .reproduce import ROOT, RUNS, read, sha256


def bundle_files():
    files = {ROOT / name for name in ("README.md", "pyproject.toml", "uv.lock", ".python-version", ".env.example")}
    for directory, extensions in (("experiments", {".py"}), ("tools", {".py", ".sh"}), ("tests", {".py"}),
                                  ("docs/reproduction", {".md", ".json"}), ("assets/paper", {".pdf", ".png", ".svg"})):
        files.update(p for p in (ROOT / directory).rglob("*") if p.is_file() and p.suffix in extensions)
    files.update(p for p in (ROOT / 'assets/tokenizer').iterdir() if p.is_file())
    # Include the audited reference inventory used by the existing archive tests.
    for item in read(ROOT / "results/reproduction/INPUT_MANIFEST.json")["records"]:
        path = ROOT / item["path"]
        allowed = ("assets/", "docs/direct_reciprocity/", "results/")
        if not item["path"].startswith(allowed) or not path.resolve().is_relative_to(ROOT):
            raise ValueError(f"Unexpected archived input: {item['path']}")
        files.add(path)
    evidence_directories = ["results/" + run for run in RUNS]
    evidence_directories += ["results/" + name for name in (
        "qwen3_8", "model_comparison_20260928", "reciprocity_population_visuals_20260924",
        "figure4_opponent_profiles_20260926", "mismatch_detection_jev")]
    evidence_directories.append("docs/direct_reciprocity/mismatch_distance")
    for directory in evidence_directories:
        files.update(p for p in (ROOT / directory).rglob("*")
                     if p.is_file() and "__pycache__" not in p.parts
                     and p.suffix in {".json", ".jsonl", ".txt", ".md", ".csv", ".tex"})
    files.update(ROOT / "docs/direct_reciprocity" / name for name in (
        "MISMATCH_DISTANCE_ANALYSIS.md", "MISMATCH_DISTANCE_ANALYSIS_reproduct.md",
        "THINKING_384K_PROTOCOL.md", "ROLE_ANALYSIS_PLAN.md"))
    for name in ("INPUT_MANIFEST.json", "replay_reproduct.json", "SCORE_MIGRATION_VALIDATION.json",
                 "CONDITION_GENERATION_VALIDATION.json"):
        files.add(ROOT / "results/reproduction" / name)
    files.update(p for p in (ROOT / "results/reproduction/latest").rglob("*") if p.is_file())
    for path in files:
        if not path.is_file():
            raise FileNotFoundError(path)
        if path.name == ".env" or path.suffix in {".key", ".pem"} or ".git" in path.parts:
            raise ValueError("Unexpected non-reproduction file in bundle")
    return sorted(files)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist/direct_reciprocity_paper_20261013.zip")
    args = parser.parse_args()
    report = read(ROOT / "results/reproduction/latest/RUN_REPORT.json")
    if report["status"] != "passed" or report["changed_archive_files"] or report.get('requested_steps') != 'all':
        raise ValueError("Complete the offline reproduction successfully before packaging")
    files = bundle_files()
    prefix = "direct_reciprocity_paper_20261013"
    records = [{"path": p.relative_to(ROOT).as_posix(), "bytes": p.stat().st_size, "sha256": sha256(p)} for p in files]
    manifest = {"paper_revision": report["paper_revision"], "files": records,
                "excluded": ["credentials", "git history", "local environments", "manuscript source", "unrelated experiments"]}
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path, record in zip(files, records):
            archive.write(path, prefix + "/" + record["path"])
        archive.writestr(prefix + "/BUNDLE_MANIFEST.json", json.dumps(manifest, indent=2) + "\n")
    with zipfile.ZipFile(output) as archive:
        bad_file = archive.testzip()
        if bad_file:
            raise ValueError(f"Archive CRC failed: {bad_file}")
    checksum = sha256(output)
    output.with_suffix(".zip.sha256").write_text(checksum + "  " + output.name + "\n", encoding="ascii")
    print(json.dumps({"output": str(output), "files": len(files), "bytes": output.stat().st_size, "sha256": checksum}))


if __name__ == "__main__":
    main()
