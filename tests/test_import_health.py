"""Import every source-backed experiment module to catch broken references."""

from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path

import pytest

import experiments

PACKAGE_ROOT = Path(experiments.__file__).parent
PREFIX = "experiments."


def _source_backed_module_names() -> list[str]:
    """Modules under ``experiments/`` that have a real ``.py`` source.

    ``pkgutil`` also lists orphaned ``__pycache__/*.pyc`` left behind by deleted
    modules; those are build artifacts, and failing on them is a false positive.
    """
    names = []
    for info in pkgutil.walk_packages([str(PACKAGE_ROOT)], prefix=PREFIX):
        relative = info.name[len(PREFIX):].replace(".", "/")
        if (PACKAGE_ROOT / f"{relative}.py").is_file():
            names.append(info.name)
    return sorted(names)


@pytest.mark.parametrize("name", _source_backed_module_names())
def test_module_imports_cleanly(name: str):
    assert importlib.import_module(name) is not None


def test_module_discovery_is_not_vacuous():
    """The walk must really find source modules, and find the ones on disk.

    test_module_imports_cleanly is only as good as this parametrisation: if the
    walk silently returned nothing, every import check would pass without
    importing anything.
    """
    names = _source_backed_module_names()
    assert names, "module discovery found nothing to import"
    assert names == sorted(names)
    for name in names:
        assert name.startswith(PREFIX), name
        relative = name[len(PREFIX):].replace(".", "/")
        assert (PACKAGE_ROOT / f"{relative}.py").is_file(), name


def test_orphan_pyc_is_not_treated_as_a_module():
    """A .pyc left by a deleted module must not be counted as a module.

    This is the false positive the walk filters out; guard the filter so a
    future change to the filter cannot quietly start failing the whole package.
    """
    (PACKAGE_ROOT / "_deleted_module_probe.pyc").write_bytes(b"\x00")
    try:
        assert "_deleted_module_probe" not in _source_backed_module_names()
    finally:
        (PACKAGE_ROOT / "_deleted_module_probe.pyc").unlink()
