"""Guards against dangling import/reference breakage after refactors.

Two real incidents motivated these checks:

1. Moving a private helper between modules broke a caller that imported the
   private name. No test imported that module, so the breakage shipped silently.
2. A module was later deleted outright, which left its script target in
   ``pyproject.toml`` pointing at a module that no longer exists. Module-import
   checks cannot see that, because a script target is a string, not an import.

So: import every module, and resolve every declared script target.
"""

from __future__ import annotations

import importlib
import pkgutil
import tomllib
from pathlib import Path

import pytest

import experiments

PACKAGE_ROOT = Path(experiments.__file__).parent
PREFIX = "experiments."
PROJECT_ROOT = PACKAGE_ROOT.parent


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


def _script_targets() -> dict[str, str]:
    with (PROJECT_ROOT / "pyproject.toml").open("rb") as handle:
        data = tomllib.load(handle)
    return dict(data.get("project", {}).get("scripts", {}))


@pytest.mark.parametrize("name", _source_backed_module_names())
def test_module_imports_cleanly(name: str):
    assert importlib.import_module(name) is not None


# Resolved once at import so the parametrisation and the skip marker cannot
# disagree. Currently empty: the reputation-framework console scripts were
# pruned with the framework itself and every entry point runs as ``python -m``.
SCRIPT_TARGETS = sorted(_script_targets().items())


@pytest.mark.skipif(
    not SCRIPT_TARGETS,
    reason="no [project.scripts] entry points are declared; see module docstring",
)
@pytest.mark.parametrize("name,target", SCRIPT_TARGETS)
def test_script_target_resolves(name: str, target: str):
    """``module:attr`` in [project.scripts] must point at a real callable.

    Skipped today because the table is empty, which is stated rather than left
    implicit: an empty parametrisation otherwise reads as a passing guard.
    Declaring any entry point activates this test automatically.
    """
    module_name, _, attr = target.partition(":")
    module = importlib.import_module(module_name)
    assert callable(getattr(module, attr)), f"{name} -> {target} is not callable"


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
