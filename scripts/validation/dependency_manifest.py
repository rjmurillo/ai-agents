"""Read dependency names from a ``pyproject.toml`` for ``check_unused_dependencies.py``.

Split from the checker so manifest parsing stays apart from the scan logic.
A manifest that cannot be read or has the wrong shape raises ``PolicyError``,
which the checker reports as exit 2 instead of a traceback.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import tomllib
from dependency_hygiene_policy import PolicyError, normalize

_REQ_NAME_RE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")


def _load_pyproject(pyproject: Path) -> dict[str, Any]:
    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PolicyError(f"manifest unreadable: {pyproject}: {exc}") from exc
    return data


def _table(data: dict[str, Any], key: str, where: str) -> dict[str, Any]:
    value = data.get(key, {})
    if not isinstance(value, dict):
        raise PolicyError(f"{where}: '{key}' must be a table")
    return value


def _requirements(value: object, where: str) -> list[str]:
    if not isinstance(value, list):
        raise PolicyError(f"{where} must be an array")
    # Dependency groups may hold {include-group = ...} tables; only strings name packages.
    return [item for item in value if isinstance(item, str)]


def project_name(pyproject: Path) -> str | None:
    """Normalized ``[project].name``, or None when the manifest declares none."""
    name = _table(_load_pyproject(pyproject), "project", str(pyproject)).get("name")
    return normalize(name) if isinstance(name, str) and name.strip() else None


def declared_packages(pyproject: Path) -> set[str]:
    """Return the normalized names of every dependency a pyproject declares."""
    data = _load_pyproject(pyproject)
    where = str(pyproject)
    project = _table(data, "project", where)
    requirements = _requirements(project.get("dependencies", []), f"{where}: dependencies")
    for name, group in _table(project, "optional-dependencies", where).items():
        requirements.extend(_requirements(group, f"{where}: optional-dependencies.{name}"))
    for name, group in _table(data, "dependency-groups", where).items():
        requirements.extend(_requirements(group, f"{where}: dependency-groups.{name}"))
    names = set()
    for requirement in requirements:
        match = _REQ_NAME_RE.match(requirement)
        if match:
            names.add(normalize(match.group(1)))
    return names
