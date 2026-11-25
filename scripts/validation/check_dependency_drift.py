#!/usr/bin/env python3
"""Enforce dependency constraint consistency across the repository's manifests.

The repository ships three Python projects (root, ``packages/semantic-hooks``,
``build/plugin-scanner``) and six npm manifests. Nothing ties their constraints
together, so the same package can drift to incompatible or lagging versions
without any gate noticing. This check compares every package declared in more
than one place and reports four kinds of drift:

* ``CONFLICT``: two manifests declare constraints no single version satisfies
  (for example ``==6.0.3`` against ``<6``). Never exemptible.
* ``FLOOR-DRIFT``: manifests agree on a range but one lower bound trails the
  highest one. Allowed only through a ``[[drift.allow]]`` entry in the policy
  file naming the package and the trailing manifest, with a reason. An entry
  whose drift has disappeared fails as stale.
* ``INTRA-MANIFEST``: one pyproject lists the same package with different
  specifiers in its runtime table, extras, or dependency groups.
* ``NPM-DRIFT``: one npm package carries different specifiers in different
  ``package.json`` files.

Python comparisons apply only where declaration markers overlap. Unsupported
marker predicates fail with exit 2, rather than guessing compatibility.

``requires-python`` is compared as the pseudo-package ``python``. uv
``override-dependencies`` and ``constraint-dependencies`` are compared like any
other declaration, which keeps the duplicated security overrides in step.

Lockfile versions are not compared: the scanner and semantic-hooks projects
resolve in isolated environments on purpose, and transitive versions legitimately
differ. ``uv lock --check`` per project (see the dependency-hygiene workflow)
covers manifest-to-lock agreement.

Exit codes (ADR-035):
    0 - no unallowed drift
    1 - drift or stale allow entries found
    2 - policy or manifest is missing or malformed (including an invalid
        ``requires-python`` specifier)
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import tomllib
from packaging.requirements import InvalidRequirement, Requirement
from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version

try:
    from scripts.validation import dependency_names as names
    from scripts.validation import python_dependency_constraints as constraints
except ModuleNotFoundError:
    names = importlib.import_module("dependency_names")
    constraints = importlib.import_module("python_dependency_constraints")

normalize = names.normalize
satisfiable = constraints.satisfiable

EXIT_OK = 0
EXIT_LOGIC = 1
EXIT_CONFIG = 2

DEFAULT_POLICY = Path(".github") / "dependency-hygiene" / "policy.toml"
PYTHON = "python"

_NPM_TABLES = ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies")


class DriftConfigError(Exception):
    """The policy or a manifest is missing or malformed."""


@dataclass(frozen=True, slots=True)
class Declaration:
    manifest: str
    package: str
    specifier: str
    origin: str
    marker: str = ""


@dataclass(frozen=True, slots=True)
class Allow:
    package: str
    manifest: str
    reason: str


@dataclass(frozen=True, slots=True)
class Policy:
    python_manifests: tuple[str, ...]
    npm_manifests: tuple[str, ...]
    allow: tuple[Allow, ...]


@dataclass(frozen=True, slots=True)
class Drift:
    kind: str
    package: str
    detail: str
    manifest: str = ""

    def render(self) -> str:
        return f"{self.kind} {self.package}: {self.detail}"


def _table(data: dict[str, Any], key: str, where: str) -> dict[str, Any]:
    return names.table(data, key, where, DriftConfigError)


def _list(data: dict[str, Any], key: str, where: str) -> list[Any]:
    value = data.get(key, [])
    if not isinstance(value, list):
        raise DriftConfigError(f"{where}: '{key}' must be an array")
    return value


def _paths(data: dict[str, Any], key: str) -> tuple[str, ...]:
    values = _list(data, key, "drift")
    if any(not isinstance(v, str) or not v.strip() for v in values):
        raise DriftConfigError(f"drift: '{key}' must be an array of non-empty strings")
    return tuple(values)


def load_policy(path: Path) -> Policy:
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise DriftConfigError(f"policy file not found: {path}") from exc
    except (OSError, ValueError) as exc:
        raise DriftConfigError(f"policy file unreadable: {path}: {exc}") from exc
    drift = raw.get("drift")
    if not isinstance(drift, dict):
        raise DriftConfigError("policy has no [drift] table")
    allows = []
    for index, entry in enumerate(_list(drift, "allow", "drift")):
        if not isinstance(entry, dict):
            raise DriftConfigError(f"drift.allow[{index}]: expected a table")
        for key in ("package", "manifest", "reason"):
            value = entry.get(key)
            if not isinstance(value, str) or not value.strip():
                raise DriftConfigError(f"drift.allow[{index}]: '{key}' must be a non-empty string")
        allows.append(
            Allow(
                normalize(entry["package"]) if entry["package"] != PYTHON else PYTHON,
                entry["manifest"],
                entry["reason"],
            )
        )
    return Policy(
        python_manifests=_paths(drift, "python_manifests"),
        npm_manifests=_paths(drift, "npm_manifests"),
        allow=tuple(allows),
    )


def _requirement(text: str, manifest: str, origin: str) -> Declaration:
    # Strict, unlike names.requirement_name: drift compares specifiers, so a
    # requirement packaging rejects must fail the gate, not fall back to a regex.
    try:
        req = Requirement(text)
    except InvalidRequirement as exc:
        raise DriftConfigError(
            f"{manifest}: invalid requirement {text!r} in {origin}: {exc}"
        ) from exc
    return Declaration(
        manifest,
        normalize(req.name),
        str(req.specifier),
        origin,
        str(req.marker) if req.marker else "",
    )


def _dependency_array(
    texts: object, manifest: str, origin: str, groups: dict[str, Any] | None = None
) -> list[Declaration]:
    if not isinstance(texts, list):
        raise DriftConfigError(f"{manifest}: {origin} must be an array")
    found = []
    for text in texts:
        if isinstance(text, str):
            found.append(_requirement(text, manifest, origin))
        elif groups is not None and isinstance(text, dict):
            _include_group(text, groups, f"{manifest}: {origin}")
        else:
            raise DriftConfigError(f"{manifest}: {origin}: expected a requirement string")
    return found


def _include_group(entry: dict[str, Any], groups: dict[str, Any], where: str) -> str:
    name = entry.get("include-group")
    if set(entry) != {"include-group"} or not isinstance(name, str) or not name.strip():
        raise DriftConfigError(f"{where}: invalid include-group table")
    matches = [key for key in groups if normalize(key) == normalize(name)]
    if len(matches) != 1:
        raise DriftConfigError(f"{where}: unknown or ambiguous include-group {name!r}")
    return matches[0]


def _group_declarations(groups: dict[str, Any], manifest: str) -> list[Declaration]:
    found = []
    edges: dict[str, set[str]] = {}
    for group, texts in groups.items():
        found.extend(_dependency_array(texts, manifest, f"dependency-groups.{group}", groups))
        edges[group] = {
            _include_group(text, groups, manifest) for text in texts if isinstance(text, dict)
        }
    remaining = dict(edges)
    while remaining:
        leaves = {name for name, targets in remaining.items() if not targets & remaining.keys()}
        if not leaves:
            raise DriftConfigError(f"{manifest}: cyclic include-group references")
        remaining = {name: targets for name, targets in remaining.items() if name not in leaves}
    return found


def _python_version(project: dict[str, Any], manifest: str) -> list[Declaration]:
    requires_python = project.get("requires-python")
    if requires_python is None:
        return []
    try:
        spec = str(SpecifierSet(requires_python))
    except (InvalidSpecifier, TypeError) as exc:
        raise DriftConfigError(
            f"{manifest}: invalid requires-python {requires_python!r}: {exc}"
        ) from exc
    return [Declaration(manifest, PYTHON, spec, "requires-python")]


def python_declarations(root: Path, manifest: str) -> list[Declaration]:
    path = root / manifest
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise DriftConfigError(f"manifest not found: {path}") from exc
    except (OSError, ValueError) as exc:
        raise DriftConfigError(f"manifest unreadable: {path}: {exc}") from exc

    project = _table(data, "project", manifest)
    found = _dependency_array(project.get("dependencies", []), manifest, "project.dependencies")
    for extra, texts in _table(project, "optional-dependencies", manifest).items():
        found.extend(_dependency_array(texts, manifest, f"optional-dependencies.{extra}"))
    found.extend(_group_declarations(_table(data, "dependency-groups", manifest), manifest))
    tool = _table(data, "tool", manifest)
    uv = _table(tool, "uv", f"{manifest}: tool")
    # Drift counts uv pins because they constrain versions across manifests;
    # dependency_manifest.declared_packages(include_uv_pins=True) is the same set of names.
    for key in ("override-dependencies", "constraint-dependencies"):
        found.extend(_dependency_array(uv.get(key, []), manifest, f"tool.uv.{key}"))
    return found + _python_version(project, manifest)


def npm_declarations(root: Path, manifest: str) -> list[Declaration]:
    path = root / manifest
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise DriftConfigError(f"manifest not found: {path}") from exc
    except (OSError, ValueError) as exc:
        raise DriftConfigError(f"manifest unreadable: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise DriftConfigError(f"manifest unreadable: {path}: expected a JSON object")
    found = []
    for table in _NPM_TABLES:
        for name, spec in _npm_table(data, table, manifest).items():
            found.append(Declaration(manifest, name, str(spec), table))
    for name, spec in _npm_table(data, "overrides", manifest).items():
        if isinstance(spec, str):
            found.append(Declaration(manifest, name, spec, "overrides"))
    return found


def _npm_table(data: dict[str, Any], key: str, manifest: str) -> dict[str, Any]:
    value = data.get(key)
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise DriftConfigError(f"{manifest}: '{key}' must be an object")
    return value


def lower_bound(spec: str) -> Version | None:
    """Highest ``>=``, ``>``, ``==``, or ``~=`` version in a specifier, or None."""
    bounds = []
    for item in SpecifierSet(spec):
        if item.operator in (">=", ">", "==", "~=", "==="):
            try:
                bounds.append(Version(item.version.rstrip(".*")))
            except InvalidVersion:
                continue
    return max(bounds) if bounds else None


def _intra_manifest(package: str, declarations: list[Declaration]) -> list[Drift]:
    plain = [d for d in declarations if not d.origin.startswith("tool.uv")]
    drifts = []
    for manifest in sorted({d.manifest for d in plain}):
        entries = [d for d in plain if d.manifest == manifest]
        if len({d.specifier for d in entries}) > 1:
            where = ", ".join(f"{d.origin}={d.specifier or '*'}" for d in entries)
            drifts.append(Drift("INTRA-MANIFEST", package, f"{manifest}: {where}"))
    return drifts


def _floor_drifts(package: str, declarations: list[Declaration]) -> list[Drift]:
    floors: dict[str, Version] = {}
    for declaration in declarations:
        floor = lower_bound(declaration.specifier)
        if floor is not None:
            floors[declaration.manifest] = max(floor, floors.get(declaration.manifest, floor))
    if len(set(floors.values())) < 2:
        return []
    top = max(floors.values())
    return [
        Drift(
            "FLOOR-DRIFT",
            package,
            f"{manifest} floor {floor} trails {top}; raise it or add a "
            "[[drift.allow]] entry with a reason",
            manifest,
        )
        for manifest, floor in sorted(floors.items())
        if floor != top
    ]


def _environment_drift(package: str, declarations: list[Declaration]) -> list[Drift]:
    drifts = _intra_manifest(package, declarations)
    if len({d.manifest for d in declarations}) < 2:
        return drifts
    if not satisfiable([d.specifier for d in declarations]):
        summary = "; ".join(f"{d.manifest} {d.origin}: {d.specifier or '*'}" for d in declarations)
        return drifts + [Drift("CONFLICT", package, f"no version satisfies all of: {summary}")]
    return drifts + _floor_drifts(package, declarations)


def _allow_key(drift: Drift) -> tuple[str, str]:
    return drift.package, drift.manifest


def find_python_drift(
    declarations: list[Declaration], allow: tuple[Allow, ...]
) -> tuple[list[Drift], set[tuple[str, str]], int]:
    drifts: dict[Drift, None] = {}
    used_allow: set[tuple[str, str]] = set()
    allowed = {(a.package, a.manifest) for a in allow}

    by_package: dict[str, list[Declaration]] = defaultdict(list)
    for decl in declarations:
        by_package[decl.package].append(decl)

    shared = 0
    for package, decls in sorted(by_package.items()):
        shared += int(len({d.manifest for d in decls}) > 1)
        try:
            groups = constraints.active_groups([d.marker for d in decls])
        except ValueError as exc:
            raise DriftConfigError(f"{package}: {exc}") from exc
        for group in sorted(groups):
            for drift in _environment_drift(package, [decls[i] for i in group]):
                if drift.kind == "FLOOR-DRIFT" and _allow_key(drift) in allowed:
                    used_allow.add(_allow_key(drift))
                else:
                    drifts[drift] = None
    return list(drifts), used_allow, shared


def find_npm_drift(declarations: list[Declaration]) -> tuple[list[Drift], int]:
    by_package: dict[str, list[Declaration]] = defaultdict(list)
    for decl in declarations:
        by_package[decl.package].append(decl)
    drifts: list[Drift] = []
    shared = 0
    for package, decls in sorted(by_package.items()):
        if len({d.manifest for d in decls}) < 2:
            continue
        shared += 1
        if len({d.specifier for d in decls}) > 1:
            where = "; ".join(f"{d.manifest} {d.origin}: {d.specifier}" for d in decls)
            drifts.append(Drift("NPM-DRIFT", package, where))
    return drifts, shared


def run(root: Path, policy: Policy) -> tuple[list[Drift], str]:
    if not policy.python_manifests and not policy.npm_manifests:
        raise DriftConfigError("policy lists no manifests under [drift]")
    py_decls = [d for m in policy.python_manifests for d in python_declarations(root, m)]
    npm_decls = [d for m in policy.npm_manifests for d in npm_declarations(root, m)]

    drifts, used, py_shared = find_python_drift(py_decls, policy.allow)
    npm_drifts, npm_shared = find_npm_drift(npm_decls)
    drifts.extend(npm_drifts)

    known = set(policy.python_manifests)
    for entry in policy.allow:
        if entry.manifest not in known:
            drifts.append(
                Drift(
                    "STALE-ALLOW",
                    entry.package,
                    f"manifest {entry.manifest} is not in python_manifests",
                )
            )
        elif (entry.package, entry.manifest) not in used:
            drifts.append(
                Drift(
                    "STALE-ALLOW",
                    entry.package,
                    f"{entry.manifest} no longer trails; delete the [[drift.allow]] entry",
                )
            )
    summary = (
        f"dependency drift: {len(policy.python_manifests)} python manifests "
        f"({len({d.package for d in py_decls})} packages, {py_shared} shared), "
        f"{len(policy.npm_manifests)} npm manifests "
        f"({len({d.package for d in npm_decls})} packages, {npm_shared} shared), "
        f"{len(drifts)} findings"
    )
    return drifts, summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="repository root")
    parser.add_argument("--policy", type=Path, default=None, help="policy TOML path")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    try:
        policy = load_policy(args.policy or (root / DEFAULT_POLICY))
        drifts, summary = run(root, policy)
    except DriftConfigError as exc:
        print(f"CONFIG ERROR: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    for drift in drifts:
        print(drift.render())
    print(summary)
    return EXIT_LOGIC if drifts else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
