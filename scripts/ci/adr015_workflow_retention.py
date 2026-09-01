#!/usr/bin/env python3
"""ADR-015 artifact retention compliance scanner.

ADR-015 (Artifact Storage Minimization Strategy, 2025-12-22) mandates:

- Operational / temporary artifacts: ``retention-days: 1`` (same-run handoff)
- All other artifacts: ``retention-days: 7`` (metrics, test results, reports)

Any other value is a deviation.  This scanner finds every ``retention-days:``
declaration in ``.github/workflows/`` and reports those that do not conform.

To record an approved exception, add an entry to ``_EXCEPTIONS`` (see below)
with the workflow file stem, the allowed value, and a justification that cites
the approving issue or ADR amendment.  The empty dict means no exceptions are
currently approved.

Exit codes (AGENTS.md):
    0 - all ``retention-days`` values conform (no violations)
    1 - at least one non-conforming value found
    2 - configuration error (workflows directory missing or unreadable)

Call sites so the gate is not vacuous (Issue #3329):
    ``tests/ci/test_adr015_workflow_retention.py::test_all_workflow_retention_conform``
    runs ``violations()`` against the live workflow tree.
    ``test_scanner_finds_values_in_real_tree`` proves the scanner is not
    returning an empty list (isolating negative control).

Issue: #3981
ADR:   .agents/architecture/ADR-015-artifact-storage-minimization.md
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

EXIT_OK = 0
EXIT_LOGIC = 1
EXIT_CONFIG = 2

# ADR-015 Decision: the only permitted retention-days values.
# 1 = operational/temporary (same-run handoff artifacts)
# 7 = standard (test results, metrics, analysis outputs)
ALLOWED_DAYS: frozenset[int] = frozenset({1, 7})

# Approved exceptions: (workflow-file-stem, retention_days) -> justification.
# Add entries here ONLY after the exception is recorded in an ADR amendment or
# issue and reviewed.  Keeping this dict visible in source makes exceptions
# auditable in code review rather than buried in workflow YAML comments.
_EXCEPTIONS: dict[tuple[str, int], str] = {}

# Matches ``retention-days: <value>`` with optional leading whitespace and
# trailing inline comment.  The capture group accepts any non-whitespace token
# so that expression-style values (``${{ inputs.days }}``, ``$RETENTION_DAYS``)
# are captured and flagged as violations rather than silently skipped.
# Does not require a full YAML parse because retention-days always appears as a
# scalar in an ``upload-artifact`` ``with:`` block.
_RETENTION_RE = re.compile(r"^\s*retention-days:\s*(\S+.*?)\s*(?:#.*)?$")

_WORKFLOW_GLOBS = ("*.yml", "*.yaml")

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOWS_DIR = _REPO_ROOT / ".github" / "workflows"


@dataclass(frozen=True)
class RetentionEntry:
    """One ``retention-days:`` declaration found in a workflow file."""

    file: Path
    line_no: int  # 1-based
    value: int | str  # int for numeric literals; str for expression-style values


def scan_text(text: str, path: Path) -> list[RetentionEntry]:
    """Return every ``retention-days:`` entry found in *text*.

    Parameters
    ----------
    text:
        Raw YAML content.
    path:
        Path to associate with the returned entries (used in messages).
    """
    entries: list[RetentionEntry] = []
    for i, line in enumerate(text.splitlines(), start=1):
        m = _RETENTION_RE.match(line)
        if m is not None:
            raw = m.group(1).strip()
            try:
                parsed: int | str = int(raw)
            except ValueError:
                parsed = raw
            entries.append(RetentionEntry(file=path, line_no=i, value=parsed))
    return entries


def scan_directory(directory: Path) -> list[RetentionEntry]:
    """Return all ``RetentionEntry`` objects from workflow YAML files under *directory*.

    Files are sorted so output is deterministic across platforms.
    """
    entries: list[RetentionEntry] = []
    for glob in _WORKFLOW_GLOBS:
        for path in sorted(directory.glob(glob)):
            text = path.read_text(encoding="utf-8")
            entries.extend(scan_text(text, path))
    return entries


def is_conforming(entry: RetentionEntry) -> bool:
    """Return True when *entry* satisfies ADR-015 policy.

    An entry is conforming when its value is in ``ALLOWED_DAYS`` or has an
    entry in ``_EXCEPTIONS`` for its workflow file.  Non-integer values (e.g.
    GitHub Actions expressions) are always violations because they cannot be
    statically verified to conform.
    """
    if not isinstance(entry.value, int):
        return False
    if entry.value in ALLOWED_DAYS:
        return True
    return (entry.file.stem, entry.value) in _EXCEPTIONS


def violations(entries: list[RetentionEntry]) -> list[RetentionEntry]:
    """Return the subset of *entries* that violate ADR-015."""
    return [e for e in entries if not is_conforming(e)]


def _format_entry(entry: RetentionEntry, repo_root: Path) -> str:
    try:
        rel: Path | str = entry.file.relative_to(repo_root)
    except ValueError:
        rel = entry.file
    return f"  {rel}:{entry.line_no}: retention-days: {entry.value}"


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="ADR-015 artifact retention compliance scanner",
    )
    parser.add_argument(
        "--workflows-dir",
        type=Path,
        default=_WORKFLOWS_DIR,
        help="Directory containing workflow YAML files (default: .github/workflows)",
    )
    args = parser.parse_args(argv)

    if not args.workflows_dir.is_dir():
        print(
            f"[CONFIG] workflows directory not found: {args.workflows_dir}",
            file=sys.stderr,
        )
        return EXIT_CONFIG

    try:
        entries = scan_directory(args.workflows_dir)
    except (PermissionError, OSError) as exc:
        print(
            f"[CONFIG] cannot read workflows directory: {exc}",
            file=sys.stderr,
        )
        return EXIT_CONFIG
    bad = violations(entries)
    if bad:
        allowed = sorted(ALLOWED_DAYS)
        print(f"ADR-015 retention violations ({len(bad)}/{len(entries)}) -- allowed: {allowed}")
        for entry in bad:
            print(_format_entry(entry, _REPO_ROOT))
        return EXIT_LOGIC
    print(f"ADR-015: all {len(entries)} retention-days values conform.")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
