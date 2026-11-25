"""Read dependency names from a ``pyproject.toml`` for ``check_unused_dependencies.py``.

Split from the checker so manifest parsing stays apart from the scan logic.
A manifest that cannot be read or has the wrong shape raises ``PolicyError``,
which the checker reports as exit 2 instead of a traceback.

Name rules (normalization, requirement parsing, table reads) live in
``dependency_names.py``, shared with ``check_dependency_drift.py``.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import tomllib
from dependency_hygiene_policy import PolicyError

try:
    from scripts.validation import dependency_names as dep_names
except ModuleNotFoundError:  # run as a script or loaded by path: the sibling is on sys.path
    dep_names = importlib.import_module("dependency_names")

_UV_PIN_KEYS = ("override-dependencies", "constraint-dependencies")


def _load_pyproject(pyproject: Path) -> dict[str, Any]:
    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PolicyError(f"manifest unreadable: {pyproject}: {exc}") from exc
    return data


def _table(data: dict[str, Any], key: str, where: str) -> dict[str, Any]:
    return dep_names.table(data, key, where, PolicyError)


def _requirements(value: object, where: str) -> list[str]:
    if not isinstance(value, list):
        raise PolicyError(f"{where} must be an array")
    # Dependency groups may hold {include-group = ...} tables; only strings name packages.
    return [item for item in value if isinstance(item, str)]


def project_name(pyproject: Path) -> str | None:
    """Normalized ``[project].name``, or None when the manifest declares none."""
    name = _table(_load_pyproject(pyproject), "project", str(pyproject)).get("name")
    return dep_names.normalize(name) if isinstance(name, str) and name.strip() else None


def declared_packages(pyproject: Path, *, include_uv_pins: bool = False) -> set[str]:
    """Return the normalized names of every dependency a pyproject declares.

    ``include_uv_pins`` adds ``[tool.uv]`` override and constraint entries.
    ``check_dependency_drift.py`` compares those pins across manifests, so it
    counts them. The unused-dependency scan leaves them out: a pin is not a
    package the code must import.
    """
    data = _load_pyproject(pyproject)
    where = str(pyproject)
    project = _table(data, "project", where)
    requirements = _requirements(project.get("dependencies", []), f"{where}: dependencies")
    for name, group in _table(project, "optional-dependencies", where).items():
        requirements.extend(_requirements(group, f"{where}: optional-dependencies.{name}"))
    for name, group in _table(data, "dependency-groups", where).items():
        requirements.extend(_requirements(group, f"{where}: dependency-groups.{name}"))
    if include_uv_pins:
        uv = _table(_table(data, "tool", where), "uv", f"{where}: tool")
        for key in _UV_PIN_KEYS:
            requirements.extend(_requirements(uv.get(key, []), f"{where}: tool.uv.{key}"))
    names = (dep_names.requirement_name(requirement) for requirement in requirements)
    return {name for name in names if name}
