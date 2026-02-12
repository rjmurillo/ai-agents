#!/usr/bin/env python3
"""Bulk update spec references in the traceability graph.

Updates multiple spec references in one atomic operation. Supports:
- Adding new references to a spec's related list
- Removing references from a spec's related list
- Replacing one reference with another

EXIT CODES:
  0 - Success (update completed or validated in dry-run)
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
    is_valid_spec_id,
    parse_frontmatter_with_content,
    validate_specs_path,
)
from scripts.traceability.traceability_cache import clear_cache  # noqa: E402


def update_yaml_references(
    file_path: Path,
    new_references: list[str],
    dry_run: bool,
) -> bool:
    """Rewrite the related block in a spec file's YAML frontmatter."""
    content = file_path.read_text(encoding="utf-8")
    sorted_refs = sorted(new_references)
    related_block = "related:\n" + "".join(f"  - {ref}\n" for ref in sorted_refs)

    match = re.match(
        r"(?s)(^---\r?\n.+?)related:\s*\r?\n(?:\s+-\s+.+\r?\n?)+(.+---\r?\n.*)",
        content,
    )
    if match:
        new_content = f"{match.group(1)}{related_block}{match.group(2)}"
    else:
        match2 = re.match(r"(?s)(^---\r?\n.+?)(\r?\n---\r?\n.*)", content)
        if match2:
            new_content = f"{match2.group(1)}\n{related_block}{match2.group(2)}"
        else:
            print(f"Could not parse YAML frontmatter in {file_path}", file=sys.stderr)
            return False

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
        description="Update spec references in the traceability graph."
    )
    parser.add_argument("--source-id", required=True, help="Spec ID to update (e.g., DESIGN-001)")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--add", nargs="+", metavar="ID", help="Spec IDs to add to related list")
    group.add_argument(
        "--remove", nargs="+", metavar="ID", help="Spec IDs to remove from related list"
    )
    group.add_argument(
        "--replace",
        nargs=2,
        metavar=("OLD", "NEW"),
        help="Replace OLD reference with NEW",
    )
    parser.add_argument("--specs-path", default=".agents/specs", help="Path to specs directory")
    parser.add_argument("--dry-run", action="store_true", help="Show plan without changes")
    parser.add_argument("--force", action="store_true", help="Skip confirmation prompts")
    args = parser.parse_args(argv)

    if not is_valid_spec_id(args.source_id):
        print(f"Invalid source ID format: {args.source_id}", file=sys.stderr)
        return 1

    ids_to_validate: list[str] = []
    if args.add:
        ids_to_validate = args.add
    elif args.remove:
        ids_to_validate = args.remove
    elif args.replace:
        ids_to_validate = args.replace

    for ref_id in ids_to_validate:
        if not is_valid_spec_id(ref_id):
            print(f"Invalid reference ID format: {ref_id}", file=sys.stderr)
            return 1

    if args.replace:
        old_ref, new_ref = args.replace
    else:
        old_ref = new_ref = ""

    try:
        resolved_path = validate_specs_path(args.specs_path)
    except SystemExit:
        return 1

    source_file = find_spec_file(args.source_id, resolved_path)
    if not source_file:
        print(f"Source spec not found: {args.source_id}", file=sys.stderr)
        return 1

    spec = parse_frontmatter_with_content(source_file)
    if not spec:
        print(f"Could not parse spec file: {source_file}", file=sys.stderr)
        return 1

    current_refs = list(spec["related"])
    new_refs = list(current_refs)

    if args.add:
        operation = "Add"
        for ref_id in args.add:
            if ref_id not in new_refs:
                new_refs.append(ref_id)
    elif args.remove:
        operation = "Remove"
        for ref_id in args.remove:
            if ref_id in new_refs:
                new_refs.remove(ref_id)
    elif args.replace:
        operation = "Replace"
        if old_ref not in current_refs:
            print(f"Reference to replace not found: {old_ref} in {args.source_id}", file=sys.stderr)
            return 1
        new_refs.remove(old_ref)
        if new_ref not in new_refs:
            new_refs.append(new_ref)

    print("Update Plan:")
    print(f"  Operation: {operation}")
    print(f"  Source: {args.source_id}")
    print()
    print("Current references:")
    for ref in sorted(current_refs):
        print(f"  - {ref}")
    print()
    print("New references:")
    for ref in sorted(new_refs):
        marker = " (NEW)" if ref not in current_refs else ""
        print(f"  - {ref}{marker}")
    for ref in current_refs:
        if ref not in new_refs:
            print(f"  Removing: {ref}")
    print()

    if args.dry_run:
        print("DRY RUN: No changes will be made")
        return 0

    if not args.force:
        confirmation = input("Proceed with update? (y/N) ")
        if confirmation.lower() != "y":
            print("Operation cancelled")
            return 2

    backup_path = Path(f"{source_file}.bak")
    try:
        print("Creating backup...")
        shutil.copy2(source_file, backup_path)

        print("Updating references...")
        if not update_yaml_references(source_file, new_refs, dry_run=False):
            raise RuntimeError("Failed to update references")

        print("Cleaning up...")
        backup_path.unlink(missing_ok=True)

        clear_cache()
        print("Update completed successfully!")
        return 0

    except Exception as e:
        print(f"Update failed: {e}", file=sys.stderr)
        print("Rolling back changes...")
        if backup_path.exists():
            shutil.copy2(backup_path, source_file)
            backup_path.unlink()
        return 1


if __name__ == "__main__":
    sys.exit(main())
