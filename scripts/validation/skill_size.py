#!/usr/bin/env python3
"""Validate SKILL.md files do not exceed size limits.

Enforces prompt size limits for skill files to prevent token bloat,
maintainability issues, and processing overhead. Skills exceeding
the limit should use progressive disclosure (references/, modules/).

Size limits:
    - SKILL.md: 500 lines (warning at 300)
    - SKILL.md: 20,480 bytes target ceiling (warning at 12,288); enforced as a
      ratchet seeded above today's largest body, lowered toward the target as
      oversized skills decompose into references/ (see SKILL_BYTE_LIMIT)
    - Exception: documented in frontmatter with 'size-exception: true'

The byte ceiling exists because the line ceiling misses table-heavy or
long-line bodies: a skill can sit under 500 lines yet carry 24 KB, so invoking
it to check one procedure pays for the whole document. Progressive disclosure
(a lean SKILL.md that states triggers, the routing decision, and pointers, with
procedures and tables in references/*.md) keeps the always-loaded body small.

Exit codes follow ADR-035:
    0 - Success: All skill files within size limits
    1 - Error: One or more files exceed limit (CI mode only)
    2 - Config error (path not found)

Related: Issue #676 (Skill Prompt Size Limits), Issue #3421 (byte ceiling)
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

# Load local frontmatter module by file path to avoid collision with
# the PyPI ``python-frontmatter`` package which also installs as ``frontmatter``.
_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parents[1]
_FRONTMATTER_PATH = (
    _PROJECT_ROOT / ".claude" / "skills" / "SkillForge" / "scripts" / "frontmatter.py"
)
try:
    _spec = importlib.util.spec_from_file_location("skill_frontmatter_utils", _FRONTMATTER_PATH)
    _mod = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
    _spec.loader.exec_module(_mod)  # type: ignore[union-attr]
    has_size_exception = _mod.has_size_exception
except (FileNotFoundError, TypeError, AttributeError) as _exc:
    print(
        f"Error: Failed to load frontmatter helper from {_FRONTMATTER_PATH}: {_exc}",
        file=__import__("sys").stderr,
    )
    raise SystemExit(2) from _exc

# Size thresholds (lines)
SKILL_SIZE_LIMIT: int = 500
SKILL_SIZE_WARNING: int = 300

# Size thresholds (bytes). The hard limit is a ratchet: it is seeded just above
# the largest SKILL.md body in the corpus so it blocks further growth and any
# new oversized skill without redding an already-green main. Lower it toward
# SKILL_BYTE_TARGET (20 KiB, Issue #3421 AC-3) as the over-limit skills
# decompose their bodies into references/. The warning marks the 12 KiB soft
# ceiling that signals a skill should adopt progressive disclosure.
SKILL_BYTE_TARGET: int = 20_480  # 20 KiB, the documented goal (Issue #3421)
SKILL_BYTE_LIMIT: int = 24_576  # 24 KiB, current ratchet (max body is 24,210 B)
SKILL_BYTE_WARNING: int = 12_288  # 12 KiB, progressive-disclosure trigger

# Pattern matching staged/changed SKILL.md files
_SKILL_MD_PATTERN: str = r"^\.claude/skills/.*/SKILL\.md$"


@dataclass
class SizeCheckResult:
    """Result of checking a single SKILL.md file size."""

    file_path: str
    line_count: int
    byte_count: int = 0
    has_exception: bool = False
    passed: bool = True
    warning: bool = False
    errors: list[str] = field(default_factory=list)


def check_skill_size(
    file_path: Path,
    limit: int = SKILL_SIZE_LIMIT,
    warn: int = SKILL_SIZE_WARNING,
    byte_limit: int = SKILL_BYTE_LIMIT,
    byte_warn: int = SKILL_BYTE_WARNING,
    *,
    content_bytes: bytes | None = None,
) -> SizeCheckResult:
    """Check a single SKILL.md file against line and byte size limits.

    Lines and bytes are independent dimensions: a body can pass one and fail the
    other (a table-heavy skill stays under 500 lines yet exceeds the byte
    ceiling). Both honor the same ``size-exception: true`` frontmatter escape,
    which downgrades a hard failure to a warning.

    Pass ``content_bytes`` to measure a specific byte payload (the staged index
    blob) instead of reading the working tree. When it is None the working-tree
    file is read. Measuring bytes and parsing the exception from the SAME source
    keeps a staged gate honest: an oversized staged body cannot be masked by a
    shrunk unstaged working copy, and only a staged exception is honored.
    """
    try:
        relative = file_path.relative_to(Path.cwd())
    except ValueError:
        relative = file_path

    if content_bytes is not None:
        raw = content_bytes
    else:
        try:
            raw = file_path.read_bytes()
        except OSError:
            return SizeCheckResult(
                file_path=str(relative),
                line_count=0,
                passed=False,
                errors=["File is unreadable"],
            )

    content = raw.decode("utf-8", errors="replace")
    line_count = len(content.splitlines())
    byte_count = len(raw)
    exception = has_size_exception(content)

    result = SizeCheckResult(
        file_path=str(relative),
        line_count=line_count,
        byte_count=byte_count,
        has_exception=exception,
    )

    if line_count > limit:
        if exception:
            result.warning = True
        else:
            result.passed = False
            result.errors.append(
                f"SKILL.md exceeds {limit} lines ({line_count} lines). "
                f"Refactor using progressive disclosure: move details to references/, "
                f"modules/, or scripts/. Add 'size-exception: true' to frontmatter "
                f"if overage is justified."
            )
    elif line_count > warn:
        result.warning = True

    if byte_count > byte_limit:
        if exception:
            result.warning = True
        else:
            result.passed = False
            result.errors.append(
                f"SKILL.md exceeds {byte_limit} bytes ({byte_count} bytes). "
                f"Refactor using progressive disclosure: move procedures, tables, and "
                f"examples to references/ so the always-loaded body stays lean. Add "
                f"'size-exception: true' to frontmatter if overage is justified."
            )
    elif byte_count > byte_warn:
        result.warning = True

    return result


def get_staged_skill_files() -> list[Path]:
    """Get staged SKILL.md files from git."""
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []

    if result.returncode != 0:
        return []

    files: list[Path] = []
    for line in result.stdout.strip().split("\n"):
        if re.search(_SKILL_MD_PATTERN, line):
            path = Path(line)
            if path.exists():
                files.append(path)
    return files


def read_staged_blob_bytes(path: Path) -> bytes | None:
    """Return the staged (indexed) bytes for ``path``, or None if unavailable.

    A pre-commit gate must judge what will be committed, not the working tree.
    ``git show :<path>`` reads the blob from the index, so an oversized staged
    body cannot be masked by a shrunk (unstaged) working copy, and a staged
    ``size-exception`` is honored while an unstaged one is ignored. The path is
    emitted as POSIX because git indexes forward-slash paths on every platform.
    """
    try:
        result = subprocess.run(
            ["git", "show", f":{path.as_posix()}"],
            capture_output=True,
            timeout=10,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None

    if result.returncode != 0:
        return None

    return result.stdout


def get_skill_files(
    path: str,
    staged_only: bool = False,
    changed_files: list[str] | None = None,
) -> list[Path]:
    """Get list of SKILL.md files to validate."""
    if changed_files:
        skill_files = [f for f in changed_files if re.search(_SKILL_MD_PATTERN, f)]
        if not skill_files:
            return []
        return [Path(f) for f in skill_files if Path(f).exists()]

    if staged_only:
        return get_staged_skill_files()

    target = Path(path)
    if not target.exists():
        return []

    if target.is_file() and target.name == "SKILL.md":
        return [target]

    return sorted(target.rglob("SKILL.md"))


def build_parser() -> argparse.ArgumentParser:
    """Build argument parser."""
    parser = argparse.ArgumentParser(
        description="Validate SKILL.md files against size limits.",
    )
    parser.add_argument(
        "--path",
        default=os.environ.get("SKILL_PATH", ".claude/skills"),
        help="Path to SKILL.md file or directory (default: .claude/skills)",
    )
    parser.add_argument(
        "--ci",
        action="store_true",
        default=os.environ.get("CI", "").lower() in ("true", "1"),
        help="CI mode: exit non-zero on validation failure",
    )
    parser.add_argument(
        "--staged-only",
        action="store_true",
        default=os.environ.get("STAGED_ONLY", "").lower() in ("true", "1"),
        help="Only check staged files",
    )
    parser.add_argument(
        "--changed-files",
        nargs="*",
        default=None,
        help="Explicit list of file paths to check",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=SKILL_SIZE_LIMIT,
        help=f"Maximum lines allowed (default: {SKILL_SIZE_LIMIT})",
    )
    parser.add_argument(
        "--warn",
        type=int,
        default=SKILL_SIZE_WARNING,
        help=f"Warning threshold in lines (default: {SKILL_SIZE_WARNING})",
    )
    parser.add_argument(
        "--byte-limit",
        type=int,
        default=SKILL_BYTE_LIMIT,
        help=f"Maximum bytes allowed (default: {SKILL_BYTE_LIMIT})",
    )
    parser.add_argument(
        "--byte-warn",
        type=int,
        default=SKILL_BYTE_WARNING,
        help=f"Warning threshold in bytes (default: {SKILL_BYTE_WARNING})",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns ADR-035 exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    # Use local variables instead of modifying globals
    limit = args.limit
    warn = args.warn
    byte_limit = args.byte_limit
    byte_warn = args.byte_warn

    print("Validating skill prompt sizes...")

    files = get_skill_files(
        path=args.path,
        staged_only=args.staged_only,
        changed_files=args.changed_files,
    )

    if not files:
        print("No SKILL.md files found to validate.")
        return 0

    print(f"Found {len(files)} SKILL.md file(s) to check.\n")

    pass_count = 0
    warn_count = 0
    fail_count = 0

    for file_path in files:
        content_bytes = read_staged_blob_bytes(file_path) if args.staged_only else None
        result = check_skill_size(
            file_path,
            limit=limit,
            warn=warn,
            byte_limit=byte_limit,
            byte_warn=byte_warn,
            content_bytes=content_bytes,
        )
        size = f"{result.line_count} lines, {result.byte_count} bytes"

        if not result.passed:
            fail_count += 1
            print(f"  [FAIL] {result.file_path} ({size})")
            for error in result.errors:
                print(f"    {error}")
            continue

        pass_count += 1
        if result.warning:
            warn_count += 1
            if result.has_exception:
                print(
                    f"  [EXCEPTION] {result.file_path} ({size})"
                    " - size-exception declared"
                )
            else:
                print(f"  [WARN] {result.file_path} ({size})")

    print()
    print("=" * 40)
    print("Skill Size Summary")
    print("=" * 40)
    print(f"  Total:    {len(files)}")
    print(f"  Passed:   {pass_count}")
    print(f"  Warnings: {warn_count}")
    print(f"  Failed:   {fail_count}")
    print(f"  Limit:    {limit} lines / {byte_limit} bytes")
    print()

    if fail_count > 0:
        print("Fix oversized skills by refactoring to progressive disclosure:")
        print("  - Move reference docs to references/")
        print("  - Extract scripts to scripts/")
        print("  - Use modules/ for reusable logic")
        print("  - Add 'size-exception: true' to frontmatter if justified")

        if args.ci:
            return 1

        print("\nNot in CI mode. Continuing...")

    else:
        print("All skill files within size limits.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
