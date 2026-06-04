#!/usr/bin/env python3
"""Verify path-like citations in orchestrator prose resolve to real files.

`.claude/commands/pr-quality/all.md` cites the modules that own the verdict
merge and emoji mapping logic (for example
`.claude/lib/ai_review_common/verdict.py:merge_verdicts`). When that logic
moves, the prose citation goes stale and the next reader follows a dead
pointer. Issue #1966 traces a prior stale citation (the removed
`AIReviewCommon.psm1` reference fixed in PR #1934) to the absence of any
lint gate over the orchestrator command file.

This check extracts backtick-wrapped, repo-relative path citations from the
tracked orchestrator command files and fails when a cited path does not
exist on disk. A citation may carry a `:symbol` suffix
(`path/to/file.py:func`); the suffix is stripped before the path is
resolved, because this check verifies the file exists, not the symbol.

Scope: this is a path-existence check, not the mirror-claim heuristic in
`scripts/validation/check_canonical_citations.py`. The two are distinct
concerns and intentionally separate scripts.

EXIT CODES (ADR-035):
  0 - Success (all citations resolve, or no target files present)
  1 - One or more cited paths do not exist (logic/validation error)
  2 - Configuration error (repo root not found)
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

# Orchestrator prose files this check inspects. Relative to repo root.
_TARGET_FILES: tuple[str, ...] = (".claude/commands/pr-quality/all.md",)

# Backtick-wrapped, repo-relative path citation ending in a known source
# extension, with an optional `:symbol` suffix. Requires at least one path
# separator so bare tokens (`main`, `WARN`) and slash commands
# (`/pr-quality:security`) do not match: a slash command has no extension,
# and a bare token has no `/`.
_PATH_CITATION: re.Pattern[str] = re.compile(
    r"`((?:[\w.\-]+/)+[\w.\-]+\.(?:py|md|ps1|json|yml|yaml|sh|ts|js|cs))(?::[\w.]+)?`"
)


@dataclass(frozen=True)
class BrokenCitation:
    """A cited path that does not resolve to an existing file."""

    source: str
    path: str


def extract_path_citations(text: str) -> list[str]:
    """Return repo-relative path citations (symbol suffix stripped)."""
    return _PATH_CITATION.findall(text)


def check_file(repo_root: Path, rel_source: str) -> list[BrokenCitation]:
    """Return broken citations found in one target file.

    A target file that is absent yields no broken citations; a downstream
    installer may not ship the orchestrator command, and that is benign.
    """
    source_path = repo_root / rel_source
    if not source_path.is_file():
        return []

    text = source_path.read_text(encoding="utf-8")
    broken: list[BrokenCitation] = []
    for cited in extract_path_citations(text):
        if not (repo_root / cited).exists():
            broken.append(BrokenCitation(source=rel_source, path=cited))
    return broken


def collect_broken_citations(repo_root: Path) -> list[BrokenCitation]:
    """Scan every target file and return all broken citations."""
    broken: list[BrokenCitation] = []
    for rel_source in _TARGET_FILES:
        broken.extend(check_file(repo_root, rel_source))
    return broken


def format_report(broken: list[BrokenCitation]) -> str:
    """Format a human-readable report of broken citations."""
    if not broken:
        return "[PASS] All orchestrator path citations resolve.\n"

    lines = [
        f"[FAIL] {len(broken)} broken path citation(s) in orchestrator prose.",
        "",
        "A backtick path citation points to a file that does not exist.",
        "Update the citation to the current path, or restore the file.",
        "",
    ]
    for item in broken:
        lines.append(f"  - {item.source} cites {item.path!r} (not found)")
    lines.append("")
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Verify orchestrator path citations resolve to real files.",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Repository root (defaults to the script's grandparent).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns an ADR-035 exit code."""
    args = parse_args(argv)

    repo_root = args.repo_root
    if repo_root is None:
        repo_root = Path(__file__).resolve().parent.parent.parent

    if not repo_root.is_dir():
        print(f"[FAIL] repo root not found: {repo_root}", file=sys.stderr)
        return 2

    broken = collect_broken_citations(repo_root)
    print(format_report(broken), end="")
    return 1 if broken else 0


if __name__ == "__main__":
    raise SystemExit(main())
