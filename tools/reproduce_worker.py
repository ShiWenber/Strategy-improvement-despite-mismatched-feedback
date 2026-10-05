"""Run one analysis with suffixed output files, without staging another project.

The parent verifies the canonical inputs. This process redirects file reads to
already recomputed intermediates and writes to *_reproduct files. It never
changes the stored requests, seals, or manuscript assets. Network is disabled.
"""
from __future__ import annotations

import argparse
import builtins
import io
import os
from pathlib import Path
import runpy
import socket
import sys

ROOT = Path(__file__).resolve().parents[1]
FIGURES = {'if_results_matching': 'fig2', 'if_payoff_behavior': 'fig3',
           'figure3': 'figS1', 'if_generation_selection': 'figS2',
           'figure5': 'figS3', 'if_opponent_profiles': 'figS4',
           'figure4': 'figS5', 'if_mismatch_distance': 'figS6'}


def route(file, writing):
    if isinstance(file, int) or not isinstance(file, (str, bytes, os.PathLike)):
        return file
    path = Path(os.fsdecode(file)).resolve()
    if not path.is_relative_to(ROOT):
        return file
    parts = path.relative_to(ROOT).parts
    if '_reproduct' in path.stem or parts[0] in ('reproduct', 'tmp'):
        return file
    if len(parts) > 2 and parts[0].startswith('paper_') and 'figures' in parts:
        stem = FIGURES.get(path.stem)
        target = ROOT / ('reproduct' if stem else 'tmp/reproduction') / ((stem or path.stem) + path.suffix)
    elif len(parts) > 2 and parts[0].startswith('paper_') and 'audit' in parts:
        target = ROOT / 'results/reproduction' / (path.stem + '_reproduct' + path.suffix)
    elif parts[0] in ('results', 'docs') or (parts[0].startswith('paper_') and 'tables' in parts):
        target = path.with_name(path.stem + '_reproduct' + path.suffix)
    else:
        return file
    if writing:
        # Scientific raw records and decision seals are never output artifacts.
        if path.name in ('manifest.json', 'SELECTIONS_SEALED.json', 'PROMPTS_SEALED.json', 'H_RELEASED.json') or any(
                p in parts for p in ('holdout', 'candidates', 'requests_candidates', 'requests_initial', 'initial', 'contexts', 'populations', 'selection_scores', 'judgments', 'summaries')):
            raise RuntimeError('Attempt to overwrite a frozen input: ' + str(path.relative_to(ROOT)))
        target.parent.mkdir(parents=True, exist_ok=True)
        return target
    return target if target.is_file() else file


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--module')
    parser.add_argument('--script')
    parser.add_argument('arguments', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    sys.path.insert(0, str(ROOT))
    os.chdir(ROOT)
    original_io, original_builtin = io.open, builtins.open

    def routed_open(original):
        def open_file(file, mode='r', *a, **kw):
            return original(route(file, any(c in mode for c in 'wax+')), mode, *a, **kw)
        return open_file

    io.open = routed_open(original_io)
    builtins.open = routed_open(original_builtin)
    original_replace = os.replace
    os.replace = lambda source, destination: original_replace(route(source, True), route(destination, True))

    def no_network(*a, **kw):
        raise RuntimeError('Offline reproduction cannot make network requests')

    socket.socket.connect = no_network
    socket.socket.connect_ex = no_network
    arguments = args.arguments[1:] if args.arguments[:1] == ['--'] else args.arguments
    sys.argv = [args.module or args.script, *arguments]
    if args.module:
        runpy.run_module(args.module, run_name='__main__')
    else:
        sys.path.insert(0, str((ROOT / args.script).parent))
        runpy.run_path(str(ROOT / args.script), run_name='__main__')


if __name__ == '__main__':
    main()
