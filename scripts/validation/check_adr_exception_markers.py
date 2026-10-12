#!/usr/bin/env python3
"""Verify every runner-exception marker in a workflow names a live ADR (issue #5199).

A workflow that runs off the ARM default carries a `# ADR-NNN Exception:` comment
(ADR-055, "Exception Documentation Format"). The comment is an audit trail, and it
rots the way a citation rots: ADR-055 once prescribed `# ADR-032 Exception:` for
the same reason that ADR-032 was renumbered away, and the retired spellings
`# ADR-024 Exception:` and `# ADR-014 Exception:` stayed loose in the tree. No
gate read the pattern, so a marker could name an ADR that does not exist, or one
that a later record retired, and still pass.

This gate scans `.github/workflows/*.yml` and `*.yaml` for the marker and checks
each cited number against `.project-toolkit/architecture/ADR-NNN-*.md`:

    missing   no ADR file carries that number
    retired   the ADR's frontmatter `status` is superseded, deprecated, or rejected

A marker can be written as a whole-line comment or trailing a YAML key. An ADR
with no readable frontmatter has an unknown status and passes on existence; the
`ADR Lifecycle Frontmatter (ratchet)` gate owns the frontmatter defect. Whether
the cited ADR is about runner selection is a review question. Only existence and
status are machine-checkable.

The tree holds no marker today, so the gate carries no baseline: any marker that
fails is a new violation.

Exit codes (per ADR-035):
    0 - every marker names a live ADR (or the tree holds no marker)
    1 - one or more markers name a missing or retired ADR
    2 - config error (a directory is missing, or a workflow cannot be read)
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.validation.check_adr_uniqueness import ADR_FILENAME_RE
from scripts.validation.frontmatter_contract import FrontmatterStatus, parse_frontmatter

EXIT_OK = 0
EXIT_VIOLATION = 1
EXIT_CONFIG = 2

ADR_DIR = Path(".project-toolkit") / "architecture"
WORKFLOW_DIR = Path(".github") / "workflows"

# `# ADR-055 Exception:`, case-insensitive, any spacing around the words.
MARKER_RE = re.compile(r"#\s*ADR-(?P<number>\d+)\s+Exception\s*:", re.IGNORECASE)

# Statuses that retire a record. `proposed` and `accepted` are live.
RETIRED_STATUSES: frozenset[str] = frozenset({"superseded", "deprecated", "rejected"})


@dataclass(frozen=True, slots=True)
class Marker:
    """One exception marker found in a workflow."""

    path: str
    line: int
    number: int


class ConfigError(Exception):
    """A directory is missing or a file cannot be read; the run measured nothing."""


def _status_of(path: Path) -> str:
    """Lowercased frontmatter status, or "" when unreadable, absent, or not a scalar."""
    try:
        result = parse_frontmatter(path.read_text(encoding="utf-8"), allow_duplicate_keys=True)
    except (OSError, UnicodeDecodeError):
        return ""
    if result.status is not FrontmatterStatus.VALID or result.metadata is None:
        return ""
    value = result.metadata.get("status")
    if value is None or isinstance(value, (list, dict)):
        return ""
    return str(value).strip().lower()


def collect_adr_statuses(adr_dir: Path) -> dict[int, str]:
    """Return {adr_number: status}; status is "" when it cannot be read."""
    statuses: dict[int, str] = {}
    for md in sorted(adr_dir.glob("ADR-*.md")):
        match = ADR_FILENAME_RE.match(md.name)
        if match:
            statuses.setdefault(int(match.group(1)), _status_of(md))
    return statuses


def _workflow_files(workflow_dir: Path) -> list[Path]:
    return sorted([*workflow_dir.glob("*.yml"), *workflow_dir.glob("*.yaml")])


def scan_markers(repo_root: Path, workflow_dir: Path) -> tuple[list[Marker], int]:
    """Return every marker plus the count of workflow files examined."""
    markers: list[Marker] = []
    files = _workflow_files(workflow_dir)
    for wf in files:
        rel = wf.relative_to(repo_root).as_posix()
        try:
            text = wf.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise ConfigError(f"cannot read {rel}: {exc}") from exc
        for number, line in enumerate(text.splitlines(), start=1):
            match = MARKER_RE.search(line)
            if match:
                markers.append(Marker(rel, number, int(match.group("number"))))
    return markers, len(files)


def judge(marker: Marker, statuses: dict[int, str]) -> str | None:
    """Return the violation text for ``marker``, or None when it names a live ADR."""
    cite = f"ADR-{marker.number:03d}"
    if marker.number not in statuses:
        return f"{marker.path}:{marker.line}: {cite} does not exist under {ADR_DIR.as_posix()}/"
    status = statuses[marker.number]
    if status in RETIRED_STATUSES:
        return (
            f"{marker.path}:{marker.line}: {cite} is {status}; "
            f"cite the ADR that replaced it (ADR-055 for runner selection)"
        )
    return None


def run(repo_root: Path) -> int:
    """Scan ``repo_root`` and print the verdict. Returns the process exit code."""
    adr_dir = repo_root / ADR_DIR
    workflow_dir = repo_root / WORKFLOW_DIR
    for label, directory in (("ADR architecture", adr_dir), ("workflows", workflow_dir)):
        if not directory.is_dir():
            print(f"[CONFIG] {label} directory not found: {directory}", file=sys.stderr)
            return EXIT_CONFIG
    try:
        markers, examined = scan_markers(repo_root, workflow_dir)
    except ConfigError as exc:
        print(f"[CONFIG] {exc}", file=sys.stderr)
        return EXIT_CONFIG
    statuses = collect_adr_statuses(adr_dir)
    problems = [text for m in markers if (text := judge(m, statuses)) is not None]
    summary = f"{len(markers)} marker(s) in {examined} workflow file(s)"
    if problems:
        print(f"[FAIL] Runner-exception markers cite a missing or retired ADR ({summary}):")
        for text in problems:
            print(f"  - {text}")
        return EXIT_VIOLATION
    print(f"[PASS] Every runner-exception marker names a live ADR ({summary}).")
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="Repository root (defaults to two levels above this script).",
    )
    args = parser.parse_args(argv)
    return run(args.repo_root)


def validate_adr_exception_markers(repo_root: Path) -> bool:
    """Pre-PR gate adapter: True only on a clean pass.

    A config error (exit 2) returns False. A gate that could not read its inputs
    has not run, and reporting that as a pass is the silent-pass failure
    `.claude/rules/ci-scripts.md` MUST 11 and 12 exist to stop.
    """
    return run(repo_root) == EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
