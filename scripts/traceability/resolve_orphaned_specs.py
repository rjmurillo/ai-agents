#!/usr/bin/env python3
"""Identify and help resolve orphaned specs in the traceability graph.

Scans the traceability graph to find orphaned specifications:
- Requirements with no designs referencing them
- Designs with no requirements or no tasks referencing them
- Tasks with no design references

Provides options to resolve orphans through listing, archival, or deletion.

EXIT CODES:
  0 - Success (no orphans or action completed)
  1 - Error (invalid path, file operation failed)
  2 - Orphans found (when --action list)

See: ADR-035 Exit Code Standardization
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path
from typing import Any

_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.traceability.spec_utils import (  # noqa: E402
    load_all_specs,
    validate_specs_path,
)
from scripts.traceability.traceability_cache import clear_cache  # noqa: E402


def find_orphaned_specs(specs: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Detect orphaned specs by analyzing reference relationships."""
    orphans: dict[str, list[dict[str, Any]]] = {
        "requirements": [],
        "designs": [],
        "tasks": [],
    }

    req_refs: dict[str, list[str]] = {rid: [] for rid in specs["requirements"]}
    design_refs: dict[str, list[str]] = {did: [] for did in specs["designs"]}

    for design_id, design in specs["designs"].items():
        for related_id in design.get("related", []):
            if related_id.startswith("REQ-") and related_id in req_refs:
                req_refs[related_id].append(design_id)

    for task_id, task in specs["tasks"].items():
        for related_id in task.get("related", []):
            if related_id.startswith("DESIGN-") and related_id in design_refs:
                design_refs[related_id].append(task_id)

    for req_id in specs["requirements"]:
        if not req_refs[req_id]:
            orphans["requirements"].append({
                "id": req_id,
                "spec": specs["requirements"][req_id],
                "reason": "No design references this requirement",
            })

    for design_id, design in specs["designs"].items():
        has_req = any(r.startswith("REQ-") for r in design.get("related", []))
        has_task = bool(design_refs[design_id])

        if not has_req and not has_task:
            reason = "No requirement reference and no tasks reference this design"
        elif not has_req:
            reason = "No requirement reference"
        elif not has_task:
            reason = "No tasks reference this design"
        else:
            continue
        orphans["designs"].append({"id": design_id, "spec": design, "reason": reason})

    for task_id, task in specs["tasks"].items():
        if not any(r.startswith("DESIGN-") for r in task.get("related", [])):
            orphans["tasks"].append({
                "id": task_id,
                "spec": task,
                "reason": "No design reference",
            })

    return orphans


def show_orphans(
    orphans: dict[str, list[dict[str, Any]]], type_filter: str
) -> int:
    """Display orphaned specs. Returns 0 if none found, 2 if orphans exist."""
    total = 0
    for category in ("requirements", "designs", "tasks"):
        if type_filter not in ("all", category):
            continue
        items = orphans[category]
        if not items:
            continue
        label = f"Orphaned {category.title()}"
        print(label + ":")
        for orphan in sorted(items, key=lambda o: o["id"]):
            print(f"  {orphan['id']}: {orphan['reason']}")
            print(f"    File: {orphan['spec'].get('filePath', 'unknown')}")
        print()
        total += len(items)

    if total == 0:
        print("No orphaned specs found.")
        return 0
    print(f"Total orphaned specs: {total}")
    return 2


def archive_orphans(
    orphans: dict[str, list[dict[str, Any]]],
    type_filter: str,
    base_path: Path,
    dry_run: bool,
    force: bool,
) -> int:
    """Move orphaned specs to an archive directory."""
    to_archive = _collect_filtered_orphans(orphans, type_filter)
    if not to_archive:
        print("No orphaned specs to archive.")
        return 0

    print("Specs to archive:")
    for spec in to_archive:
        print(f"  {spec['id']}")
    print()

    if dry_run:
        print("DRY RUN: No files will be moved")
        return 0

    if not force:
        confirmation = input(f"Archive {len(to_archive)} spec(s)? (y/N) ")
        if confirmation.lower() != "y":
            print("Operation cancelled")
            return 0

    archive_base = base_path / ".archive"
    for subdir in ("requirements", "design", "tasks"):
        (archive_base / subdir).mkdir(parents=True, exist_ok=True)

    for spec in to_archive:
        target_subdir = _id_to_archive_subdir(spec["id"])
        src = Path(spec["spec"]["filePath"])
        dest = archive_base / target_subdir / src.name
        shutil.move(str(src), str(dest))
        print(f"  Archived: {spec['id']} -> {dest}")

    print(f"Archived {len(to_archive)} spec(s).")
    clear_cache()
    return 0


def delete_orphans(
    orphans: dict[str, list[dict[str, Any]]],
    type_filter: str,
    dry_run: bool,
    force: bool,
) -> int:
    """Delete orphaned spec files."""
    to_delete = _collect_filtered_orphans(orphans, type_filter)
    if not to_delete:
        print("No orphaned specs to delete.")
        return 0

    print("Specs to DELETE:")
    for spec in to_delete:
        print(f"  {spec['id']}: {spec['spec']['filePath']}")
    print()

    if dry_run:
        print("DRY RUN: No files will be deleted")
        return 0

    if not force:
        print("WARNING: This action cannot be undone!")
        confirmation = input(f"Type 'DELETE' to confirm deletion of {len(to_delete)} spec(s): ")
        if confirmation != "DELETE":
            print("Operation cancelled")
            return 0

    for spec in to_delete:
        Path(spec["spec"]["filePath"]).unlink()
        print(f"  Deleted: {spec['id']}")

    print(f"Deleted {len(to_delete)} spec(s).")
    clear_cache()
    return 0


def _collect_filtered_orphans(
    orphans: dict[str, list[dict[str, Any]]], type_filter: str
) -> list[dict[str, Any]]:
    """Collect orphans matching the type filter."""
    result: list[dict[str, Any]] = []
    for category in ("requirements", "designs", "tasks"):
        if type_filter in ("all", category):
            result.extend(orphans[category])
    return result


def _id_to_archive_subdir(spec_id: str) -> str:
    """Map a spec ID prefix to its archive subdirectory."""
    if spec_id.startswith("REQ-"):
        return "requirements"
    if spec_id.startswith("DESIGN-"):
        return "design"
    return "tasks"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Identify and resolve orphaned specs in the traceability graph."
    )
    parser.add_argument("--specs-path", default=".agents/specs", help="Path to specs directory")
    parser.add_argument(
        "--action",
        choices=["list", "archive", "delete"],
        default="list",
        help="Action to take on orphans (default: list)",
    )
    parser.add_argument(
        "--type",
        choices=["all", "requirements", "designs", "tasks"],
        default="all",
        help="Filter by spec type (default: all)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Show plan without changes")
    parser.add_argument("--force", action="store_true", help="Skip confirmation prompts")
    parser.add_argument("--no-cache", action="store_true", help="Bypass cache")
    args = parser.parse_args(argv)

    try:
        resolved_path = validate_specs_path(args.specs_path)
    except SystemExit:
        return 1

    specs = load_all_specs(resolved_path, use_cache=not args.no_cache)
    orphans = find_orphaned_specs(specs)

    if args.action == "list":
        return show_orphans(orphans, args.type)
    if args.action == "archive":
        return archive_orphans(orphans, args.type, resolved_path, args.dry_run, args.force)
    if args.action == "delete":
        return delete_orphans(orphans, args.type, args.dry_run, args.force)

    return 0


if __name__ == "__main__":
    sys.exit(main())
