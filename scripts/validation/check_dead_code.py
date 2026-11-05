#!/usr/bin/env python3
"""Blocking gate: ruff's ARG rules may report no unused argument outside the baseline.

The gate runs ``ruff check --select ARG`` with JSON output over the tracked
Python files under ``SCAN_ROOTS``. ruff resolves each name in its own scope, so
a parameter named ``path`` or ``args`` is reported when that function never
reads it, even if another function uses the same name. It reports unused
function, method, class-method, static-method, and lambda arguments
(``ARG001`` to ``ARG005``).

What it does not catch: unused imports, unused functions, classes, variables,
or attributes, and unreachable code. ``check_unreachable_code.py`` covers
unreachable statements; the repo-wide ruff ``F`` rules cover unused imports.
ARG is not in the repo-wide ruff ``select``: adding it there would turn every
listed finding red in the other ruff gates.

Each finding is keyed as ``<path>: <code> <argument>``, with no line number, so
an edit elsewhere in a file does not churn the key. The findings must equal the
committed baseline in ``dead_code_baseline.txt`` next to this script.
It runs as the pre-push ``python-dead-code`` job, the ``Dead Code Detection``
gate in ``pre_pr.py``, and a step in the ``pytest`` workflow:

- A finding the baseline does not list fails the gate. Use the argument, or
  remove it. A leading underscore marks an argument as intentionally unused.
- A baseline entry ruff no longer reports also fails the gate, so the
  baseline can only shrink. Delete the line in the same change that fixed it.

Two unused arguments with the same name in one file share a key, so the gate
sees the count per file and name, not which function holds it.

``tests/validation/test_check_dead_code.py`` pins the baseline length, so an
added line fails until a reviewer sees that constant move.

The scan reads only files git tracks under the scan roots, so an untracked
draft cannot fail a push that CI, checking out the same commit, passes. A
tracked file reads its working-tree content.

Exit codes (ADR-035):
    0 - Success (findings equal the baseline)
    1 - Logic error (new finding or stale baseline entry)
    2 - Config error (bad baseline, unreadable source, nothing scanned, repo
        root not a git work tree, git or ruff not installed or failing)
    3 - External error (git or ruff timed out)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

REPO_ROOT = Path(__file__).resolve().parents[2]
BASELINE_RELPATH = Path("scripts/validation/dead_code_baseline.txt")
KEY_SEPARATOR = ": "

# Canonical sources of the [tool.coverage.run] roots: .claude/skills links into
# src/claude/skills, and the .claude/hooks and src/claude/hooks trees render
# from templates/hooks, so each file is scanned once at its source.
SCAN_ROOTS = ("scripts", "src/claude", "templates/hooks", ".claude/lib")

# Generated copies and linked files under the scan roots. A path equal to an
# entry, or under an entry that ends in "/", is skipped. Test trees are skipped
# by directory name in _is_excluded.
EXCLUDED_PATHS = (
    "src/claude/hooks/",
    "src/claude/lib/ai_review_common/",
    "src/claude/lib/bootstrap.py",
    "src/claude/lib/failure_classifier/",
    "src/claude/lib/github_core/",
    "src/claude/lib/hook_utilities/",
    "src/claude/skills/review/scripts/validate_review_marker.py",
    ".claude/lib/bootstrap.py",
    ".claude/lib/paths.py",
)

GIT_TIMEOUT_SECONDS = 30
RUFF_TIMEOUT_SECONDS = 60
# Windows caps a command line near 32K characters; batch the file list.
RUFF_BATCH_SIZE = 200

_ARG_CODE = re.compile(r"ARG\d{3}")
_ARGUMENT_NAME = re.compile(r"`([^`]+)`")


class GateConfigError(RuntimeError):
    """Raised when the gate cannot trust its inputs."""


class ExternalToolError(RuntimeError):
    """Raised when a tool the gate runs does not finish in time."""


@dataclass(frozen=True)
class ScanResult:
    """Finding keys plus the number of first-party files ruff read."""

    keys: list[str]
    scanned_files: int


@dataclass(frozen=True)
class Comparison:
    """Findings outside the baseline and baseline entries with no finding."""

    new: list[str]
    stale: list[str]


def parse_baseline(text: str) -> list[str]:
    """Return baseline keys, skipping blank lines and ``#`` comments."""
    keys: list[str] = []
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        path, sep, message = line.partition(KEY_SEPARATOR)
        if not sep or not path or not message:
            raise GateConfigError(f"baseline line {lineno} is not '<path>: <message>': {raw!r}")
        keys.append(line)
    return keys


def load_baseline(path: Path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise GateConfigError(f"cannot read baseline {path}: {exc}") from exc
    return parse_baseline(text)


def compare(findings: Iterable[str], baseline: Iterable[str]) -> Comparison:
    """Compare as multisets: two identical findings need two baseline lines."""
    found = Counter(findings)
    allowed = Counter(baseline)
    return Comparison(
        new=sorted((found - allowed).elements()),
        stale=sorted((allowed - found).elements()),
    )


def _clean_git_env() -> dict[str, str]:
    """Return the process environment without ambient Git repository pointers."""
    return {key: value for key, value in os.environ.items() if not key.upper().startswith("GIT_")}


def _is_excluded(relpath: str) -> bool:
    if "tests" in PurePosixPath(relpath).parts:
        return True
    return any(
        relpath.startswith(entry) if entry.endswith("/") else relpath == entry
        for entry in EXCLUDED_PATHS
    )


def tracked_python_files(repo_root: Path, roots: Sequence[str] = SCAN_ROOTS) -> list[Path]:
    """Return the tracked regular ``.py`` files under ``roots``, as absolute paths."""
    try:
        listing = subprocess.run(
            ["git", "ls-files", "-z", "--stage", "--", *roots],
            cwd=repo_root,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            env=_clean_git_env(),
            timeout=GIT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise ExternalToolError(
            f"dead-code gate: git ls-files timed out after {GIT_TIMEOUT_SECONDS}s"
        ) from exc
    except OSError as exc:
        raise GateConfigError(f"cannot run git: {exc}") from exc
    if listing.returncode != 0:
        raise GateConfigError(
            f"git ls-files failed under {repo_root}: {listing.stderr.strip() or 'no output'}"
        )
    files: list[Path] = []
    for entry in listing.stdout.split("\0"):
        meta, sep, relpath = entry.partition("\t")
        if not sep or not relpath.endswith(".py") or _is_excluded(relpath):
            continue
        # A symlink's target is scanned at its own path when it is in scope.
        # A deletion not yet committed has no file to read.
        if meta.startswith("120000 "):
            continue
        path = repo_root / relpath
        if path.is_file():
            files.append(path)
    return files


def _run_ruff(repo_root: Path, ruff: str, batch: Sequence[Path]) -> list[dict[str, object]]:
    try:
        completed = subprocess.run(
            [
                ruff,
                "check",
                "--select",
                "ARG",
                "--output-format",
                "json",
                "--no-cache",
                "--force-exclude",
                "--",
                *map(str, batch),
            ],
            cwd=repo_root,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            env=_clean_git_env(),
            timeout=RUFF_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise ExternalToolError(
            f"dead-code gate: ruff timed out after {RUFF_TIMEOUT_SECONDS}s"
        ) from exc
    except OSError as exc:
        raise GateConfigError(f"cannot run ruff: {exc}") from exc
    # ruff exits 0 with no findings and 1 with findings; anything else is a failure.
    if completed.returncode not in (0, 1):
        raise GateConfigError(
            f"ruff exited {completed.returncode}: {completed.stderr.strip() or 'no output'}"
        )
    try:
        parsed = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise GateConfigError(f"ruff did not print JSON: {exc}") from exc
    return parsed


def _finding_key(item: dict[str, object], resolved_root: Path) -> str:
    code = item.get("code")
    filename = str(item.get("filename", ""))
    if not (isinstance(code, str) and _ARG_CODE.fullmatch(code)):
        # ruff reports a syntax error as an entry whose code is not an ARG rule.
        raise GateConfigError(f"ruff could not parse {filename}: {item.get('message')}")
    match = _ARGUMENT_NAME.search(str(item.get("message", "")))
    if match is None:
        raise GateConfigError(f"ruff {code} message names no argument: {item.get('message')!r}")
    relative = Path(filename).resolve().relative_to(resolved_root)
    return f"{relative.as_posix()}{KEY_SEPARATOR}{code} {match.group(1)}"


def scan(repo_root: Path) -> ScanResult:
    """Run ``ruff check --select ARG`` over the tracked files in scope."""
    ruff = shutil.which("ruff")
    if ruff is None:
        raise GateConfigError("ruff is not installed; run `uv sync --extra dev`")
    files = tracked_python_files(repo_root)
    if not files:
        raise GateConfigError(f"no tracked Python files under {list(SCAN_ROOTS)}")
    resolved_root = repo_root.resolve()
    keys: list[str] = []
    for start in range(0, len(files), RUFF_BATCH_SIZE):
        for item in _run_ruff(repo_root, ruff, files[start : start + RUFF_BATCH_SIZE]):
            keys.append(_finding_key(item, resolved_root))
    return ScanResult(keys=sorted(keys), scanned_files=len(files))


def validate(repo_root: Path, baseline_path: Path) -> bool:
    """Return True when ruff's ARG findings equal the baseline."""
    baseline = load_baseline(baseline_path)
    result = scan(repo_root)
    outcome = compare(result.keys, baseline)
    if not outcome.new and not outcome.stale:
        print(
            f"check_dead_code: OK. Scanned {result.scanned_files} Python file(s); "
            f"{len(result.keys)} finding(s), all in the baseline of {len(baseline)}."
        )
        return True
    for key in outcome.new:
        print(f"  new unused argument: {key}", file=sys.stderr)
    for key in outcome.stale:
        print(f"  stale baseline entry: {key}", file=sys.stderr)
    print(
        f"\ncheck_dead_code: {len(outcome.new)} new finding(s) and "
        f"{len(outcome.stale)} stale baseline line(s) across "
        f"{result.scanned_files} scanned file(s). Use or remove each new argument; never add it "
        f"to the baseline. Delete each stale line from {baseline_path.name}.",
        file=sys.stderr,
    )
    return False


def validate_dead_code(repo_root: Path) -> bool:
    """pre_pr gate entry point. Fails closed when the scan cannot run."""
    try:
        return validate(repo_root, repo_root / BASELINE_RELPATH)
    except (GateConfigError, ExternalToolError) as exc:
        print(f"error: dead-code gate did not run: {exc}", file=sys.stderr)
        return False


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument(
        "--baseline", type=Path, default=None, help=f"default: <repo-root>/{BASELINE_RELPATH}"
    )
    args = parser.parse_args(argv)
    repo_root = args.repo_root.resolve()
    baseline = args.baseline if args.baseline is not None else repo_root / BASELINE_RELPATH
    try:
        return 0 if validate(repo_root, baseline) else 1
    except GateConfigError as exc:
        print(f"error: dead-code gate did not run: {exc}", file=sys.stderr)
        return 2
    except ExternalToolError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
