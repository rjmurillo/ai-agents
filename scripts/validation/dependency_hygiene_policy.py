"""Policy value model and loader for ``check_unused_dependencies.py``.

Split from the checker so the policy shape (what the TOML may contain) stays
apart from the scan logic. Every shape error is a ``PolicyError`` so the checker
reports exit 2 instead of a traceback.
"""

from __future__ import annotations

import importlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import tomllib

try:
    from scripts.validation import dependency_names as dep_names
except ModuleNotFoundError:  # run as a script or loaded by path: the sibling is on sys.path
    dep_names = importlib.import_module("dependency_names")

# Re-exported for check_unused_dependencies.py, which imports it from here.
normalize = dep_names.normalize


class PolicyError(Exception):
    """The policy file or a manifest it names is unusable."""


@dataclass(frozen=True, slots=True)
class ToolOnly:
    package: str
    reason: str
    evidence_file: str
    evidence_pattern: str


@dataclass(frozen=True, slots=True)
class TransitiveOk:
    """A DEP003 import allowed only under ``only_under`` while ``via`` stays declared."""

    module: str
    via: str
    only_under: str
    reason: str


@dataclass(frozen=True, slots=True)
class FixtureModule:
    """A bare module name imported only in ``used_in`` that is not a package.

    ``used_in`` is one repository-relative file, or a directory prefix ending in
    ``/``. The exemption covers DEP001 findings for ``module`` inside that scope
    and fails as stale when no such finding remains.
    """

    module: str
    used_in: str
    reason: str

    def covers(self, relative: str) -> bool:
        if self.used_in.endswith("/"):
            return relative.startswith(self.used_in)
        return relative == self.used_in


@dataclass(frozen=True, slots=True)
class Manifest:
    path: str
    extend_exclude: tuple[str, ...] = ()
    dev_groups: tuple[str, ...] = ()
    module_map: dict[str, tuple[str, ...]] = field(default_factory=dict)
    tool_only: tuple[ToolOnly, ...] = ()
    transitive_ok: tuple[TransitiveOk, ...] = ()
    fixture_modules: tuple[FixtureModule, ...] = ()


def require_str(table: dict[str, Any], key: str, where: str) -> str:
    value = table.get(key)
    if not isinstance(value, str) or not value.strip():
        raise PolicyError(f"{where}: '{key}' must be a non-empty string")
    return value


def _tables(entry: dict[str, Any], key: str, where: str) -> list[dict[str, Any]]:
    value = entry.get(key, [])
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise PolicyError(f"{where}: '{key}' must be an array of tables")
    return value


def _strings(entry: dict[str, Any], key: str, where: str) -> tuple[str, ...]:
    value = entry.get(key, [])
    if not isinstance(value, list) or any(not isinstance(i, str) or not i for i in value):
        raise PolicyError(f"{where}: '{key}' must be an array of non-empty strings")
    return tuple(value)


def _module_map(entry: dict[str, Any], where: str) -> dict[str, tuple[str, ...]]:
    raw = entry.get("module_map", {})
    if not isinstance(raw, dict):
        raise PolicyError(f"{where}: 'module_map' must be a table")
    mapping: dict[str, tuple[str, ...]] = {}
    for key, value in raw.items():
        names = (value,) if isinstance(value, str) else value
        if (
            not isinstance(names, (list, tuple))
            or not names
            or any(not isinstance(n, str) or not n for n in names)
        ):
            raise PolicyError(
                f"{where}.module_map: '{key}' must map to a module name or a list of names"
            )
        mapping[dep_names.normalize(key)] = tuple(names)
    return mapping


def _parse_manifest(entry: dict[str, Any], where: str) -> Manifest:
    tools = tuple(
        ToolOnly(
            package=require_str(t, "package", f"{where}.tool_only"),
            reason=require_str(t, "reason", f"{where}.tool_only"),
            evidence_file=require_str(t, "evidence_file", f"{where}.tool_only"),
            evidence_pattern=_pattern(t, f"{where}.tool_only"),
        )
        for t in _tables(entry, "tool_only", where)
    )
    transitive = tuple(
        TransitiveOk(
            module=require_str(t, "module", f"{where}.transitive_ok"),
            via=dep_names.normalize(require_str(t, "via", f"{where}.transitive_ok")),
            only_under=require_str(t, "only_under", f"{where}.transitive_ok"),
            reason=require_str(t, "reason", f"{where}.transitive_ok"),
        )
        for t in _tables(entry, "transitive_ok", where)
    )
    fixtures = tuple(
        FixtureModule(
            module=require_str(f, "module", f"{where}.fixture_module"),
            used_in=require_str(f, "used_in", f"{where}.fixture_module"),
            reason=require_str(f, "reason", f"{where}.fixture_module"),
        )
        for f in _tables(entry, "fixture_module", where)
    )
    return Manifest(
        path=require_str(entry, "path", where),
        extend_exclude=_strings(entry, "extend_exclude", where),
        dev_groups=_strings(entry, "dev_groups", where),
        module_map=_module_map(entry, where),
        tool_only=tools,
        transitive_ok=transitive,
        fixture_modules=fixtures,
    )


def _pattern(table: dict[str, Any], where: str) -> str:
    pattern = require_str(table, "evidence_pattern", where)
    try:
        re.compile(pattern)
    except re.error as exc:
        raise PolicyError(f"{where}: 'evidence_pattern' is not a valid regex: {exc}") from exc
    return pattern


def load_policy(policy_path: Path) -> list[Manifest]:
    try:
        raw = tomllib.loads(policy_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PolicyError(f"policy file not found: {policy_path}") from exc
    except (OSError, ValueError) as exc:
        raise PolicyError(f"policy file unreadable: {policy_path}: {exc}") from exc

    entries = raw.get("manifest")
    if not isinstance(entries, list) or not entries:
        raise PolicyError("policy must declare at least one [[manifest]]")

    manifests: list[Manifest] = []
    seen: set[str] = set()
    for index, entry in enumerate(entries):
        where = f"manifest[{index}]"
        if not isinstance(entry, dict):
            raise PolicyError(f"{where}: expected a table")
        manifest = _parse_manifest(entry, where)
        if manifest.path in seen:
            raise PolicyError(f"{where}: duplicate manifest path '{manifest.path}'")
        seen.add(manifest.path)
        manifests.append(manifest)
    return manifests
