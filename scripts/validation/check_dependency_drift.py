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
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import tomllib
from packaging.requirements import InvalidRequirement, Requirement
from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version

EXIT_OK = 0
EXIT_LOGIC = 1
EXIT_CONFIG = 2

DEFAULT_POLICY = Path(".github") / "dependency-hygiene" / "policy.toml"
PYTHON = "python"

_NORMALIZE_RE = re.compile(r"[-_.]+")
_NPM_TABLES = ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies")


class DriftConfigError(Exception):
    """The policy or a manifest is missing or malformed."""


def normalize(name: str) -> str:
    return _NORMALIZE_RE.sub("-", name).lower()


@dataclass(frozen=True, slots=True)
class Declaration:
    manifest: str
    package: str
    specifier: str
    origin: str


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

    def render(self) -> str:
        return f"{self.kind} {self.package}: {self.detail}"


def _table(data: dict[str, Any], key: str, where: str) -> dict[str, Any]:
    value = data.get(key, {})
    if not isinstance(value, dict):
        raise DriftConfigError(f"{where}: '{key}' must be a table")
    return value


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


def _requirement(text: str, manifest: str, origin: str) -> tuple[str, str]:
    try:
        req = Requirement(text)
    except InvalidRequirement as exc:
        raise DriftConfigError(
            f"{manifest}: invalid requirement {text!r} in {origin}: {exc}"
        ) from exc
    return normalize(req.name), str(req.specifier)


def python_declarations(root: Path, manifest: str) -> list[Declaration]:
    path = root / manifest
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise DriftConfigError(f"manifest not found: {path}") from exc
    except (OSError, ValueError) as exc:
        raise DriftConfigError(f"manifest unreadable: {path}: {exc}") from exc

    found: list[Declaration] = []

    def add(texts: object, origin: str) -> None:
        if not isinstance(texts, list):
            raise DriftConfigError(f"{manifest}: {origin} must be an array")
        for text in texts:
            if not isinstance(text, str):
                continue
            name, spec = _requirement(text, manifest, origin)
            found.append(Declaration(manifest, name, spec, origin))

    project = _table(data, "project", manifest)
    add(project.get("dependencies", []), "project.dependencies")
    for extra, texts in _table(project, "optional-dependencies", manifest).items():
        add(texts, f"optional-dependencies.{extra}")
    for group, texts in _table(data, "dependency-groups", manifest).items():
        add(texts, f"dependency-groups.{group}")
    tool = _table(data, "tool", manifest)
    uv = _table(tool, "uv", f"{manifest}: tool")
    add(uv.get("override-dependencies", []), "tool.uv.override-dependencies")
    add(uv.get("constraint-dependencies", []), "tool.uv.constraint-dependencies")
    requires_python = project.get("requires-python")
    if requires_python is not None:
        try:
            spec = str(SpecifierSet(requires_python))
        except (InvalidSpecifier, TypeError) as exc:
            raise DriftConfigError(
                f"{manifest}: invalid requires-python {requires_python!r}: {exc}"
            ) from exc
        found.append(Declaration(manifest, PYTHON, spec, "requires-python"))
    return found


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


def _candidates(specs: list[str]) -> list[Version]:
    base: set[Version] = {Version("0"), Version("99999")}
    boundaries = [item for spec in specs for item in SpecifierSet(spec)]
    depth = max((len(item.version.split(".")) for item in boundaries), default=1) + 1
    for spec in specs:
        for item in SpecifierSet(spec):
            try:
                version = Version(item.version.rstrip(".*"))
            except InvalidVersion:
                continue
            base.add(version)
            epoch = f"{version.epoch}!" if version.epoch else ""
            # Release tuples have arbitrary length. A micro-version bump alone
            # misses valid versions between adjacent micro-version bounds.
            padded = [*version.release, *([0] * (depth - len(version.release))), 1]
            base.add(Version(epoch + ".".join(str(n) for n in padded)))
            for index in range(len(version.release)):
                sibling = [*version.release[:index], version.release[index] + 1]
                base.add(Version(epoch + ".".join(str(n) for n in sibling)))
            release_text = epoch + ".".join(str(n) for n in version.release)
            if version.pre:
                label, number = version.pre
                base.add(Version(f"{release_text}{label}{number + 1}"))
            if version.dev is not None:
                base.add(Version(f"{release_text}.dev{version.dev + 1}"))
            if version.post is not None:
                base.add(Version(f"{release_text}.post{version.post + 1}"))
            release = list(version.release) + [0, 0, 0]
            base.add(Version(".".join(str(n) for n in release[:3])))
            bumped = list(version.release)
            bumped[-1] += 1
            base.add(Version(".".join(str(n) for n in bumped)))
            base.add(Version(".".join(str(n) for n in release[:2] + [999])))
    return sorted(base)


def satisfiable(specs: list[str]) -> bool:
    """True when at least one version satisfies every specifier."""
    sets = [SpecifierSet(s) for s in specs if s]
    if not sets:
        return True
    return any(all(v in s for s in sets) for v in _candidates(specs))


def find_python_drift(
    declarations: list[Declaration], allow: tuple[Allow, ...]
) -> tuple[list[Drift], set[tuple[str, str]], int]:
    drifts: list[Drift] = []
    used_allow: set[tuple[str, str]] = set()
    allowed = {(a.package, a.manifest) for a in allow}

    by_package: dict[str, list[Declaration]] = defaultdict(list)
    for decl in declarations:
        by_package[decl.package].append(decl)

    shared = 0
    for package, decls in sorted(by_package.items()):
        manifests = sorted({d.manifest for d in decls})

        # Same manifest, runtime/extras/groups must agree. Overrides and
        # constraints exist to differ from the declared range, so they are exempt.
        plain = [d for d in decls if not d.origin.startswith("tool.uv")]
        for manifest in manifests:
            specs = {d.specifier for d in plain if d.manifest == manifest}
            if len(specs) > 1:
                where = ", ".join(
                    f"{d.origin}={d.specifier or '*'}" for d in plain if d.manifest == manifest
                )
                drifts.append(Drift("INTRA-MANIFEST", package, f"{manifest}: {where}"))

        if len(manifests) < 2:
            continue
        shared += 1

        specs_all = [d.specifier for d in decls if d.specifier]
        if not satisfiable(specs_all):
            summary = "; ".join(f"{d.manifest} {d.origin}: {d.specifier or '*'}" for d in decls)
            drifts.append(Drift("CONFLICT", package, f"no version satisfies all of: {summary}"))
            continue

        floors: dict[str, Version] = {}
        for manifest in manifests:
            lows = [lb for d in decls if d.manifest == manifest if (lb := lower_bound(d.specifier))]
            if lows:
                floors[manifest] = max(lows)
        if len(set(floors.values())) > 1:
            top = max(floors.values())
            for manifest, floor in sorted(floors.items()):
                if floor == top:
                    continue
                if (package, manifest) in allowed:
                    used_allow.add((package, manifest))
                    continue
                drifts.append(
                    Drift(
                        "FLOOR-DRIFT",
                        package,
                        f"{manifest} floor {floor} trails {top}; raise it or add a "
                        "[[drift.allow]] entry with a reason",
                    )
                )
    return drifts, used_allow, shared


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
