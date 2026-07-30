#!/usr/bin/env python3
"""Validate .claude/commands/*.md files do not exceed the 200-line ceiling.

The slashcommandcreator skill states three times that a command body must be
under 200 lines. Commands exceeding this should be converted to a skill.
Commands that carry irreducible repo-specific content may declare a
size-exception in their YAML frontmatter with a prose rationale in a
leading HTML comment.

Exit codes follow ADR-035:
    0 - Success: All command files within size limits
    1 - Error: One or more files exceed limit (CI mode only)

Related: Issue #4016 (command size ceiling not enforced)
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parents[1]

COMMAND_SIZE_LIMIT = 200
COMMAND_SIZE_WARNING = 150

_FRONTMATTER_RE = re.compile(r"\A---\n(.*?\n)---\n", re.DOTALL)
_EXCEPTION_KEY_RE = re.compile(r"^size-exception\s*:\s*true", re.MULTILINE | re.IGNORECASE)

RATIONALE_SEARCH_LINES = 30
RATIONALE_MIN_CHARS = 40
_RATIONALE_KW_RE = re.compile(r"\brationale\b", re.IGNORECASE)


def _parse_frontmatter(content: str) -> dict[str, str]:
    m = _FRONTMATTER_RE.match(content)
    if not m:
        return {}
    body = m.group(1)
    result: dict[str, str] = {}
    for line in body.splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            result[k.strip()] = v.strip()
    return result


def has_size_exception(content: str) -> bool:
    fm = _parse_frontmatter(content)
    raw = fm.get("size-exception", "")
    return raw.lower() in ("true", "yes", "1")


def has_exception_rationale(content: str) -> bool:
    head = "\n".join(content.splitlines()[:RATIONALE_SEARCH_LINES])
    # Look for an opening comment that contains "rationale" within the window.
    # The comment may close outside the window; we check the opening only.
    open_comments = re.findall(r"<!--(.*?)(?:-->|\Z)", head, re.DOTALL)
    for c in open_comments:
        if _RATIONALE_KW_RE.search(c) and len(c.strip()) >= RATIONALE_MIN_CHARS:
            return True
    return False


@dataclass
class CommandSizeResult:
    path: str
    line_count: int
    passed: bool
    warning: bool = False
    errors: list[str] = field(default_factory=list)


def check_command_size(path: str | Path) -> CommandSizeResult:
    """Check a single command file against the size ceiling."""
    p = Path(path)
    content = p.read_text(encoding="utf-8")
    lines = content.splitlines()
    count = len(lines)

    if count <= COMMAND_SIZE_WARNING:
        return CommandSizeResult(path=str(path), line_count=count, passed=True)

    if count <= COMMAND_SIZE_LIMIT:
        return CommandSizeResult(path=str(path), line_count=count, passed=True, warning=True)

    # Over limit
    if has_size_exception(content):
        if not has_exception_rationale(content):
            return CommandSizeResult(
                path=str(path),
                line_count=count,
                passed=False,
                warning=True,
                errors=["size-exception declared but no rationale comment found in first "
                        f"{RATIONALE_SEARCH_LINES} lines"],
            )
        return CommandSizeResult(path=str(path), line_count=count, passed=True, warning=True)

    return CommandSizeResult(
        path=str(path),
        line_count=count,
        passed=False,
        errors=[
            f"{count} lines exceeds {COMMAND_SIZE_LIMIT}-line ceiling. "
            "Convert to a skill or add size-exception with a rationale comment."
        ],
    )


def get_command_files(
    path: str | None = None,
    changed_files: list[str] | None = None,
) -> list[Path]:
    """Return command .md files to validate."""
    if changed_files is not None:
        return [Path(f) for f in changed_files if f.endswith(".md") and "/commands/" in f and Path(f).exists()]

    if path is None:
        target = _PROJECT_ROOT / ".claude" / "commands"
    else:
        target = Path(path)

    if not target.exists():
        return []
    if target.is_file():
        return [target]
    return sorted(target.glob("*.md"))


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns ADR-035 exit code."""
    parser = argparse.ArgumentParser(
        description="Validate .claude/commands/*.md files against the 200-line ceiling.",
    )
    parser.add_argument(
        "--path",
        default=None,
        help="Path to a command file or directory (default: .claude/commands)",
    )
    parser.add_argument(
        "--ci",
        action="store_true",
        default=os.environ.get("CI", "").lower() in ("true", "1"),
        help="CI mode: exit non-zero on validation failure",
    )
    parser.add_argument(
        "--changed-files",
        nargs="*",
        default=None,
        help="Only check these files (used by lefthook changed-files mode)",
    )
    args = parser.parse_args(argv)

    files = get_command_files(path=args.path, changed_files=args.changed_files)
    if not files:
        print("No command files found to validate.")
        return 0

    print(f"Checking {len(files)} command file(s)...\n")

    failures = 0
    warnings = 0
    for f in files:
        result = check_command_size(f)
        status = "OK" if result.passed and not result.warning else ("WARN" if result.passed else "FAIL")
        if not result.passed:
            failures += 1
            print(f"  [FAIL] {f} ({result.line_count} lines)")
            for e in result.errors:
                print(f"    {e}")
        elif result.warning:
            warnings += 1
            print(f"  [WARN] {f} ({result.line_count} lines)")
        else:
            print(f"  [ OK ] {f} ({result.line_count} lines)")

    print(f"\nSummary: {len(files)} files, {failures} failures, {warnings} warnings")

    if failures and args.ci:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
