#!/usr/bin/env python3
"""Fail when a tracked prescription names a push-lock path that is not canonical.

``flock`` excludes only processes that open the same path, so a second lock name
is not a second lock: it is no lock at all against the first. Three schemes were
live at once on 2026-08-02 and the only way anyone found out was a ``ps`` census
(issue #4366). This checker makes a fourth scheme visible at commit time.

The canonical form is fixed by ``.claude/rules/push-lock.md``:

    flock "$HOME/src/scratch/locks/push-lock-$SLUG.lock" git push origin "$BR"

Scope is prescriptive Markdown only. A retrospective or an audit that records
what an old scheme looked like is evidence, not a recipe, so those trees are
skipped wholesale; a fenced block elsewhere opts out by carrying the token
``push-lock-historical`` on a line inside the fence.

EXIT CODES (ADR-035):
  0 - every prescription agrees (prints the examined count)
  1 - at least one non-canonical lock path
  2 - configuration or runtime error
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path

CANONICAL_TEMPLATE = '"$HOME/src/scratch/locks/push-lock-<slug>.lock"'
HISTORICAL_MARKER = "push-lock-historical"

# Trees whose whole purpose is recording what already happened.
EXCLUDED_PREFIXES = (
    ".agents/retrospective/",
    ".agents/audits/",
    ".agents/archive/",
)

_FLOCK_PATH = re.compile(r"\bflock\b[^\n]*?([\"']?)(\S*?\.lock)\1")
_CANONICAL_PATH = re.compile(
    r"^(?:\$HOME|\$\{HOME\})/src/scratch/locks/push-lock-[^/]*\.lock$"
)
_FENCE = re.compile(r"^\s*(?:```|~~~)")


def is_canonical(path: str) -> bool:
    """Return True when ``path`` matches the one sanctioned lock filename shape."""
    return bool(_CANONICAL_PATH.match(path.strip("\"'")))


def _fenced_blocks(lines: Sequence[str]) -> list[tuple[int, int]]:
    """Return (start, end) line indices for each fenced block, end exclusive."""
    blocks: list[tuple[int, int]] = []
    start: int | None = None
    for index, line in enumerate(lines):
        if not _FENCE.match(line):
            continue
        if start is None:
            start = index
        else:
            blocks.append((start, index + 1))
            start = None
    if start is not None:
        blocks.append((start, len(lines)))
    return blocks


def _historical_line_numbers(lines: Sequence[str]) -> set[int]:
    """Return the 1-based line numbers inside blocks marked historical."""
    skipped: set[int] = set()
    for start, end in _fenced_blocks(lines):
        block = lines[start:end]
        if any(HISTORICAL_MARKER in line for line in block):
            skipped.update(range(start + 1, end + 1))
    return skipped


def scan_text(text: str) -> list[tuple[int, str]]:
    """Return (line number, offending path) for every non-canonical lock path."""
    lines = text.splitlines()
    skipped = _historical_line_numbers(lines)
    findings: list[tuple[int, str]] = []
    for index, line in enumerate(lines, start=1):
        if index in skipped:
            continue
        for match in _FLOCK_PATH.finditer(line):
            candidate = match.group(2)
            if not is_canonical(candidate):
                findings.append((index, candidate))
    return findings


def tracked_markdown(repo_root: Path) -> list[str]:
    """Return tracked Markdown paths in scope, read from HEAD (ci-scripts MUST 9)."""
    result = subprocess.run(
        ["git", "-C", str(repo_root), "ls-tree", "-r", "-z", "--name-only", "HEAD"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git ls-tree failed: {result.stderr.strip()}")
    paths = [entry for entry in result.stdout.split("\0") if entry.endswith(".md")]
    return [path for path in paths if not path.startswith(EXCLUDED_PREFIXES)]


def check_paths(repo_root: Path, paths: Iterable[str]) -> tuple[list[str], int]:
    """Return (violation messages, examined file count)."""
    violations: list[str] = []
    examined = 0
    for relative in paths:
        target = repo_root / relative
        try:
            text = target.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        examined += 1
        for line_number, candidate in scan_text(text):
            violations.append(
                f"{relative}:{line_number}: push lock '{candidate}' is not "
                f"{CANONICAL_TEMPLATE} (see .claude/rules/push-lock.md, issue #4366)"
            )
    return violations, examined


def validate_push_lock_paths(repo_root: Path) -> bool:
    """Return True when every tracked prescription names the canonical lock path.

    Entry point matching the ``validate_*(repo_root) -> bool`` contract used by
    ``pre_pr.py``.
    """
    try:
        paths = tracked_markdown(repo_root)
    except (RuntimeError, OSError) as error:
        print(f"[FAIL] push-lock check could not read HEAD: {error}", file=sys.stderr)
        return False
    violations, examined = check_paths(repo_root, paths)
    if not violations:
        print(f"[PASS] push-lock: 0 violation(s) in {examined} tracked Markdown file(s)")
        return True
    print(
        f"[FAIL] {len(violations)} push-lock path(s) in {examined} tracked Markdown "
        "file(s) disagree with the canonical form:",
        file=sys.stderr,
    )
    for violation in violations:
        print(f"  {violation}", file=sys.stderr)
    return False


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo-root", default=".")
    args = parser.parse_args(argv)
    repo_root = Path(args.repo_root).resolve()
    try:
        paths = tracked_markdown(repo_root)
    except (RuntimeError, OSError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    violations, examined = check_paths(repo_root, paths)
    for violation in violations:
        print(violation, file=sys.stderr)
    print(f"push-lock: {len(violations)} violation(s) in {examined} tracked Markdown file(s)")
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
