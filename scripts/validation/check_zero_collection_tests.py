#!/usr/bin/env python3
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

Exit codes (``AGENTS.md``): 0 ok, 1 violations found, 2 configuration unusable,
3 pytest could not be run or its output could not be parsed.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import tomllib

EXIT_OK = 0
EXIT_VIOLATIONS = 1
EXIT_CONFIG = 2
EXIT_EXTERNAL = 3

EXEMPTION_MARKER = "pytest-zero-collection:"

# pytest's own default ``norecursedirs``, plus ``__pycache__``. A file under one
# of these is never collected, so reporting it would be a false positive.
_SKIPPED_DIRECTORY_NAMES = frozenset(
    {"__pycache__", "build", "dist", "node_modules", "venv", "CVS", "_darcs"}
)

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


def pytest_collection_finish(session):
    target = os.environ.get("ZERO_COLLECTION_REPORT")
    if not target:
        return
    files = sorted({item.nodeid.split("::", 1)[0] for item in session.items})
    with open(target, "w", encoding="utf-8") as stream:
        json.dump({"files": files, "items": len(session.items)}, stream)
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


def read_pytest_config(repo_root: Path) -> tuple[list[str], list[str]]:
    """Return ``(testpaths, python_files)`` from ``pyproject.toml``."""
    pyproject = repo_root / "pyproject.toml"
    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"cannot read {pyproject}: {exc}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"cannot parse {pyproject}: {exc}") from exc

    options = data.get("tool", {}).get("pytest", {}).get("ini_options", {})
    testpaths = options.get("testpaths")
    python_files = options.get("python_files")
    if not isinstance(testpaths, list) or not testpaths:
        raise ValueError(f"{pyproject} has no [tool.pytest.ini_options] testpaths")
    if not isinstance(python_files, list) or not python_files:
        raise ValueError(f"{pyproject} has no [tool.pytest.ini_options] python_files")
    return [str(path) for path in testpaths], [str(pattern) for pattern in python_files]


def _is_walked(relative: Path) -> bool:
    return not any(
        part.startswith(".") or part.endswith(".egg") or part in _SKIPPED_DIRECTORY_NAMES
        for part in relative.parts[:-1]
    )


def candidate_files(
    repo_root: Path, testpaths: Sequence[str], python_files: Sequence[str]
) -> list[str]:
    """Every path pytest would walk into and try to collect from."""
    found: set[str] = set()
    for testpath in testpaths:
        base = repo_root / testpath
        entries = [base] if base.is_file() else sorted(base.rglob("*.py"))
        for entry in entries:
            relative = entry.relative_to(repo_root)
            if not _is_walked(relative):
                continue
            if any(fnmatch.fnmatch(entry.name, pattern) for pattern in python_files):
                found.add(relative.as_posix())
    return sorted(found)


def declares_exemption(text: str) -> bool:
    """True when the file declares itself as deliberately collecting nothing.

    The marker needs a reason after it. A bare marker is an undocumented
    suppression, which `.claude/rules/code-quality.md` rejects, so it does not
    count as a declaration.
    """
    for line in text.splitlines():
        _, separator, reason = line.partition(EXEMPTION_MARKER)
        if separator and reason.strip():
            return True
    return False


def collect_files(repo_root: Path, testpaths: Sequence[str]) -> set[str]:
    """Return every path pytest collected at least one test from."""
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
                *testpaths,
                "--collect-only",
                "-p",
                _REPORT_PLUGIN_NAME,
                "-p",
                "no:cacheprovider",
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
    return set(payload["files"])


def build_report(repo_root: Path) -> Report:
    """Compare what pytest walks against what it collected."""
    testpaths, python_files = read_pytest_config(repo_root)
    examined = candidate_files(repo_root, testpaths, python_files)
    collected = collect_files(repo_root, testpaths)

    undeclared: list[str] = []
    stale: list[str] = []
    declared: list[str] = []
    for relative in examined:
        exempt = declares_exemption((repo_root / relative).read_text(encoding="utf-8"))
        if relative in collected:
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
