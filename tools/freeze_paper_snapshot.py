"""Freeze figure assets and source hashes for a compiled manuscript revision."""
import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess

from .reproduce import ROOT, sha256

FIGURES = [
    (1, "fig_overview", "figure1"),
    (2, "fig_proposals", "if_results_matching"),
    (3, "fig_opponent_profiles", "if_payoff_behavior"),
    (4, "fig_generation_selection_full", "if_generation_selection"),
    (5, "fig_all_selectors", "figure3"),
    (6, "fig_policies", "figure5"),
    (7, "fig_mismatch_distance", "if_mismatch_distance"),
]
TABLES = [("I", "tab_selectors"), ("II", "tab_probe"), ("III", "tab_decomposition"),
          ("IV", "tab_sensitivity"), ("V", "tab_mismatch_distance_sensitivity")]


def source_inputs(paper):
    pending, seen = [paper / "main.tex"], set()
    while pending:
        path = pending.pop()
        if path in seen:
            continue
        seen.add(path)
        text = re.sub(r"(?m)(?<!\\)%.*$", "", path.read_text(encoding="utf-8"))
        pending.extend(paper / (name if name.endswith(".tex") else name + ".tex")
                       for name in re.findall(r"\\input\{([^}]+)\}", text))
    return sorted(seen)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manuscript", type=Path, default=ROOT / "paper_interface_focus")
    args = parser.parse_args()
    paper = args.manuscript.resolve()
    labels = dict(re.findall(r"\\newlabel\{([^}]+)\}\{\{([^}]+)\}",
                             (paper / "main.aux").read_text(encoding="utf-8")))
    for number, label in [(str(n), label) for n, label, _ in FIGURES] + TABLES:
        if labels.get(label) != number:
            raise ValueError(f"Compiled manuscript label differs: {label}")
    destination = ROOT / "assets/paper"
    destination.mkdir(parents=True, exist_ok=True)
    assets = []
    for number, label, source in FIGURES:
        for extension in ("pdf", "png", "svg"):
            path = paper / "figures" / f"{source}.{extension}"
            if not path.is_file():
                if extension == "svg" and number == 1:
                    continue
                raise FileNotFoundError(path)
            target = destination / f"figure{number}.{extension}"
            shutil.copy2(path, target)
            assets.append({"figure": number, "label": label, "path": target.relative_to(ROOT).as_posix(),
                           "sha256": sha256(target), "bytes": target.stat().st_size})
    report = {
        "paper_title": "Strategy improvement despite mismatched feedback: evolving direct reciprocity with large language models",
        "snapshot_date": "2026-10-13",
        "paper_revision": subprocess.check_output(["git", "-C", str(paper), "rev-parse", "HEAD"], text=True).strip(),
        "base_code_revision": subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip(),
        "figures": [{"number": number, "label": label} for number, label, _ in FIGURES],
        "tables": [{"number": number, "label": label} for number, label in TABLES],
        "source_hashes": {p.relative_to(paper).as_posix(): sha256(p) for p in source_inputs(paper)},
        "assets": assets,
        "scope": "Compiled input graph only. Orphan Score tables and former supplementary figures are additional evidence.",
    }
    endings = subprocess.check_output(['git', '-c', 'core.fsmonitor=false', '-C', str(ROOT),
                                       'ls-files', '--eol'], text=True)
    report['text_export_newlines'] = {}
    for line in endings.splitlines():
        metadata, name = line.split('\t', 1)
        if '_reproduct' in Path(name).stem and Path(name).suffix in ('.json', '.csv', '.tex'):
            report['text_export_newlines'][name] = 'crlf' if metadata.startswith('i/crlf') else 'lf'
    output = ROOT / "docs/reproduction/paper_snapshot.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Frozen {len(assets)} assets and {len(report['source_hashes'])} compiled source inputs.")


if __name__ == "__main__":
    main()
