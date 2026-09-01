#!/usr/bin/env python3
# taste-lint: ignore file-size -- the guard, its config reader, its exemption
# parser, and its skip-module trust check are one gate with one contract;
# splitting them would let the pieces drift out of sync with what
# tests/validation/test_check_zero_collection_tests.py exercises as a unit.
"""Fail when a file pytest walks into contributes no tests.

A file that matches ``python_files`` inside ``testpaths`` is walked on every CI
and pre-push run. When it defines no test, pytest collects nothing from it and
says nothing about it: the file is inside the tested tree, matches the tested
pattern, and is counted in no failure. Issue #4494 found two such files in
``tests/mutation/``, one of them a mutation harness whose results nobody had
ever read.

The contract this guard reads, verbatim from pyproject.toml:68-69::

    testpaths = ["tests"]
    python_files = ["test_*.py"]

Both are read from the file rather than hardcoded, so widening either one
widens the guard.

Not every such file is a defect. Two in this repository are legitimately not
test suites: ``tests/skills/github/test_helpers.py`` is imported by its
siblings, and ``tests/workflows/test_claude_authorization.py`` is a checker
script ``.github/workflows/claude.yml`` invokes. Those declare themselves with
a ``pytest-zero-collection:`` marker plus a reason. The declaration is checked
in both directions: a declared file that starts collecting tests fails too, so
a marker cannot outlive the reason it was written for.

A module pytest skips during collection answers for itself only when its source
defines a test carrying a registered pytest marker (``markers`` in
``pyproject.toml``, the same signal ``windows_path`` already uses). That
distinguishes a genuine platform-specific suite from a skip-only helper or a
dead test added just to satisfy this guard, without letting either bypass it.
An unconditional module-level ``pytest.skip(..., allow_module_level=True)``
disqualifies the module regardless of what else it defines: pytest's import
machinery marks the whole module skipped the moment such a call executes, so
nothing textually after or around it is ever collected on any host.
``pytest.importorskip(...)`` is different: it is conditional on whether the
named module is importable, so a module using it falls through to the same
registered-marker check as any other conditionally-skipped module.

Exit codes (``AGENTS.md``): 0 ok, 1 violations found, 2 configuration unusable,
3 pytest could not be run or its output could not be parsed.
"""

from __future__ import annotations

import argparse
import ast
import fnmatch
import io
import json
import os
import subprocess
import sys
import tempfile
import tokenize
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import tomllib

EXIT_OK = 0
EXIT_VIOLATIONS = 1
EXIT_CONFIG = 2
EXIT_EXTERNAL = 3

EXEMPTION_MARKER = "pytest-zero-collection:"

# Copilot review round 6 (PR #5344): trusting every registered pytest marker
# leaves the gate bypassable. pyproject.toml also registers ``unit``,
# ``integration``, ``security``, and ``smoke``, none of which selects a
# different runner or environment; a dead test decorated with any of those
# would still pass. Only a marker this repository actually uses to route a
# test to a separately gated environment proves a skipped module is reachable
# elsewhere. Widen this set only alongside a real environment-selection
# mechanism for the new marker, not merely because pyproject.toml declares it.
_ENVIRONMENT_GATED_MARKERS = frozenset({"windows_path"})

# Read the collected set from pytest's own session rather than from its
# console output. ``--collect-only`` renders three different shapes depending
# on net verbosity: a tree, one node id per line, and a ``path: count`` digest.
# Net verbosity is addopts minus command-line flags, so a text parser silently
# changes meaning when someone edits addopts.
_REPORT_PLUGIN_NAME = "_zero_collection_report_plugin"
_REPORT_ENVIRONMENT_VARIABLE = "ZERO_COLLECTION_REPORT"
_REPORT_PLUGIN_SOURCE = '''"""Write the files pytest collected tests from to a JSON report."""

import json
import os

_candidate_modules = []
_skipped_modules = []


def pytest_pycollect_makemodule(module_path, parent):
    """Record each Python module pytest decided to collect."""
    try:
        relative = module_path.relative_to(parent.config.rootpath)
    except ValueError:
        return None
    _candidate_modules.append(relative.as_posix())
    return None


def pytest_collectreport(report):
    """Record a module pytest skipped during collection.

    A module-level ``pytest.skip(..., allow_module_level=True)`` or an
    import-scope ``pytest.importorskip`` raises Skipped while the Module
    collector runs, so the file contributes no session items and would read as
    collecting nothing. The collect report carries the module's nodeid, which
    is the same relative path shape ``session.items`` yields; a nodeid holding
    "::" belongs to a class or a parametrized node, not to a whole module.
    """
    if report.outcome != "skipped":
        return
    nodeid = getattr(report, "nodeid", "")
    if not nodeid or "::" in nodeid:
        return
    _skipped_modules.append(nodeid)


def pytest_collection_finish(session):
    target = os.environ.get("ZERO_COLLECTION_REPORT")
    if not target:
        return
    files = sorted({item.nodeid.split("::", 1)[0] for item in session.items})
    with open(target, "w", encoding="utf-8") as stream:
        json.dump(
            {
                "candidate_modules": sorted(set(_candidate_modules)),
                "files": files,
                "items": len(session.items),
                "python_classes": list(session.config.getini("python_classes")),
                "python_functions": list(session.config.getini("python_functions")),
                "skipped_modules": sorted(set(_skipped_modules)),
            },
            stream,
        )
'''

# Inherited pytest state would reach the child run as extra options or as a
# worker identity it must not adopt (`.claude/rules/testing.md` SHOULD 12).
_STRIPPED_ENVIRONMENT = (
    "PYTEST_ADDOPTS",
    "PYTEST_CURRENT_TEST",
    "PYTEST_XDIST_WORKER",
    "PYTEST_XDIST_WORKER_COUNT",
)


class CollectionError(RuntimeError):
    """pytest could not be run, or its collection output could not be read."""


@dataclass(frozen=True, slots=True)
class Report:
    """What the guard examined and what it found."""

    examined: tuple[str, ...]
    undeclared: tuple[str, ...]
    stale_declarations: tuple[str, ...]
    declared: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CollectionResult:
    """Python modules pytest considered and the items they produced."""

    candidates: tuple[str, ...]
    collected: frozenset[str]
    skipped: frozenset[str]
    python_classes: tuple[str, ...]
    python_functions: tuple[str, ...]


def read_pytest_config(repo_root: Path) -> tuple[list[str], list[str]]:
    """Return ``(testpaths, python_files)`` from ``pyproject.toml``."""
    pyproject = repo_root / "pyproject.toml"
    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"cannot read {pyproject}: {exc}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"cannot parse {pyproject}: {exc}") from exc

    options: object = data
    for section in ("tool", "pytest", "ini_options"):
        if not isinstance(options, Mapping):
            raise ValueError(f"{pyproject} [tool.pytest.ini_options] must be a table")
        options = options.get(section)
    if not isinstance(options, Mapping):
        raise ValueError(f"{pyproject} [tool.pytest.ini_options] must be a table")

    testpaths = options.get("testpaths")
    python_files = options.get("python_files")
    if not isinstance(testpaths, list) or not testpaths:
        raise ValueError(f"{pyproject} has no [tool.pytest.ini_options] testpaths")
    if not isinstance(python_files, list) or not python_files:
        raise ValueError(f"{pyproject} has no [tool.pytest.ini_options] python_files")
    declared_testpaths = _require_nonempty_strings(testpaths, pyproject, "testpaths")
    declared_python_files = _require_nonempty_strings(python_files, pyproject, "python_files")
    for testpath in declared_testpaths:
        resolved = (repo_root / testpath).resolve()
        if not resolved.is_relative_to(repo_root) or not resolved.exists():
            raise ValueError(f"{pyproject} has unusable testpath: {testpath}")
    return declared_testpaths, declared_python_files


def _require_nonempty_strings(values: list[object], pyproject: Path, key: str) -> list[str]:
    """Reject a TOML entry pytest cannot use as a path or glob pattern.

    ``python_files = [1]`` is valid TOML, so ``tomllib`` never raises. Stringifying
    it unconditionally used to hand pytest ``"1"`` as a collection pattern, which
    fails during collection itself (external exit 3) instead of the documented
    configuration exit 2. A non-string or empty-string entry is a malformed
    contract, not an unusable-but-honest one, so it is refused here.
    """
    result: list[str] = []
    for value in values:
        if not isinstance(value, str) or not value:
            raise ValueError(
                f"{pyproject} [tool.pytest.ini_options] {key} entries must be "
                f"non-empty strings, found {value!r}"
            )
        result.append(value)
    return result


def registered_pytest_markers(repo_root: Path) -> frozenset[str]:
    """Return the environment-gated marker names this guard may trust.

    Every entry in ``[tool.pytest.ini_options] markers`` is ``"name:
    description"``, but registration alone is not a signal this guard can
    trust: this repository also registers ``unit``, ``integration``,
    ``security``, and ``smoke``, none of which routes a test to a different
    runner or environment, so a dead test decorated with any of those would
    still buy a bypass. The result is intersected with
    ``_ENVIRONMENT_GATED_MARKERS``, the curated set this repository actually
    uses to select a separately gated environment (``windows_path`` is the
    existing example), so removing a marker from ``pyproject.toml`` also
    revokes this guard's trust in it.
    """
    pyproject = repo_root / "pyproject.toml"
    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return frozenset()
    options: object = data
    for section in ("tool", "pytest", "ini_options"):
        if not isinstance(options, Mapping):
            return frozenset()
        options = options.get(section)
    if not isinstance(options, Mapping):
        return frozenset()
    markers = options.get("markers")
    if not isinstance(markers, list):
        return frozenset()
    names: set[str] = set()
    for entry in markers:
        if isinstance(entry, str) and entry.strip():
            names.add(entry.split(":", 1)[0].strip())
    return frozenset(names) & _ENVIRONMENT_GATED_MARKERS


def _contains_exemption(text: str) -> bool:
    for line in text.splitlines():
        candidate = line.strip()
        if candidate.startswith("#"):
            candidate = candidate[1:].lstrip()
        if not candidate.startswith(EXEMPTION_MARKER):
            continue
        if candidate.removeprefix(EXEMPTION_MARKER).strip():
            return True
    return False


def declares_exemption(text: str) -> bool:
    """True when the file declares itself as deliberately collecting nothing.

    The marker needs a reason after it. A bare marker is an undocumented
    suppression, which `.claude/rules/code-quality.md` rejects, so it does not
    count as a declaration.
    """
    try:
        module = ast.parse(text)
    except SyntaxError:
        return False

    docstring = ast.get_docstring(module, clean=False)
    if docstring and _contains_exemption(docstring):
        return True

    try:
        tokens = tokenize.generate_tokens(io.StringIO(text).readline)
        return any(
            token.type == tokenize.COMMENT and _contains_exemption(token.string)
            for token in tokens
        )
    except tokenize.TokenError:
        return False


def _matches_test_name(name: str, patterns: Sequence[str]) -> bool:
    for pattern in patterns:
        if name.startswith(pattern):
            return True
        if any(character in pattern for character in "*?[") and fnmatch.fnmatch(
            name, pattern
        ):
            return True
    return False


def _defines_collectable_test(
    text: str,
    python_classes: Sequence[str],
    python_functions: Sequence[str],
    registered_markers: frozenset[str],
) -> bool:
    """Return True only when a skipped module is safe to trust without a marker.

    Two conditions, both load-bearing:

    1. No unconditional module-level skip. ``pytest.skip(..., allow_module_level=True)``
       raises ``Skipped`` the moment it executes, and pytest's import machinery
       catches that by marking the WHOLE module skipped without ever
       inspecting what got defined earlier in the same file. A test-shaped
       ``def`` anywhere in a module that also contains an unconditional skip
       is therefore unreachable on every host, not just this one; a walk that
       finds the ``def`` regardless of the skip call is exactly the bypass a
       zero-collecting file could use to dodge this guard by adding a dead
       ``def test_*``. ``pytest.importorskip(...)`` is conditional on module
       availability, not unconditional, and is handled by rule 2 below like
       any other conditional skip.
    2. The candidate test carries ``@pytest.mark.<name>`` where ``<name>`` is
       registered in ``pyproject.toml``'s ``markers`` list (the same signal
       ``windows_path`` already uses). An ``if <condition>: def test(): ...
       else: skip()`` shape cannot be trusted by AST presence alone: the
       condition can name a platform that will never match on any real host,
       which is functionally identical to an unconditional skip. Only a
       registered marker is a decision a maintainer made about a real,
       supported environment; an arbitrary ``if`` is not.
    """
    module = ast.parse(text)
    if any(_is_unconditional_module_skip(stmt) for stmt in module.body):
        return False

    function_types = (ast.FunctionDef, ast.AsyncFunctionDef)
    pending = list(reversed(module.body))
    while pending:
        node = pending.pop()
        if (
            isinstance(node, function_types)
            and _matches_test_name(node.name, python_functions)
            and _has_registered_marker(node.decorator_list, registered_markers)
        ):
            return True
        if isinstance(node, ast.ClassDef):
            if _matches_test_name(node.name, python_classes) and any(
                isinstance(child, function_types)
                and _matches_test_name(child.name, python_functions)
                and _has_registered_marker(child.decorator_list, registered_markers)
                for child in node.body
            ):
                return True
            continue
        if isinstance(node, function_types):
            continue
        statements = [
            child for child in ast.iter_child_nodes(node) if isinstance(child, ast.stmt)
        ]
        pending.extend(reversed(statements))
    return False


def _is_pytest_attr_call(node: ast.expr, attr: str) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == attr
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "pytest"
    )


def _is_unconditional_module_skip(stmt: ast.stmt) -> bool:
    """True for a bare top-level ``pytest.skip(..., allow_module_level=True)``.

    Checked only against ``module.body`` entries directly, never against
    statements nested inside an ``if``/``try``/``for``/``while``: a skip call
    confined to one branch of a conditional does not execute on a host that
    takes the other branch, so it does not disqualify a test defined there.

    ``pytest.importorskip(...)`` is deliberately excluded. Unlike
    ``pytest.skip(..., allow_module_level=True)``, it is not unconditional: it
    returns the imported module and execution continues past it on a host
    where the dependency is installed. Treating it as always-disqualifying
    would fail a normal optional-dependency suite's own registered-marker path
    on every host lacking the dependency, and no exemption can fix that
    without going stale the moment the dependency is installed elsewhere. An
    ``importorskip``-skipped module falls through to the marker check below,
    the same as any other conditionally-skipped module.
    """
    if not isinstance(stmt, ast.Expr) or not isinstance(stmt.value, ast.Call):
        return False
    call = stmt.value
    if _is_pytest_attr_call(call, "skip"):
        return any(
            keyword.arg == "allow_module_level"
            and isinstance(keyword.value, ast.Constant)
            and keyword.value.value is True
            for keyword in call.keywords
        )
    return False


def _has_registered_marker(
    decorators: Sequence[ast.expr], registered_markers: frozenset[str]
) -> bool:
    for decorator in decorators:
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        if (
            isinstance(target, ast.Attribute)
            and isinstance(target.value, ast.Attribute)
            and isinstance(target.value.value, ast.Name)
            and target.value.value.id == "pytest"
            and target.value.attr == "mark"
            and target.attr in registered_markers
        ):
            return True
    return False


def collect_files(repo_root: Path, testpaths: Sequence[str]) -> CollectionResult:
    """Return pytest's candidate modules, collected files, and skipped modules.

    Candidate discovery comes from ``pytest_pycollect_makemodule``. Pytest owns
    directory ignores, configured ``norecursedirs`` globs, conftest
    ``collect_ignore`` entries, and future collection rules. Reimplementing that
    traversal beside pytest creates false violations for files pytest never
    visits.
    """
    with tempfile.TemporaryDirectory(prefix="zero-collection-") as scratch:
        scratch_root = Path(scratch)
        plugin = scratch_root / f"{_REPORT_PLUGIN_NAME}.py"
        plugin.write_text(_REPORT_PLUGIN_SOURCE, encoding="utf-8")
        report = scratch_root / "report.json"

        environment = {
            key: value
            for key, value in os.environ.items()
            if key not in _STRIPPED_ENVIRONMENT
        }
        environment[_REPORT_ENVIRONMENT_VARIABLE] = str(report)
        existing_path = environment.get("PYTHONPATH")
        environment["PYTHONPATH"] = (
            f"{scratch_root}{os.pathsep}{existing_path}" if existing_path else str(scratch_root)
        )

        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-c",
                str(repo_root / "pyproject.toml"),
                "--collect-only",
                "-p",
                _REPORT_PLUGIN_NAME,
                "-p",
                "no:cacheprovider",
                "-q",
                "-q",
                "-q",
                "--",
                *testpaths,
            ],
            cwd=repo_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=environment,
            check=False,
        )
        # 0 is a normal collection; 5 means the whole run collected nothing,
        # which is a legitimate input here because every candidate is then a
        # violation and the report says so. Anything else (a collection error,
        # a usage error) leaves the guard with no evidence.
        if completed.returncode not in (0, 5):
            raise CollectionError(
                f"pytest --collect-only exited {completed.returncode}\n"
                f"{completed.stdout[-2000:]}\n{completed.stderr[-2000:]}"
            )
        try:
            payload = json.loads(report.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CollectionError(
                f"pytest wrote no collection report ({exc}); "
                f"exit was {completed.returncode}\n{completed.stdout[-2000:]}"
            ) from exc
    return CollectionResult(
        candidates=tuple(payload["candidate_modules"]),
        collected=frozenset(payload["files"]),
        skipped=frozenset(payload["skipped_modules"]),
        python_classes=tuple(payload["python_classes"]),
        python_functions=tuple(payload["python_functions"]),
    )


def build_report(repo_root: Path) -> Report:
    """Compare what pytest walks against what answered for itself.

    A path is satisfied when pytest collected a test from it. A skipped module
    is also satisfied when its source defines a test carrying a registered
    pytest marker, which distinguishes a genuine platform-specific suite from
    a skip-only helper or a dead test added to dodge the gate.
    """
    testpaths, _ = read_pytest_config(repo_root)
    registered_markers = registered_pytest_markers(repo_root)
    collection = collect_files(repo_root, testpaths)
    if not collection.candidates:
        raise ValueError("pytest found no candidate modules under configured testpaths")
    examined = collection.candidates

    undeclared: list[str] = []
    stale: list[str] = []
    declared: list[str] = []
    for relative in examined:
        text = (repo_root / relative).read_text(encoding="utf-8")
        exempt = declares_exemption(text)
        satisfied = relative in collection.collected or (
            relative in collection.skipped
            and _defines_collectable_test(
                text,
                collection.python_classes,
                collection.python_functions,
                registered_markers,
            )
        )
        if satisfied:
            if exempt:
                stale.append(relative)
            continue
        if exempt:
            declared.append(relative)
        else:
            undeclared.append(relative)

    return Report(
        examined=tuple(examined),
        undeclared=tuple(undeclared),
        stale_declarations=tuple(stale),
        declared=tuple(declared),
    )


def _print_report(report: Report) -> None:
    print(
        f"zero-collection guard: examined {len(report.examined)} files, "
        f"{len(report.declared)} declared exempt, "
        f"{len(report.undeclared)} collecting nothing, "
        f"{len(report.stale_declarations)} stale declarations"
    )
    for relative in report.undeclared:
        print(
            f"[FAIL] {relative}: collects zero tests. Add test functions, rename "
            f"the file off the test_ prefix, or declare it with a "
            f"'{EXEMPTION_MARKER} <reason>' comment.",
            file=sys.stderr,
        )
    for relative in report.stale_declarations:
        print(
            f"[FAIL] {relative}: declares '{EXEMPTION_MARKER}' but now collects "
            "tests. Remove the declaration.",
            file=sys.stderr,
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="Repository root holding pyproject.toml (default: this repository)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point. Returns an exit code, never a findings list."""
    args = build_parser().parse_args(argv)
    repo_root = args.repo_root.resolve()

    try:
        report = build_report(repo_root)
    except ValueError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return EXIT_CONFIG
    except CollectionError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return EXIT_EXTERNAL

    _print_report(report)
    if report.undeclared or report.stale_declarations:
        return EXIT_VIOLATIONS
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
