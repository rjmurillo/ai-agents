#!/usr/bin/env python3
"""Rename a spec ID and update all references automatically.

Safely renames a specification ID across the entire traceability graph,
updating the spec file itself (filename and frontmatter) and all YAML
frontmatter references in other specs. Uses backup/rollback for atomicity.

EXIT CODES:
  0 - Success (rename completed or validated in dry-run)
  1 - Error (ID not found, invalid format, file operation failed)
  2 - User cancelled operation

See: ADR-035 Exit Code Standardization
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.traceability.spec_utils import (  # noqa: E402
    find_spec_file,
    get_spec_subdir,
    get_spec_type,
    is_valid_spec_id,
    parse_yaml_frontmatter,
    validate_specs_path,
)
from scripts.traceability.traceability_cache import clear_cache  # noqa: E402


def find_referencing_files(spec_id: str, base_path: Path) -> list[Path]:
    """Find all spec files that reference the given spec ID in their related list."""
    referencing: list[Path] = []
    for subdir in ("requirements", "design", "tasks"):
        subdir_path = base_path / subdir
        if not subdir_path.exists():
            continue
        for md_file in sorted(subdir_path.glob("*.md")):
            spec = parse_yaml_frontmatter(md_file, use_cache=False)
            if spec and spec_id in spec.get("related", []):
                referencing.append(md_file)
    return referencing


def update_file_content(
    file_path: Path, old_value: str, new_value: str, dry_run: bool
) -> bool:
    """Replace a spec ID reference in a file. Returns True on success."""
    content = file_path.read_text(encoding="utf-8")
    pattern = rf"(?<=\s){re.escape(old_value)}(?=\s|$)"
    new_content = re.sub(pattern, new_value, content)

    if dry_run:
        print(f"  Would update: {file_path}")
        return True

    try:
        file_path.write_text(new_content, encoding="utf-8")
        return True
    except OSError as e:
        print(f"Failed to update {file_path}: {e}", file=sys.stderr)
        return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Rename a spec ID and update all references."
    )
    parser.add_argument("--old-id", required=True, help="Current spec ID (e.g., REQ-001)")
    parser.add_argument("--new-id", required=True, help="New spec ID (e.g., REQ-100)")
    parser.add_argument(
        "--specs-path", default=".agents/specs", help="Path to specs directory"
    )
    parser.add_argument("--dry-run", action="store_true", help="Show plan without changes")
    parser.add_argument("--force", action="store_true", help="Skip confirmation prompts")
    args = parser.parse_args(argv)

    if not is_valid_spec_id(args.old_id):
        msg = f"Invalid old ID format: {args.old_id}. Expected: TYPE-ID (e.g., REQ-001)"
        print(msg, file=sys.stderr)
        return 1
    if not is_valid_spec_id(args.new_id):
        msg = f"Invalid new ID format: {args.new_id}. Expected: TYPE-ID (e.g., REQ-001)"
        print(msg, file=sys.stderr)
        return 1

    old_type = get_spec_type(args.old_id)
    new_type = get_spec_type(args.new_id)
    if old_type != new_type:
        print(f"Cannot change spec type during rename ({old_type} -> {new_type})", file=sys.stderr)
        return 1

    try:
        resolved_path = validate_specs_path(args.specs_path)
    except SystemExit:
        return 1

    old_file = find_spec_file(args.old_id, resolved_path)
    if not old_file:
        print(f"Spec not found: {args.old_id}", file=sys.stderr)
        return 1

    new_file = find_spec_file(args.new_id, resolved_path)
    if new_file:
        print(f"Target spec already exists: {args.new_id}", file=sys.stderr)
        return 1

    referencing_files = find_referencing_files(args.old_id, resolved_path)

    print("Rename Plan:")
    print(f"  Old ID: {args.old_id}")
    print(f"  New ID: {args.new_id}")
    print()
    print("Files to update:")
    print(f"  1. {old_file} (rename file and update ID)")
    for i, f in enumerate(referencing_files, start=2):
        print(f"  {i}. {f} (update reference)")
    print()

    if args.dry_run:
        print("DRY RUN: No changes will be made")
        return 0

    if not args.force:
        confirmation = input("Proceed with rename? (y/N) ")
        if confirmation.lower() != "y":
            print("Operation cancelled")
            return 2

    backups: list[tuple[Path, Path]] = []
    try:
        print("Creating backups...")
        backup_path = Path(f"{old_file}.bak")
        shutil.copy2(old_file, backup_path)
        backups.append((old_file, backup_path))

        for ref_file in referencing_files:
            bak = Path(f"{ref_file}.bak")
            shutil.copy2(ref_file, bak)
            backups.append((ref_file, bak))

        print("Updating references...")
        for ref_file in referencing_files:
            if not update_file_content(ref_file, args.old_id, args.new_id, dry_run=False):
                raise RuntimeError(f"Failed to update {ref_file}")

        print("Updating spec file...")
        if not update_file_content(old_file, args.old_id, args.new_id, dry_run=False):
            raise RuntimeError(f"Failed to update spec ID in {old_file}")

        print("Renaming file...")
        subdir = get_spec_subdir(args.old_id)
        new_file_path = resolved_path / subdir / f"{args.new_id}.md"
        old_file.rename(new_file_path)

        print("Cleaning up...")
        for _, bak in backups:
            bak.unlink(missing_ok=True)

        clear_cache()
        print("Rename completed successfully!")
        return 0

    except Exception as e:
        print(f"Rename failed: {e}", file=sys.stderr)
        print("Rolling back changes...")
        for original, bak in backups:
            if bak.exists():
                shutil.copy2(bak, original)
                bak.unlink()
        return 1


if __name__ == "__main__":
    sys.exit(main())
