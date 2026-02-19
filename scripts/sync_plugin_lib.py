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

# Non-Python files in the lib directory that should be left untouched.
SKIP_EXTENSIONS: set[str] = {".md", ".pyc"}

CANONICAL_NOTE = "Canonical copy lives at {src_rel}; keep in sync via scripts/sync_plugin_lib.py."


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


def sync_pair(
    src_rel: str,
    dst_rel: str,
    *,
    check_only: bool,
) -> list[str]:
    """Sync one source directory to its lib counterpart.

    Returns a list of human-readable change descriptions.
    """
    src_dir = (REPO_ROOT / src_rel).resolve()
    dst_dir = (REPO_ROOT / dst_rel).resolve()
    repo_root_resolved = REPO_ROOT.resolve()
    changes: list[str] = []

    if not str(src_dir).startswith(str(repo_root_resolved)):
        changes.append(f"[ERROR] Source path escapes repo root: {src_rel}")
        return changes
    if not str(dst_dir).startswith(str(repo_root_resolved)):
        changes.append(f"[ERROR] Destination path escapes repo root: {dst_rel}")
        return changes

    if not src_dir.is_dir():
        changes.append(f"[WARNING] Source directory missing: {src_rel}")
        return changes

    try:
        dst_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        changes.append(f"[ERROR] Cannot create destination directory {dst_rel}: {exc}")
        return changes

    # Collect source .py files
    src_files = {f.name for f in src_dir.iterdir() if f.suffix == ".py"}

    # Sync each source file to destination
    for name in sorted(src_files):
        src_path = src_dir / name
        dst_path = dst_dir / name
        try:
            expected = _transform_file(src_path, src_rel)
        except (OSError, UnicodeDecodeError) as exc:
            changes.append(f"  [ERROR] Cannot read {src_rel}/{name}: {exc}")
            continue

        if dst_path.exists():
            try:
                current = dst_path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                changes.append(f"  [ERROR] Cannot read {dst_rel}/{name}: {exc}")
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

    # Remove stale .py files in destination that no longer exist in source,
    # but preserve lib-only files.
    for dst_file in sorted(dst_dir.iterdir()):
        if dst_file.suffix != ".py":
            continue
        if dst_file.name in LIB_ONLY_FILES:
            continue
        if dst_file.name not in src_files:
            changes.append(f"  removed: {dst_rel}/{dst_file.name}")
            if not check_only:
                dst_file.unlink()

    return changes


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
    for src_rel, dst_rel in SYNC_PAIRS:
        pair_changes = sync_pair(src_rel, dst_rel, check_only=args.check)
        if pair_changes:
            all_changes.append(f"{src_rel} -> {dst_rel}:")
            all_changes.extend(pair_changes)

    if not all_changes:
        print("All plugin lib copies are in sync.")
        return 0

    if args.check:
        print("Plugin lib copies are out of sync:")
        for line in all_changes:
            print(line)
        print("\nRun 'python3 scripts/sync_plugin_lib.py' to fix.")
        return 1

    print("Synced plugin lib copies:")
    for line in all_changes:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
