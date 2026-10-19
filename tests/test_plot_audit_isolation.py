"""Optional layout audits must not gate figure exports."""
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pytest

from experiments.direct_reciprocity.figures import plot_camera_ready as camera
from experiments.direct_reciprocity.figures import plot_results_three_figures as main
from experiments.direct_reciprocity.figures import results_plot_audit as audit
from experiments.direct_reciprocity.figures.results_plot_style import save_figure


def export(renderer, fig, output, monkeypatch):
    if renderer == 'main':
        return main.save(fig, output, 'example')
    if renderer == 'camera':
        monkeypatch.setattr(camera, 'OUT', output)
        monkeypatch.setattr(camera, 'exports', [])
        camera.save(fig, 5)
        return camera.exports[0]
    return save_figure(fig, 'example', output)


@pytest.mark.parametrize('renderer', ['shared', 'main', 'camera'])
def test_export_succeeds_with_layout_that_fails_optional_audit(tmp_path, monkeypatch, renderer):
    fig = plt.figure(figsize=(1, 1))
    fig.text(1.1, .5, 'Small external text', fontsize=1)
    with pytest.raises(AssertionError):
        audit.validate_panel_layout(fig, 'figS2')

    def unexpected_audit(*_args, **_kwargs):
        pytest.fail('Default export invoked a layout audit')

    monkeypatch.setattr(audit, 'validate_panel_layout', unexpected_audit)
    monkeypatch.setattr(main, 'audit_figure', unexpected_audit)
    try:
        result = export(renderer, fig, tmp_path, monkeypatch)
    finally:
        plt.close(fig)

    assert set(result['outputs']) == {'pdf', 'svg', 'png'}
    assert all(Path(path).stat().st_size > 0 for path in result['outputs'].values())
    assert {path.suffix for path in tmp_path.iterdir()} == {'.pdf', '.svg', '.png'}


@pytest.mark.parametrize('renderer', ['shared', 'main', 'camera'])
def test_export_still_propagates_save_errors(tmp_path, monkeypatch, renderer):
    fig = plt.figure(figsize=(1, 1))

    def failed_save(*_args, **_kwargs):
        raise OSError('Cannot write the figure')

    monkeypatch.setattr(fig, 'savefig', failed_save)
    try:
        with pytest.raises(OSError, match='Cannot write the figure'):
            export(renderer, fig, tmp_path, monkeypatch)
    finally:
        plt.close(fig)
