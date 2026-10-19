"""Copy compiled manuscript figures into assets/paper/."""
import argparse
from pathlib import Path
import re
import shutil

from .reproduce import ROOT

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
    copied = 0
    for number, label, source in FIGURES:
        for extension in ("pdf", "png", "svg"):
            path = paper / "figures" / f"{source}.{extension}"
            if not path.is_file():
                if extension == "svg" and number == 1:
                    continue
                raise FileNotFoundError(path)
            target = destination / f"figure{number}.{extension}"
            shutil.copy2(path, target)
            copied += 1
    print(f"Copied {copied} figure files to {destination}.")


if __name__ == "__main__":
    main()
