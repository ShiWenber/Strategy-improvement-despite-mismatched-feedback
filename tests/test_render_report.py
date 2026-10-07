"""Readable reports must preserve JSON values and leave scientific inputs untouched."""
import json
from pathlib import Path
import subprocess
import sys

import pytest

from tools.render_report import render_report

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'tools/render_report.py'


def test_nested_statistics_and_record_tables_keep_precision_and_missing_values():
    data = {'raw': {'accurate': {'mean': 0.12345678901234568,
                               'ci95': [-0.3, 0.7], 'n': 9007199254740993}},
            'records': [{'arm': 'accurate', 'gain': -1e-300, 'valid': True},
                        {'arm': 'mismatched', 'gain': None, 'valid': False}],
            'empty': [], 'metadata': {}}
    original = json.dumps(data)
    report = render_report(data, 'ANALYSIS.json')
    assert '| mean | 0.12345678901234568 |' in report
    assert '| n | 9007199254740993 |' in report
    assert r'| ci95 | \[-0.3, 0.7\] |' in report
    assert '| arm | gain | valid |' in report
    assert '| accurate | -1e-300 | true |' in report
    assert '| mismatched | null | false |' in report
    assert '| empty | \\[\\] |' in report
    assert '| metadata | {} |' in report
    assert json.dumps(data) == original


def test_labels_and_text_cannot_break_tables_or_inject_html():
    report = render_report({'x|y': '<script>\n*a_b* [link] `code`'}, 'ANALYSIS.json')
    assert '| x&#124;y |' in report
    assert '&lt;script&gt;<br>' in report
    assert '<script>' not in report
    assert r'\*a\_b\* \[link\] \`code\`' in report


def test_unequal_record_keys_and_nested_lists_preserve_structure():
    report = render_report([{'gain': None}, {'accepted': False}, [[1, 2], [3]]], 'data.json')
    assert '<summary>Item 0</summary>' in report
    assert '<summary>Item 1</summary>' in report
    assert '<summary>Item 2</summary>' in report
    assert '| gain | null |' in report
    assert '| accepted | false |' in report
    assert r'\[1, 2\]' in report and r'\[3\]' in report


def test_cli_default_and_explicit_destinations_do_not_modify_input(tmp_path):
    source = tmp_path / 'ANALYSIS_reproduct.json'
    source.write_text(json.dumps({'mean': 0.012345678901234567}), encoding='utf-8-sig')
    before = source.read_bytes()
    for options, output in [([], source.with_suffix('.md')),
                            (['--output', str(tmp_path / 'views/report.md')], tmp_path / 'views/report.md')]:
        result = subprocess.run([sys.executable, str(SCRIPT), str(source), *options],
                                capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        assert '| mean | 0.012345678901234567 |' in output.read_text(encoding='utf-8')
        assert source.read_bytes() == before


def test_cli_rejects_overwriting_source_or_rendering_nonfinite_statistics(tmp_path):
    source = tmp_path / 'ANALYSIS.json'
    source.write_text('{"mean": NaN}', encoding='utf-8')
    before = source.read_bytes()
    result = subprocess.run([sys.executable, str(SCRIPT), str(source), '--output', str(source)],
                            capture_output=True, text=True)
    assert result.returncode != 0 and 'Output must differ' in result.stderr
    result = subprocess.run([sys.executable, str(SCRIPT), str(source)], capture_output=True, text=True)
    assert result.returncode != 0
    assert not source.with_suffix('.md').exists()
    assert source.read_bytes() == before


@pytest.mark.parametrize('relative', [
    'results/feedback_specificity_v2/ANALYSIS.json',
    'results/feedback_specificity_v2/role_analysis/ANALYSIS.json',
    'results/feedback_specificity_thinking_384k_20260923/ANALYSIS.json',
    'results/qwen3_8/ANALYSIS.json',
])
def test_current_paper_schemas_keep_every_numeric_value(relative):
    source = ROOT / relative
    before = source.read_bytes()
    data = json.loads(before)
    report = render_report(data, relative)

    def numbers(value):
        if isinstance(value, dict):
            return set().union(*(numbers(item) for item in value.values()))
        if isinstance(value, list):
            return set().union(*(numbers(item) for item in value))
        return {json.dumps(value)} if type(value) in (float, int) else set()

    values = numbers(data)
    assert values and all(value in report for value in values)
    assert source.read_bytes() == before


@pytest.mark.parametrize('module,entry,output', [
    ('analyze', 'summarize', 'analysis.json'),
    ('analyze_control', 'summarize_controls', 'CONTROL_ANALYSIS.json'),
    ('factor_report', 'report', 'FACTOR_COMPARISONS.json'),
])
def test_old_analysis_entries_write_json_without_markdown(tmp_path, module, entry, output):
    from importlib import import_module
    (tmp_path / 'matrix_plan.json').write_text('{"cells": []}', encoding='utf-8')
    (tmp_path / 'analysis.json').write_text('{"endpoints": [], "all_main_cells_complete": true}', encoding='utf-8')
    result = getattr(import_module('experiments.direct_reciprocity.' + module), entry)(tmp_path)
    assert json.loads((tmp_path / output).read_text(encoding='utf-8')) == result
    assert not list(tmp_path.glob('*.md'))
