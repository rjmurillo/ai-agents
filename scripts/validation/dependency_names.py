"""Shared dependency-name rules for the dependency hygiene gates.

``check_unused_dependencies.py`` (through ``dependency_manifest.py`` and
``dependency_hygiene_policy.py``) and ``check_dependency_drift.py`` both read
dependency names out of ``pyproject.toml``. One module owns the rules so the two
gates cannot disagree on what a name is:

* ``normalize``: PEP 503 name normalization.
* ``requirement_name``: the normalized name of a PEP 508 requirement string,
  parsed by ``packaging.Requirement``.
* ``table``: a TOML table read that fails with the caller's error type.

Each gate keeps its own scope. The drift gate also reads ``[tool.uv]`` pins and
rejects a requirement ``packaging`` cannot parse, because it compares
specifiers. The unused-dependency gate asks only which packages are declared,
so it keeps a leading-name fallback for a line ``packaging`` rejects.
``tests/validation/test_dependency_names.py`` pins that the two agree on every
real manifest in the repository.
"""

from __future__ import annotations

import re
from typing import Any

from packaging.requirements import InvalidRequirement, Requirement

_NORMALIZE_RE = re.compile(r"[-_.]+")
_LEADING_NAME_RE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")


def normalize(name: str) -> str:
    """PEP 503 normalized form of a distribution name."""
    return _NORMALIZE_RE.sub("-", name).lower()


def requirement_name(text: str) -> str | None:
    """Return the normalized package name of a requirement string, or None.

    ``packaging.Requirement`` is the parser. Only when it raises
    ``InvalidRequirement`` does a leading-name regex run, so a malformed line
    still names the package a scanner should look for. None means the text has
    no leading name at all.
    """
    try:
        return normalize(Requirement(text).name)
    except InvalidRequirement:
        match = _LEADING_NAME_RE.match(text)
        return normalize(match.group(1)) if match else None


def table(data: dict[str, Any], key: str, where: str, error: type[Exception]) -> dict[str, Any]:
    """Return ``data[key]`` as a table (empty when absent), else raise ``error``."""
    value = data.get(key, {})
    if not isinstance(value, dict):
        raise error(f"{where}: '{key}' must be a table")
    return value
