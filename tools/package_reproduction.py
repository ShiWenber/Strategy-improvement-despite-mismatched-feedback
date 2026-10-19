"""Package an explicit allowlist of paper code, records and outputs."""
import argparse
import json
from pathlib import Path
import zipfile

from .reproduce import ROOT, read, paper_input_paths, paper_reference_paths


def bundle_files():
    files = {ROOT / name for name in ("README.md", "pyproject.toml", "uv.lock", ".python-version", ".env.example")}
    for directory, extensions in (("experiments", {".py"}), ("tools", {".py", ".sh"}), ("tests", {".py"})):
        files.update(p for p in (ROOT / directory).rglob("*") if p.is_file() and p.suffix in extensions)
    files.update(paper_input_paths(ROOT) | paper_reference_paths(ROOT))
    files.update(ROOT / name for name in (
        "results/reproduction/INPUT_MANIFEST.json", "docs/reproduction/README.md",
        "docs/reproduction/VALIDATION.md", "docs/direct_reciprocity/MISMATCH_DISTANCE_ANALYSIS.md"))
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
    if report["status"] != "passed" or report.get('requested_steps') != 'all':
        raise ValueError("Complete the offline reproduction successfully before packaging")
    files = bundle_files()
    prefix = "direct_reciprocity_paper_20261013"
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in files:
            archive.write(path, prefix + "/" + path.relative_to(ROOT).as_posix())
    print(json.dumps({"output": str(output), "files": len(files), "bytes": output.stat().st_size}))


if __name__ == "__main__":
    main()
