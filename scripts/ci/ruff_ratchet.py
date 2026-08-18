#!/usr/bin/env python3
"""Fail on ruff violations that land on lines this change added or modified.

Issue #2993. This gate used to lint whole changed files, so editing one clean
line of a file that already carried debt inherited every pre-existing finding
in it and blocked the push. Measured on ``origin/main`` at 4f5a12c: 27 tracked
violations across 11 files, every one of which was a tripwire for unrelated
work. The gate now reports those findings but blocks only when a finding's
reported row range intersects an added or modified line.

The whole-tree ceiling still lives in ``scripts/ci/ruff_count_ratchet.py``:
this gate stops new authored debt, that one stops the total from growing by any
other route. Neither can be dropped for the other.

Fail-closed behavior: an unresolvable diff base, a git failure, or ruff output
that will not parse all block on every finding, so the gate is never weaker
than the whole-file check it replaces.

Exit codes (AGENTS.md contract):
    0 - ok (no findings, or only findings outside the change)
    1 - a finding intersects an added or modified line
    2 - config error (repo root is not a git worktree, bad args)
    3 - external error (git or ruff could not run, unparseable ruff output)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.ci.diff_line_scope import (
    changed_line_map,
    intersects_changed_lines,
    normalize_path,
)

EXIT_OK = 0
EXIT_VIOLATIONS = 1
EXIT_CONFIG = 2
EXIT_EXTERNAL = 3

_ZERO_SHA = re.compile(r"^0+$")
_FALLBACK_BASE_REF = "origin/main"


def default_base_ref() -> str:
    if os.environ.get("GITHUB_EVENT_NAME") == "push":
        return _FALLBACK_BASE_REF

    raw_base_ref = os.environ.get("RUFF_RATCHET_BASE_REF", "").strip()
    if raw_base_ref and _ZERO_SHA.fullmatch(raw_base_ref) is None:
        return raw_base_ref
    return _FALLBACK_BASE_REF


def git_diff_name_only(base_ref: str, repo_root: Path) -> subprocess.CompletedProcess[str]:
    # ``-z`` emits NUL-separated raw names. Without it git C-quotes any path
    # holding a quote, a backslash, or a control character, and the quoted form
    # never matches the path ruff reports, so the file silently left the scope.
    return subprocess.run(
        [
            "git",
            "-C",
            str(repo_root),
            "diff",
            "--name-only",
            "-z",
            "--diff-filter=ACMR",
            f"{base_ref}...HEAD",
        ],
        check=False,
        capture_output=True,
        text=True,
        errors="replace",
        encoding="utf-8",
    )


def changed_python_files(base_ref: str, repo_root: Path) -> tuple[int, list[str], str]:
    """Return the status, the changed Python files, and the base ref that worked.

    The resolved ref is returned, not assumed: when the requested ref is stale
    the file list comes from the fallback, and building the line map from the
    stale ref would fail, drop the map to ``None``, and block on every finding
    in every changed file. That is the whole-file behavior this gate replaces.
    """
    resolved = base_ref
    result = git_diff_name_only(base_ref, repo_root)
    if result.returncode != 0 and base_ref != _FALLBACK_BASE_REF:
        resolved = _FALLBACK_BASE_REF
        result = git_diff_name_only(_FALLBACK_BASE_REF, repo_root)
    if result.returncode != 0:
        print(result.stderr.strip(), file=sys.stderr)
        return EXIT_EXTERNAL, [], resolved

    files = [
        name
        for name in result.stdout.split("\0")
        if name.endswith(".py") and (repo_root / name).is_file()
    ]
    return EXIT_OK, files, resolved


def relative_finding_path(filename: str, repo_root: Path) -> str | None:
    """Map a ruff-reported filename onto a repo-relative, forward-slash path.

    Ruff reports absolute filenames in JSON, so this mapping is load-bearing.
    ``None`` means the path could not be placed inside the repository; callers
    block on that finding rather than passing it, because a key that can never
    match the changed-line map would silently make every finding in that file
    non-blocking.
    """
    candidate = Path(filename)
    if not candidate.is_absolute():
        return normalize_path(filename)
    try:
        return normalize_path(str(candidate.relative_to(repo_root)))
    except ValueError:
        return None


def _row_of(payload: object, fallback: int) -> int:
    """Read a ``row`` out of a ruff location, defaulting when it is absent."""
    if not isinstance(payload, dict):
        return fallback
    row = payload.get("row")
    return row if isinstance(row, int) else fallback


def finding_rows(finding: dict[str, object]) -> tuple[int, int]:
    """Return the inclusive ``(start_row, end_row)`` a ruff finding covers.

    ``end_location`` is absent on some ruff diagnostics, and ruff already emits
    a null ``row`` on others (``noqa_row``); the start row then stands for the
    whole range. Reading these defensively keeps a malformed payload from
    raising out of ``main``, where the interpreter's exit 1 would be
    indistinguishable from ``EXIT_VIOLATIONS``.
    """
    start_row = _row_of(finding.get("location"), 1)
    return start_row, _row_of(finding.get("end_location"), start_row)


def describe(finding: dict[str, object], path: str, start_row: int) -> str:
    location = finding.get("location")
    column = location.get("column", 1) if isinstance(location, dict) else 1
    code = finding.get("code") or "RUFF"
    message = finding.get("message", "")
    return f"{path}:{start_row}:{column}: {code} {message}"


def report(
    findings: Sequence[dict[str, object]],
    repo_root: Path,
    changed_lines: dict[str, set[int]] | None,
) -> list[str]:
    """Print every finding and return the ones that block.

    Pre-existing findings stay visible so the debt is never hidden; only the
    blocking ones are emitted as GitHub annotations, which is what turns a CI
    run red.
    """
    blocking: list[str] = []
    pre_existing: list[str] = []
    for finding in findings:
        raw_filename = str(finding.get("filename", ""))
        path = relative_finding_path(raw_filename, repo_root)
        start_row, end_row = finding_rows(finding)
        line = describe(finding, path or raw_filename, start_row)
        if path is None or intersects_changed_lines(changed_lines, path, start_row, end_row):
            blocking.append(line)
            print(f"::error file={path or raw_filename},line={start_row}::{line}")
        else:
            pre_existing.append(line)

    if pre_existing:
        print(
            f"Pre-existing ruff findings outside this change "
            f"({len(pre_existing)}, not blocking):"
        )
        for line in pre_existing:
            print(f"  {line}")
    return blocking


def run_ruff(
    files: Sequence[str],
    repo_root: Path,
    changed_lines: dict[str, set[int]] | None,
) -> int:
    if not files:
        print("No changed Python files found. Ruff ratchet passed.")
        return EXIT_OK

    result = subprocess.run(
        ["ruff", "check", "--output-format=json", "--", *files],
        check=False,
        capture_output=True,
        cwd=repo_root,
        text=True,
        errors="replace",
        encoding="utf-8",
    )
    if result.stderr:
        print(result.stderr, file=sys.stderr, end="")

    if result.returncode not in (0, 1):
        return EXIT_EXTERNAL
    if result.returncode == 0:
        print(f"Ruff ratchet passed for {len(files)} changed Python file(s).")
        return EXIT_OK

    try:
        findings = json.loads(result.stdout or "[]")
    except json.JSONDecodeError as error:
        print(f"error: could not parse ruff JSON output: {error}", file=sys.stderr)
        return EXIT_EXTERNAL
    if not isinstance(findings, list):
        print("error: ruff JSON output was not a list of findings", file=sys.stderr)
        return EXIT_EXTERNAL

    parsed = [item for item in findings if isinstance(item, dict)]
    blocking = report(parsed, repo_root, changed_lines)
    if blocking:
        print(
            f"Ruff ratchet failed: {len(blocking)} finding(s) on lines this change "
            f"added or modified across {len(files)} changed Python file(s).",
            file=sys.stderr,
        )
        return EXIT_VIOLATIONS
    print(
        f"Ruff ratchet passed for {len(files)} changed Python file(s): "
        "no findings on added or modified lines."
    )
    return EXIT_OK


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run ruff only on lines changed since a base ref."
    )
    parser.add_argument(
        "--base-ref",
        default=default_base_ref(),
        help="Git ref used as the diff base (default: RUFF_RATCHET_BASE_REF or origin/main).",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path.cwd(),
        help="Repository root (default: current working directory).",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    repo_root = args.repo_root.resolve()
    if not (repo_root / ".git").exists():
        print(f"error: {repo_root} is not a git worktree", file=sys.stderr)
        return EXIT_CONFIG

    status, files, resolved_base_ref = changed_python_files(args.base_ref, repo_root)
    if status != EXIT_OK:
        return status
    changed_lines = changed_line_map(resolved_base_ref, repo_root, files)
    if changed_lines is None:
        print(
            f"warning: diff base {resolved_base_ref} unresolvable; "
            "blocking on every ruff finding in the changed files",
            file=sys.stderr,
        )
    return run_ruff(files, repo_root, changed_lines)


if __name__ == "__main__":
    sys.exit(main())
