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

# Git stores a symlink's *target path text* as its blob content, not the bytes
# of the file it points to. A staged symlink SKILL.md therefore measures the
# short link text and would slip a 30 KiB target past the ceiling, so the gate
# rejects it (see StagedBlobError / read_staged_blob_bytes).
_GIT_SYMLINK_MODE: str = "120000"


class StagedBlobError(RuntimeError):
    """A staged SKILL.md blob could not be certified for size measurement.

    Raised in staged mode when the index blob is missing, is a symlink (git
    stores the link target text as the blob, not the linked file's bytes, so
    measuring it under-counts), or ``git show`` fails. The gate fails closed on
    this rather than fall back to the working tree, which a pre-commit hook must
    never trust for what is about to be committed.
    """


def _relative_display(file_path: Path) -> str:
    """Best-effort cwd-relative string for display; absolute path on failure."""
    try:
        return str(file_path.relative_to(Path.cwd()))
    except ValueError:
        return str(file_path)


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


@dataclass
class _Tally:
    """Running counts across the SKILL.md files a single run inspects.

    ``uncertifiable`` counts staged blobs the gate could not measure (missing
    index entry, symlink, or failed ``git show``); it drives an unconditional
    fail-closed exit so an unmeasurable blob can never be reported as passing.
    """

    passed: int = 0
    warnings: int = 0
    failed: int = 0
    uncertifiable: int = 0


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
    relative = _relative_display(file_path)

    if content_bytes is not None:
        raw = content_bytes
    else:
        try:
            raw = file_path.read_bytes()
        except OSError:
            return SizeCheckResult(
                file_path=relative,
                line_count=0,
                passed=False,
                errors=["File is unreadable"],
            )

    content = raw.decode("utf-8", errors="replace")
    line_count = len(content.splitlines())
    byte_count = len(raw)
    exception = has_size_exception(content)

    result = SizeCheckResult(
        file_path=relative,
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
        if line and re.search(_SKILL_MD_PATTERN, line):
            files.append(Path(line))
    return files


def _staged_index_mode(path: Path) -> str | None:
    """Return the git index mode for ``path`` (e.g. '100644', '120000'), or None.

    ``git ls-files -s`` prints ``<mode> <sha> <stage>\\t<path>``; the first token
    is the mode. None means the path has no index entry (or git is unavailable).
    """
    try:
        result = subprocess.run(
            ["git", "ls-files", "-s", "--", path.as_posix()],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None
    if result.returncode != 0:
        return None
    out = result.stdout.strip()
    if not out:
        return None
    return out.split(maxsplit=1)[0]


def read_staged_blob_bytes(path: Path) -> bytes:
    """Return the staged (indexed) bytes for ``path``; fail closed on any doubt.

    A pre-commit gate must judge what will be committed, not the working tree.
    ``git show :<path>`` reads the blob from the index, so an oversized staged
    body cannot be masked by a shrunk (unstaged) working copy, and a staged
    ``size-exception`` is honored while an unstaged one is ignored. The path is
    emitted as POSIX because git indexes forward-slash paths on every platform.

    Raises ``StagedBlobError`` when the blob cannot be certified: no index entry,
    a symlink (git stores the link target text as the blob, which under-measures
    a link to a large file), or a failed/timed-out ``git show``. The caller must
    never fall back to the working tree in staged mode.
    """
    mode = _staged_index_mode(path)
    if mode is None:
        msg = f"{path.as_posix()}: no staged index entry; cannot measure staged bytes"
        raise StagedBlobError(msg)
    if mode == _GIT_SYMLINK_MODE:
        msg = (
            f"{path.as_posix()}: staged entry is a symlink (mode 120000); git "
            "stores the link target as the blob, so its size cannot certify the "
            "linked file. Commit a real SKILL.md, not a symlink."
        )
        raise StagedBlobError(msg)
    try:
        result = subprocess.run(
            ["git", "show", f":{path.as_posix()}"],
            capture_output=True,
            timeout=10,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        msg = f"{path.as_posix()}: git show failed ({exc})"
        raise StagedBlobError(msg) from exc
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace").strip()
        msg = f"{path.as_posix()}: git show exited {result.returncode}: {stderr}"
        raise StagedBlobError(msg)
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


def _report_summary(files_count: int, tally: _Tally, args: argparse.Namespace) -> int:
    """Print the run summary and return the ADR-035 exit code.

    An uncertifiable staged blob is a fail-closed integrity failure and returns
    2 unconditionally (even outside ``--ci``): the gate refuses to pass a blob it
    could not measure. This takes priority over the ordinary oversize failure
    (exit 1 in CI), because a blob whose size is unknown is a stronger signal
    than one that is known to be too large.
    """
    print()
    print("=" * 40)
    print("Skill Size Summary")
    print("=" * 40)
    print(f"  Total:    {files_count}")
    print(f"  Passed:   {tally.passed}")
    print(f"  Warnings: {tally.warnings}")
    print(f"  Failed:   {tally.failed}")
    if tally.uncertifiable:
        print(f"  Uncertifiable (staged): {tally.uncertifiable}")
    print(f"  Limit:    {args.limit} lines / {args.byte_limit} bytes")
    print()

    if tally.uncertifiable > 0:
        print(
            f"{tally.uncertifiable} staged SKILL.md file(s) could not be certified "
            "for size. Failing closed: a pre-commit gate must not pass a blob it "
            "cannot measure. Fix the staged entry (commit a real file, not a "
            "symlink; ensure it is actually staged) and retry."
        )
        return 2

    if tally.failed > 0:
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

    tally = _Tally()

    for file_path in files:
        content_bytes: bytes | None = None
        if args.staged_only:
            try:
                content_bytes = read_staged_blob_bytes(file_path)
            except StagedBlobError as exc:
                tally.uncertifiable += 1
                print(
                    f"  [FAIL] {_relative_display(file_path)} "
                    "(staged blob uncertifiable)"
                )
                print(f"    {exc}")
                continue

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
            tally.failed += 1
            print(f"  [FAIL] {result.file_path} ({size})")
            for error in result.errors:
                print(f"    {error}")
            continue

        tally.passed += 1
        if result.warning:
            tally.warnings += 1
            if result.has_exception:
                print(
                    f"  [EXCEPTION] {result.file_path} ({size})"
                    " - size-exception declared"
                )
            else:
                print(f"  [WARN] {result.file_path} ({size})")

    return _report_summary(len(files), tally, args)


if __name__ == "__main__":
    raise SystemExit(main())
