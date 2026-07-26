#!/usr/bin/env python3
"""Assert every hand-written ``pkg==version`` pin in ``.github/`` YAML agrees
with ``pyproject.toml`` (Issue #3377).

Two CI install steps pinned pytest by hand and disagreed with each other::

    .github/workflows/validate-generated-agents.yml   pytest==9.0.3
    .github/actions/validate-plugin-manifests/action.yml   pytest==8.3.3

``pyproject.toml`` declares ``pytest>=9.0.3``, so the action installed a pytest
the project does not support. Nothing caught it: both pins are string literals
in YAML with no gate comparing them to the source of truth.

The cost is not the stale pin itself. A reader looking at two disagreeing
literals cannot tell which is authoritative without opening ``pyproject.toml``,
so "align them" resolves toward the wrong one about half the time. That is
exactly what happened on PR #3361: a review proposed aligning down to 8.3.3 and
an autofix commit downgraded the correct pin.

This is the converse-assertion shape of Issues #3341 and #3371: something
asserts the pin exists, nothing asserts it agrees with the source of truth.

Scope, stated so a reader does not infer coverage that is not here:

* Workflow and action YAML under ``.github/`` only. A pin in a requirements
  file, a shell script, a Dockerfile, or a composite action written in another
  format is not read.
* A pin is checked only when ``pyproject.toml`` declares that package. CI
  installs tools the project does not depend on (``pip`` itself, for one), and
  those carry no constraint to disagree with.
* Quoted and unquoted pins both count. ``pytest==9.0.3`` and
  ``'pytest==9.0.3'`` install the same version, so keying on the quotes would
  let an unquoted pin drift silently.

Call sites, because a guard with none protects nothing (Issue #3329):

* ``tests/validation/test_check_ci_dependency_pins.py::TestTheRealTree`` runs
  ``check`` against this repository under the required "Run Python Tests"
  check, alongside a negative control proving the scan is not vacuous.
* ``checks_tooling.validate_ci_dependency_pins`` puts it in the pre-PR
  sequence for the author's terminal.

ADR-006 keeps the logic here rather than in workflow YAML. ADR-042 mandates
Python for new scripts.

Exit codes (ADR-035):
    0 - every checked pin satisfies its declared constraint
    1 - at least one pin violates its constraint (logic failure)
    2 - pyproject.toml or the scan root is missing or unparseable (config)
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import tomllib
from packaging.requirements import InvalidRequirement, Requirement
from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version

EXIT_OK = 0
EXIT_LOGIC = 1
EXIT_CONFIG = 2

_REPO_ROOT = Path(__file__).resolve().parents[2]

# A pin as it appears in a shell ``run:`` line: pytest==9.0.3, quoted or not.
# Both spellings install the same version, so keying on the quotes would let an
# unquoted pin drift silently.
#
# What keeps YAML's own ``==`` out: GitHub expressions space their operator
# (``env.FOO == '1'``), the lookbehind rejects ``===`` and mid-token matches,
# and a version must start with a digit, so ``foo==bar`` is not a pin.
_PIN_RE = re.compile(
    r"""(?<![A-Za-z0-9._=-])['"]?([A-Za-z][A-Za-z0-9._-]*)==([0-9][A-Za-z0-9._*+!-]*)"""
)


@dataclass(frozen=True)
class Pin:
    """One ``pkg==version`` literal found in a CI file."""

    path: Path
    line: int
    name: str
    version: str

    @property
    def canonical(self) -> str:
        return canonicalize_name(self.name)


@dataclass(frozen=True)
class Violation:
    """A pin that does not satisfy the constraint pyproject declares."""

    pin: Pin
    constraint: str

    def render(self, repo_root: Path) -> str:
        """Render relative to the repository root, not the scan root.

        The scan root is ``.github/``; showing a path relative to it would
        print ``workflows/pytest.yml``, which is not a path anyone can open
        from where they are standing.
        """
        try:
            shown = self.pin.path.relative_to(repo_root)
        except ValueError:
            shown = self.pin.path
        return (
            f"{shown}:{self.pin.line}: {self.pin.name}=={self.pin.version} "
            f"violates pyproject constraint '{self.pin.name}{self.constraint}'"
        )


def declared_constraints(pyproject: Path) -> dict[str, SpecifierSet]:
    """Return canonical package name -> combined specifier from pyproject.

    Merges ``[project].dependencies`` with every entry under
    ``[project.optional-dependencies]``. A package declared in more than one
    place contributes all of its specifiers, so a pin must satisfy the
    intersection. That is the honest reading: CI installs one version, and it
    has to work everywhere the project claims to need the package.
    """
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    project = data.get("project", {})
    groups: list[list[str]] = [list(project.get("dependencies", []))]
    for extra in project.get("optional-dependencies", {}).values():
        groups.append(list(extra))
    for group in data.get("dependency-groups", {}).values():
        if isinstance(group, list):
            groups.append([item for item in group if isinstance(item, str)])

    merged: dict[str, SpecifierSet] = {}
    for group in groups:
        for raw in group:
            try:
                req = Requirement(raw)
            except InvalidRequirement:
                continue
            if not req.specifier:
                continue
            key = canonicalize_name(req.name)
            merged[key] = merged.get(key, SpecifierSet()) & req.specifier
    return merged


def find_pins(root: Path) -> list[Pin]:
    """Return every ``pkg==version`` literal under ``root``, quoted or not.

    Scans ``.yml`` and ``.yaml`` only. A pin in a Python or shell file is
    installed the same way, but those files are covered by the dependency
    resolver rather than by hand-written literals, and widening the scan
    turns ordinary equality comparisons into false positives.

    Per-file errors (I/O failures, encoding issues) are logged and skipped so
    that one unreadable file does not abort the scan of other pins.
    """
    pins: list[Pin] = []
    for path in sorted(root.rglob("*")):
        if path.suffix.lower() not in {".yml", ".yaml"} or not path.is_file():
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            print(f"::warning::skipping {path}: {exc}", file=sys.stderr)
            continue
        for number, text in enumerate(content.splitlines(), 1):
            # Skip YAML/shell comment lines: a pin mentioned in a comment is not
            # an active install (Issue #3377 comment-stripping fix).  Only
            # leading-# lines are dropped; trailing # can appear inside quotes
            # or parameter expansions (${VAR#pat}), so stripping there mangles
            # live commands.
            if text.lstrip().startswith("#"):
                continue
            for name, version in _PIN_RE.findall(text):
                pins.append(Pin(path=path, line=number, name=name, version=version))
    return pins


def violations(pins: list[Pin], constraints: dict[str, SpecifierSet]) -> list[Violation]:
    """Return the pins that contradict a declared constraint."""
    found: list[Violation] = []
    for pin in pins:
        specifier = constraints.get(pin.canonical)
        if specifier is None:
            continue
        try:
            parsed = Version(pin.version)
        except InvalidVersion:
            found.append(Violation(pin=pin, constraint=str(specifier)))
            continue
        # prereleases=True so a pinned release candidate is judged against the
        # constraint rather than silently excluded and reported as passing.
        if not specifier.contains(parsed, prereleases=True):
            found.append(Violation(pin=pin, constraint=str(specifier)))
    return found


def check(root: Path, pyproject: Path) -> int:
    """Validate every pin under ``root`` and return an exit code."""
    if not pyproject.is_file():
        print(f"::error::pyproject.toml not found: {pyproject}", file=sys.stderr)
        return EXIT_CONFIG
    if not root.is_dir():
        print(f"::error::scan root not found: {root}", file=sys.stderr)
        return EXIT_CONFIG

    try:
        constraints = declared_constraints(pyproject)
    except (tomllib.TOMLDecodeError, InvalidSpecifier, OSError, UnicodeDecodeError) as exc:
        print(f"::error::cannot read constraints from {pyproject}: {exc}", file=sys.stderr)
        return EXIT_CONFIG

    found = violations(find_pins(root), constraints)
    if not found:
        return EXIT_OK

    for violation in found:
        print(f"::error::{violation.render(_REPO_ROOT)}", file=sys.stderr)
    print(
        f"::error::{len(found)} CI pin(s) contradict pyproject.toml. "
        f"Update the pin, not pyproject, unless the floor itself is wrong.",
        file=sys.stderr,
    )
    return EXIT_LOGIC


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--root", default=str(_REPO_ROOT / ".github"), help="directory to scan")
    parser.add_argument(
        "--pyproject", default=str(_REPO_ROOT / "pyproject.toml"), help="constraint source"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return check(Path(args.root), Path(args.pyproject))


if __name__ == "__main__":
    raise SystemExit(main())
