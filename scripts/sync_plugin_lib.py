#!/usr/bin/env python3
"""Sync scripts/ packages to .claude/lib/ with relative imports for plugin distribution.

The .claude/lib/ directory contains copies of shared Python packages that use
relative imports (instead of the absolute imports used under scripts/). This
script automates keeping those copies in sync.

Usage:
    python3 scripts/sync_plugin_lib.py          # sync files
    python3 scripts/sync_plugin_lib.py --check   # CI dry-run (exits 1 if out of sync)
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent

SYNC_PAIRS: list[tuple[str, str]] = [
    ("scripts/hook_utilities", ".claude/lib/hook_utilities"),
    ("scripts/github_core", ".claude/lib/github_core"),
]

IMPORT_CONVERSIONS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"from scripts\.github_core\.(\w+) import"), r"from .\1 import"),
    (re.compile(r"from scripts\.hook_utilities\.(\w+) import"), r"from .\1 import"),
    (re.compile(r"from scripts\.github_core import"), "from . import"),
    (re.compile(r"from scripts\.hook_utilities import"), "from . import"),
]

# Files that exist only in the lib copy and must not be deleted during sync.
LIB_ONLY_FILES: set[str] = set()

CANONICAL_NOTE = "Canonical: {src_rel}. Sync via scripts/sync_plugin_lib.py."


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------


def _build_canonical_note(src_rel: str) -> str:
    """Return the canonical-copy docstring line for a given source path."""
    return CANONICAL_NOTE.format(src_rel=src_rel)


def _convert_imports(content: str) -> str:
    """Replace absolute imports with relative imports."""
    for pattern, replacement in IMPORT_CONVERSIONS:
        content = pattern.sub(replacement, content)
    return content


def _replace_first_docstring_line(content: str, note: str) -> str:
    """Replace the first line inside a module-level docstring with *note*.

    Handles both triple-double-quote and triple-single-quote styles.
    If the module has no leading docstring, prepend one.
    """
    # Single-line docstring: """some text.""" (opening and closing on same line)
    match = re.match(r'^("""|\'\'\')[^\n]*?("""|\'\'\')', content)
    if match:
        quote = match.group(1)
        close_end = match.end()
        after = content[close_end:]
        return f'{quote}{note}{quote}{after}'

    # Multi-line docstring: """text\n...\n"""
    match = re.match(r'^("""|\'\'\')\s*\n?', content)
    if match:
        quote = match.group(1)
        # Find the end of the first line after the opening quotes
        rest_start = match.end()
        # Skip past the original first content line
        newline_pos = content.find("\n", rest_start)
        if newline_pos == -1:
            after = ""
        else:
            after = content[newline_pos:]
        return f'{quote}{note}{after}'

    # No docstring found: prepend one
    print(
        "[WARNING] sync_plugin_lib: No module docstring found in source, prepending canonical note",
        file=sys.stderr,
    )
    return f'"""{note}"""\n\n{content}'


def _transform_file(src_path: Path, src_dir_rel: str) -> str:
    """Read a source file and return its plugin-ready content."""
    content = src_path.read_text(encoding="utf-8")
    content = _convert_imports(content)
    src_rel = f"{src_dir_rel}/{src_path.name}"
    content = _replace_first_docstring_line(content, _build_canonical_note(src_rel))
    return content


def _validate_sync_dirs(
    src_rel: str,
    dst_rel: str,
) -> tuple[Path, Path, list[str]]:
    """Validate and resolve source/destination directories.

    Returns (src_dir, dst_dir, errors). Non-empty errors means abort.
    """
    src_dir = (REPO_ROOT / src_rel).resolve()
    dst_dir = (REPO_ROOT / dst_rel).resolve()
    repo_root_resolved = REPO_ROOT.resolve()
    errors: list[str] = []

    try:
        src_dir.relative_to(repo_root_resolved)
    except ValueError:
        errors.append(f"[ERROR] Source path escapes repo root: {src_rel}")
    try:
        dst_dir.relative_to(repo_root_resolved)
    except ValueError:
        errors.append(f"[ERROR] Destination path escapes repo root: {dst_rel}")

    return src_dir, dst_dir, errors


def _sync_files(
    src_dir: Path,
    dst_dir: Path,
    src_rel: str,
    dst_rel: str,
    src_files: set[str],
    *,
    check_only: bool,
) -> tuple[list[str], bool]:
    """Sync source .py files to destination. Returns (changes, had_errors)."""
    changes: list[str] = []
    had_errors = False

    for name in sorted(src_files):
        src_path = src_dir / name
        dst_path = dst_dir / name
        try:
            expected = _transform_file(src_path, src_rel)
        except (OSError, UnicodeDecodeError) as exc:
            changes.append(f"  [ERROR] Cannot read {src_rel}/{name}: {exc}")
            had_errors = True
            continue

        if dst_path.exists():
            try:
                current = dst_path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                changes.append(f"  [ERROR] Cannot read {dst_rel}/{name}: {exc}")
                had_errors = True
                continue
            if current == expected:
                continue
            action = "updated"
        else:
            action = "created"

        changes.append(f"  {action}: {dst_rel}/{name}")
        if not check_only:
            try:
                dst_path.write_text(expected, encoding="utf-8")
            except OSError as exc:
                changes.append(f"  [ERROR] Cannot write {dst_rel}/{name}: {exc}")
                had_errors = True

    return changes, had_errors


def _remove_stale_files(
    dst_dir: Path,
    dst_rel: str,
    src_files: set[str],
    *,
    check_only: bool,
) -> tuple[list[str], bool]:
    """Remove destination .py files not in source. Returns (changes, had_errors)."""
    changes: list[str] = []
    had_errors = False

    try:
        dst_entries = sorted(dst_dir.iterdir())
    except OSError as exc:
        changes.append(f"[ERROR] Cannot list destination directory {dst_rel}: {exc}")
        return changes, True

    for dst_file in dst_entries:
        if dst_file.suffix != ".py":
            continue
        if dst_file.name in LIB_ONLY_FILES:
            continue
        if dst_file.name not in src_files:
            changes.append(f"  removed: {dst_rel}/{dst_file.name}")
            if not check_only:
                try:
                    dst_file.unlink()
                except OSError as exc:
                    changes.append(
                        f"  [ERROR] Cannot remove {dst_rel}/{dst_file.name}: {exc}"
                    )
                    had_errors = True

    return changes, had_errors


def sync_pair(
    src_rel: str,
    dst_rel: str,
    *,
    check_only: bool,
) -> tuple[list[str], bool]:
    """Sync one source directory to its lib counterpart.

    Returns a tuple of (change descriptions, had_errors).
    """
    src_dir, dst_dir, errors = _validate_sync_dirs(src_rel, dst_rel)
    if errors:
        return errors, True

    if not src_dir.is_dir():
        return [f"[WARNING] Source directory missing: {src_rel}"], False

    try:
        dst_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        msg = f"[ERROR] Cannot create destination directory {dst_rel}: {exc}"
        return [msg], True

    try:
        src_files = {f.name for f in src_dir.iterdir() if f.suffix == ".py"}
    except OSError as exc:
        msg = f"[ERROR] Cannot list source directory {src_rel}: {exc}"
        return [msg], True

    changes: list[str] = []
    had_errors = False

    sync_changes, sync_errors = _sync_files(
        src_dir, dst_dir, src_rel, dst_rel, src_files, check_only=check_only,
    )
    changes.extend(sync_changes)
    had_errors = had_errors or sync_errors

    stale_changes, stale_errors = _remove_stale_files(
        dst_dir, dst_rel, src_files, check_only=check_only,
    )
    changes.extend(stale_changes)
    had_errors = had_errors or stale_errors

    return changes, had_errors


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns 0 on success, 1 if --check finds drift."""
    parser = argparse.ArgumentParser(
        description="Sync scripts/ packages to .claude/lib/ with relative imports.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Dry-run mode: exit 1 if any files would change.",
    )
    args = parser.parse_args(argv)

    all_changes: list[str] = []
    any_errors = False
    for src_rel, dst_rel in SYNC_PAIRS:
        pair_changes, had_errors = sync_pair(src_rel, dst_rel, check_only=args.check)
        if had_errors:
            any_errors = True
        if pair_changes:
            all_changes.append(f"{src_rel} -> {dst_rel}:")
            all_changes.extend(pair_changes)

    if not all_changes:
        print("All plugin lib copies are in sync.")
        return 1 if any_errors else 0

    if args.check:
        print("Plugin lib copies are out of sync:")
        for line in all_changes:
            print(line)
        print("\nRun 'python3 scripts/sync_plugin_lib.py' to fix.")
        return 1

    print("Synced plugin lib copies:")
    for line in all_changes:
        print(line)
    return 1 if any_errors else 0


if __name__ == "__main__":
    sys.exit(main())
