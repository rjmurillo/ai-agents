#!/usr/bin/env python3
"""Verify every runner-exception marker in a workflow names a live ADR (issue #5199).

A workflow that runs off the ARM default carries a `# ADR-NNN Exception:` comment
(ADR-055, "Exception Documentation Format"). The comment is an audit trail, and it
rots the way a citation rots: ADR-055 itself prescribed `# ADR-032 Exception:` until
PR #1604 renumbered it from ADR-032 and left the body unswept, and the retired spellings
`# ADR-024 Exception:` and `# ADR-014 Exception:` stayed loose in the tree. No
gate read the pattern, so a marker could name an ADR that does not exist, or one
that a later record retired, and still pass.

This gate scans `.github/workflows/*.yml` and `*.yaml`, plus every
`.github/actions/**/action.yml` and `action.yaml`, for the marker and checks
each cited number against `.project-toolkit/architecture/ADR-NNN-*.md`:

    missing   no ADR file carries that number
    retired   the ADR's frontmatter `status` is superseded, deprecated, or rejected
    unread    the ADR's frontmatter `status` cannot be read (unparseable, absent,
              or not a scalar), so the marker cannot be shown to name a live ADR

A comment that looks like a marker but would not match is a near miss and also
fails the gate: `# ADR 055 Exception:`, `# ADR-055 Exception` (no colon),
`# ADR-055: Exception`, or a misspelled word such as `Exeption`. A marker no gate
can read is an audit trail nobody checks. Only a comment that starts with
`# ADR` is examined, so prose such as `(ADR-055 exception)` is left alone.

A marker can be written as a whole-line comment or trailing a YAML key. An ADR
with no readable status fails the marker (issue #6506): passing on existence
alone would let a retired record with broken frontmatter stand as live. The
`ADR Lifecycle Frontmatter (ratchet)` gate still owns the frontmatter defect;
this gate only refuses to vouch for the marker until it is fixed. Whether
the cited ADR is about runner selection is a review question. Only existence and
status are machine-checkable.

The tree holds no marker today, so the gate carries no baseline: any marker that
fails is a new violation.

Exit codes (per ADR-035):
    0 - every marker names a live ADR (or the tree holds no marker)
    1 - one or more markers name a missing, retired, or unreadable-status ADR,
        or are misspelled
    2 - config error (a directory is missing, or a workflow cannot be read)
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.validation.check_adr_uniqueness import ADR_FILENAME_RE
from scripts.validation.frontmatter_contract import FrontmatterStatus, parse_frontmatter

EXIT_OK = 0
EXIT_VIOLATION = 1
EXIT_CONFIG = 2

ADR_DIR = Path(".project-toolkit") / "architecture"
WORKFLOW_DIR = Path(".github") / "workflows"
ACTIONS_DIR = Path(".github") / "actions"

# `# ADR-055 Exception:`, case-insensitive, any spacing around the words.
MARKER_RE = re.compile(r"#\s*ADR-(?P<number>\d+)\s+Exception\s*:", re.IGNORECASE)

# A comment that starts like a marker: `#` at the start of a line or after whitespace,
# `ADR`, a number, an optional separator, then the next word. The word is compared with
# "exception" to catch a misspelling. The `(?<!\S)` guard keeps a URL fragment such as
# `https://h/p#adr-7-exception` from reading as a comment.
CANDIDATE_RE = re.compile(
    r"(?<!\S)#\s*ADR[\s_-]*(?P<number>\d+)\s*[:,-]?\s*(?P<word>[A-Za-z]+)", re.IGNORECASE
)
NEAR_MISS_WORD = "exception"
# "Exeption" and "Exceptions" score 0.94; "except" scores 0.80 and stays unflagged.
NEAR_MISS_RATIO = 0.85

# Statuses that retire a record. `proposed` and `accepted` are live.
RETIRED_STATUSES: frozenset[str] = frozenset({"superseded", "deprecated", "rejected"})


@dataclass(frozen=True, slots=True)
class Marker:
    """One exception marker found in a workflow."""

    path: str
    line: int
    number: int


@dataclass(frozen=True, slots=True)
class NearMiss:
    """A comment that looks like a marker but does not match `MARKER_RE`."""

    path: str
    line: int
    text: str


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


def _action_files(repo_root: Path) -> list[Path]:
    """Composite and local actions: `.github/actions/**/action.y*ml` (issue #6506)."""
    actions_dir = repo_root / ACTIONS_DIR
    return sorted([*actions_dir.glob("**/action.yml"), *actions_dir.glob("**/action.yaml")])


def find_near_miss(line: str) -> str | None:
    """Return the comment text when ``line`` holds a marker-like comment `MARKER_RE` misses."""
    for match in CANDIDATE_RE.finditer(line):
        if MARKER_RE.match(line, match.start()):
            continue
        ratio = SequenceMatcher(None, match.group("word").lower(), NEAR_MISS_WORD).ratio()
        if ratio >= NEAR_MISS_RATIO:
            return line[match.start() :].strip()
    return None


def scan_markers(repo_root: Path, workflow_dir: Path) -> tuple[list[Marker], list[NearMiss], int]:
    """Return every marker, every near miss, and the count of workflow files examined."""
    markers: list[Marker] = []
    near_misses: list[NearMiss] = []
    files = [*_workflow_files(workflow_dir), *_action_files(repo_root)]
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
            if (miss := find_near_miss(line)) is not None:
                near_misses.append(NearMiss(rel, number, miss))
    return markers, near_misses, len(files)


def judge(marker: Marker, statuses: dict[int, str]) -> str | None:
    """Return the violation text for ``marker``, or None when it names a live ADR."""
    cite = f"ADR-{marker.number:03d}"
    if marker.number not in statuses:
        return f"{marker.path}:{marker.line}: {cite} does not exist under {ADR_DIR.as_posix()}/"
    status = statuses[marker.number]
    if not status:
        return (
            f"{marker.path}:{marker.line}: {cite} has no readable frontmatter status, "
            f"so the marker cannot be shown to name a live ADR; fix the record's frontmatter"
        )
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
        markers, near_misses, examined = scan_markers(repo_root, workflow_dir)
    except ConfigError as exc:
        print(f"[CONFIG] {exc}", file=sys.stderr)
        return EXIT_CONFIG
    statuses = collect_adr_statuses(adr_dir)
    problems = [text for m in markers if (text := judge(m, statuses)) is not None]
    problems += [
        f"{n.path}:{n.line}: near-miss marker {n.text!r}; write it as `# ADR-NNN Exception:`"
        for n in near_misses
    ]
    summary = f"{len(markers)} marker(s) in {examined} workflow file(s)"
    if problems:
        header = (
            "[FAIL] Runner-exception markers cite a missing, retired, or unreadable-status ADR,"
            " or are misspelled"
        )
        print(f"{header} ({summary}):")
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
