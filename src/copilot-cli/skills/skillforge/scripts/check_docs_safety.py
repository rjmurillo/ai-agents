"""
check_docs_safety.py - Guard against unsafe hook command examples in docs.

Flags markdown lines where $TOOL_INPUT or $TOOL_OUTPUT appear in command
strings without explicit quoting.

Usage:
    python scripts/check_docs_safety.py
    python scripts/check_docs_safety.py skills/my-skill/
    python scripts/check_docs_safety.py SKILL.md references/script-integration-framework.md

With no argument it scans this skill's SKILL.md and two reference files. A
directory argument scans that skill's SKILL.md plus every references/*.md. A
file argument scans that file.

Exit codes:
    0 - no unsafe patterns found (the scanned file count is printed)
    1 - unsafe patterns found
    2 - bad input: unreadable path, or a directory with no markdown to scan
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def default_targets(repo_root: Path) -> list[Path]:
    return [
        repo_root / "SKILL.md",
        repo_root / "references" / "script-integration-framework.md",
        repo_root / "references" / "synthesis-protocol.md",
    ]


def is_unquoted_tool_var(line: str, var: str) -> bool:
    token_a = f"${var}"
    token_b = f"${{{var}}}"
    if token_a not in line and token_b not in line:
        return False

    safe_forms = (
        f'"${var}"',
        f'"${{{var}}}"',
    )
    return not any(safe in line for safe in safe_forms)


def scan_file(path: Path) -> list[str]:
    issues: list[str] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception as exc:
        raise RuntimeError(f"Cannot read {path}: {exc}") from exc

    for idx, line in enumerate(lines, start=1):
        if "command:" not in line:
            continue
        if is_unquoted_tool_var(line, "TOOL_INPUT") or is_unquoted_tool_var(line, "TOOL_OUTPUT"):
            issues.append(f"{path}:{idx}: {line.strip()}")
    return issues


def expand_target(target: Path) -> list[Path]:
    """Return the files to scan for one CLI argument.

    A directory expands to its SKILL.md plus references/**/*.md. Any other
    path is returned as-is so scan_file reports an unreadable file.
    """
    if not target.is_dir():
        return [target]
    files: list[Path] = []
    skill_file = target / "SKILL.md"
    if skill_file.is_file():
        files.append(skill_file)
    references = target / "references"
    if references.is_dir():
        files.extend(sorted(references.rglob("*.md")))
    return files


def build_parser() -> argparse.ArgumentParser:
    """Build argument parser."""
    parser = argparse.ArgumentParser(
        prog="check_docs_safety.py",
        description=(
            "Flag unquoted $TOOL_INPUT or $TOOL_OUTPUT in markdown command "
            "examples. With no argument, scans this skill's default docs."
        ),
        epilog=(
            "Exit codes: 0 no unsafe patterns found, 1 unsafe patterns found, "
            "2 bad input (unreadable path or a directory with no markdown)."
        ),
    )
    parser.add_argument(
        "paths",
        nargs="*",
        metavar="PATH",
        help=("Skill directory (scans SKILL.md and references/*.md) or markdown file. Repeatable."),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo_root = Path(__file__).resolve().parents[1]

    if args.paths:
        targets: list[Path] = []
        for raw in args.paths:
            expanded = expand_target(Path(raw).resolve())
            if not expanded:
                print(
                    f"No markdown files to scan under {raw} "
                    "(expected SKILL.md or references/*.md).",
                    file=sys.stderr,
                )
                return 2
            targets.extend(expanded)
    else:
        targets = default_targets(repo_root)

    all_issues: list[str] = []
    try:
        for target in targets:
            all_issues.extend(scan_file(target))
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if all_issues:
        print("Unsafe command interpolation found:")
        for issue in all_issues:
            print(f"  - {issue}")
        return 1

    print(f"No unsafe command interpolation patterns found ({len(targets)} files scanned).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
