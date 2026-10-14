#!/usr/bin/env python3
"""Fail when an added Markdown line states a tree-state count with no anchor.

A count that describes the current state of this repository ("109 skills in
`.claude/skills/`", "9,765 tracked files") is a measurement of one commit.
Without a commit SHA, ISO date, or version tag on the same line, a later
reader cannot tell "still true" from "was true once". Issue #5771 carries
the incident record: a 49-skill claim sat unflagged while the tree held 111.

Deliberate scope, in the design of ``check_citation_freshness.py``:

* Added lines only (``base...HEAD``), so the existing backlog is never
  re-policed and the gate passes on day one. ``--tree`` prints the backlog
  at HEAD for a human; it is the corpus demonstration
  ``.claude/rules/ci-scripts.md`` item 13 asks of a PR that adds a gate.
* Tracked ``.md`` files and ``.md.tmpl`` skill sources, minus point-in-time
  records (``HISTORICAL_ROOTS`` from ``stale_script_refs.py`` plus the
  extras below) and generated mirrors. Those trees state what was true when
  they were written, or are rendered from a source this gate already reads.
* The trigger is the narrow one in ``measurement_claims.py``; the loose
  "integer plus noun" definition was measured at 1,882 lines with roughly
  one genuine claim per 25 sampled.

Escape hatch: ``measurement-anchor: ignore -- <reason>`` on the flagged line
or the line above; line-scoped, no whole-gate skip.

EXIT CODES (ADR-035): 0 = no findings (prints examined counts so an idle
run is distinguishable from a clean one) or no base ref resolved (prints
``[SKIP]``); 1 = findings; 2 = configuration error (git itself failed)."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent.parent
# checks_common transitively imports ``scripts.cli_exec`` (absolute), so the
# repo root must be importable even when this runs as a plain script.
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from checks_common import _resolve_default_base_ref  # noqa: E402
from citation_head_state import (  # noqa: E402
    HeadReadError,
    _added_lines_since_base,
    _head_tracked_paths,
    _HeadFileCache,
)
from measurement_claims import (  # noqa: E402
    IGNORE_MARKER,
    fenced_line_numbers,
    has_reasoned_ignore,
    is_heading,
    unanchored_claims,
)
from stale_script_refs import HISTORICAL_ROOTS  # noqa: E402

_SCANNED_SUFFIXES = (".md", ".md.tmpl")

# Dated records beyond stale_script_refs's tuple: episode memory, PR comment
# captures, per-issue handoffs, and incident reviews all describe a moment.
_EXTRA_HISTORICAL_ROOTS = (
    ".project-toolkit/memory/",
    ".project-toolkit/pr-comments/",
    ".project-toolkit/handoffs/",
    ".project-toolkit/incidents/",
)

# Rendered from templates/ by build/scripts/build_all.py; the template source
# is the tree-state claim's author, so the mirror is read once, at the source.
_GENERATED_ROOTS = (
    "src/claude/",
    "src/codex/",
    "src/copilot-cli/",
    ".github/instructions/",
    ".claude/rules/",
    ".claude/agents/",
)
_GENERATED_SKILL_FILE = "SKILL.md"
_SKILLS_ROOT = ".claude/skills/"

_FIXTURE_FRAGMENT = "/fixtures/"


@dataclass(frozen=True)
class Finding:
    """One unanchored tree-state count."""

    path: str
    line: int
    claim: str

    def format(self) -> str:
        """Return the finding in file:line: claim: reason form."""
        return (
            f"{self.path}:{self.line}: {self.claim!r}: tree-state count has no "
            f"commit SHA, ISO date, or version tag on the line"
        )


def is_out_of_scope(path: str) -> bool:
    """Return whether the gate must not read this tracked path."""
    if not path.endswith(_SCANNED_SUFFIXES):
        return True
    if path.startswith((*HISTORICAL_ROOTS, *_EXTRA_HISTORICAL_ROOTS, *_GENERATED_ROOTS)):
        return True
    if path.startswith(_SKILLS_ROOT) and path.rsplit("/", 1)[-1] == _GENERATED_SKILL_FILE:
        return True
    return _FIXTURE_FRAGMENT in f"/{path}"


def _findings_for_file(
    path: str, numbered: list[tuple[int, str]], head_files: _HeadFileCache
) -> list[Finding]:
    """Return the findings among the given (line number, text) pairs of one file."""
    lines = head_files.lines(path)
    fenced = fenced_line_numbers(lines)
    found: list[Finding] = []
    for number, text in numbered:
        if number in fenced or is_heading(text):
            continue
        claims = unanchored_claims(text)
        if claims and not has_reasoned_ignore(lines, number, text):
            found.extend(Finding(path, number, claim) for claim in claims)
    return found


def _scan(
    candidates: dict[str, list[tuple[int, str]]], head_files: _HeadFileCache
) -> tuple[list[Finding], int, int]:
    """Scan candidate lines; return (findings, lines examined, files examined)."""
    findings: list[Finding] = []
    examined_lines = 0
    examined_files = 0
    for path in sorted(candidates):
        if is_out_of_scope(path):
            continue
        examined_files += 1
        examined_lines += len(candidates[path])
        findings.extend(_findings_for_file(path, candidates[path], head_files))
    return findings, examined_lines, examined_files


def _whole_tree_candidates(
    tracked: set[str], head_files: _HeadFileCache
) -> dict[str, list[tuple[int, str]]]:
    """Treat every line of every in-scope tracked file at HEAD as added."""
    return {
        path: list(enumerate(head_files.lines(path), 1))
        for path in sorted(tracked)
        if not is_out_of_scope(path)
    }


def find_unanchored_counts(
    repo_root: Path, base_ref: str | None
) -> tuple[list[Finding], str] | None:
    """Return (findings, scope label), or None on git failure.

    ``base_ref`` None scans the whole tree at HEAD instead of the added lines.
    """
    tracked = _head_tracked_paths(repo_root)
    if tracked is None:
        return None
    head_files = _HeadFileCache(repo_root)
    try:
        if base_ref is None:
            candidates = _whole_tree_candidates(tracked, head_files)
            label = "every line at HEAD"
        else:
            added = _added_lines_since_base(repo_root, base_ref)
            if added is None:
                return None
            candidates = added
            label = f"added lines vs {base_ref}"
        findings, lines, files = _scan(candidates, head_files)
    except HeadReadError as error:
        print(f"[measurement-anchoring] git could not read {error} at HEAD", file=sys.stderr)
        return None
    print(f"[measurement-anchoring] examined {lines} line(s) across {files} file(s): {label}")
    return findings, label


def _report(findings: list[Finding]) -> None:
    """Print each finding plus the one-line remediation footer."""
    for finding in findings:
        print(finding.format())
    if findings:
        print(
            f"[measurement-anchoring] {len(findings)} unanchored count(s). Add the "
            f"commit SHA or ISO date the count was measured at to the same line, "
            f"rephrase it so it states no count, or mark a deliberate exception "
            f"with '{IGNORE_MARKER} -- <reason>' on the line or the line above."
        )


def validate_measurement_anchoring(repo_root: Path) -> bool:
    """Gate entry point: print findings, return True when clean.

    Resolving no base ref prints ``[SKIP]`` and passes: with no base there is
    no added-lines range to make claims about.
    """
    base_ref = _resolve_default_base_ref(repo_root)
    if base_ref is None:
        print("[SKIP] measurement-anchoring: no base ref resolved; nothing to diff against")
        return True
    outcome = find_unanchored_counts(repo_root, base_ref)
    if outcome is None:
        print("[measurement-anchoring] git failed while reading repository state", file=sys.stderr)
        return False
    _report(outcome[0])
    return not outcome[0]


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""
    parser = argparse.ArgumentParser(
        description="Fail when an added Markdown line states a tree-state count with no anchor."
    )
    parser.add_argument("--repo-root", default=".", help="Repository root path.")
    parser.add_argument(
        "--base",
        default=None,
        help="Base ref to diff against (default: resolved like pre_pr's other gates).",
    )
    parser.add_argument(
        "--tree",
        action="store_true",
        help="Scan every in-scope line at HEAD instead of the added lines (backlog report).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the measurement-anchoring check as a CLI."""
    args = build_parser().parse_args(argv)
    repo_root = Path(args.repo_root).resolve()
    if not (repo_root / ".git").exists():
        print(f"[measurement-anchoring] not a git repository: {repo_root}", file=sys.stderr)
        return 2

    base_ref = None
    if not args.tree:
        base_ref = args.base or _resolve_default_base_ref(repo_root)
        if base_ref is None:
            print("[SKIP] measurement-anchoring: no base ref resolved; nothing to diff against")
            return 0

    outcome = find_unanchored_counts(repo_root, base_ref)
    if outcome is None:
        print("[measurement-anchoring] git failed while reading repository state", file=sys.stderr)
        return 2
    _report(outcome[0])
    return 1 if outcome[0] else 0


if __name__ == "__main__":
    raise SystemExit(main())
