#!/usr/bin/env python3
"""Orchestrate memory cross-reference scripts for pre-commit hook integration.

Unified entry point that executes all three memory cross-reference scripts
in the correct order:
1. convert_index_table_links (tables first)
2. convert_memory_references (backticks second)
3. improve_memory_graph_density (related sections last, atomic files only)

Index files (*-index.md) are excluded from Related section addition
per ADR-017 requirement for pure lookup table format (token efficiency).

IMPORTANT: This script always exits with code 0 (success) regardless of errors.
This is intentional for fail-open git hook behavior. Callers MUST parse the
JSON output (via --output-json) to determine actual success/failure status.
The JSON output includes a 'Success' property (true/false) and 'Errors' array.

NOTE: FilesModified represents total modifications across all scripts, not unique
files. A file modified by multiple scripts in sequence will be counted once per
script that modifies it.

Exit codes follow ADR-035:
    0 - Always (fail-open for git hooks)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from convert_index_table_links import (
    _find_project_root,
    _validate_path_within_project,
)
from convert_index_table_links import process_files as process_index_links
from convert_memory_references import process_files as process_backtick_refs
from improve_memory_graph_density import process_files as process_graph_density


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Orchestrate all memory cross-reference scripts.",
    )
    parser.add_argument(
        "--files",
        nargs="*",
        help="Specific memory files to process. Defaults to all files.",
    )
    parser.add_argument(
        "--memories-path",
        help="Path to memories directory. Defaults to .serena/memories.",
    )
    parser.add_argument(
        "--output-json",
        action="store_true",
        help="Output machine-parseable JSON statistics.",
    )
    parser.add_argument(
        "--skip-path-validation",
        action="store_true",
        help="Skip CWE-22 path validation (for testing only).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    project_root = _find_project_root()

    if args.memories_path:
        if args.skip_path_validation:
            memories_path = Path(args.memories_path).resolve()
        else:
            memories_path = _validate_path_within_project(
                args.memories_path, project_root
            )
    else:
        memories_path = project_root / ".serena" / "memories"

    files_to_process = [Path(f) for f in args.files] if args.files else None

    aggregate: dict[str, Any] = {
        "IndexLinksAdded": 0,
        "BacktickLinksAdded": 0,
        "RelatedSectionsAdded": 0,
        "FilesModified": 0,
        "Errors": [],
        "Success": True,
    }

    # Step 1: Convert index table links
    if not args.output_json:
        print("=== Step 1/3: Converting index table links ===")
    try:
        result = process_index_links(
            memories_path, files_to_process, output_json=True
        )
        aggregate["IndexLinksAdded"] = result.get("LinksAdded", 0)
        aggregate["FilesModified"] += result.get("FilesModified", 0)
        if result.get("Errors"):
            aggregate["Errors"].extend(result["Errors"])
    except Exception as exc:
        aggregate["Errors"].append(f"convert_index_table_links: {exc}")
        if not args.output_json:
            print(f"WARNING: convert_index_table_links failed: {exc}", file=sys.stderr)

    # Step 2: Convert backtick references
    if not args.output_json:
        print("\n=== Step 2/3: Converting backtick references ===")
    try:
        result = process_backtick_refs(
            memories_path, files_to_process, output_json=True
        )
        aggregate["BacktickLinksAdded"] = result.get("LinksAdded", 0)
        aggregate["FilesModified"] += result.get("FilesModified", 0)
        if result.get("Errors"):
            aggregate["Errors"].extend(result["Errors"])
    except Exception as exc:
        aggregate["Errors"].append(f"convert_memory_references: {exc}")
        if not args.output_json:
            print(f"WARNING: convert_memory_references failed: {exc}", file=sys.stderr)

    # Step 3: Add Related sections
    if not args.output_json:
        print("\n=== Step 3/3: Adding Related sections ===")
    try:
        result = process_graph_density(
            memories_path, files_to_process, output_json=True
        )
        aggregate["RelatedSectionsAdded"] = result.get("RelationshipsAdded", 0)
        aggregate["FilesModified"] += result.get("FilesModified", 0)
        if result.get("Errors"):
            aggregate["Errors"].extend(result["Errors"])
    except Exception as exc:
        aggregate["Errors"].append(f"improve_memory_graph_density: {exc}")
        if not args.output_json:
            print(f"WARNING: improve_memory_graph_density failed: {exc}", file=sys.stderr)

    aggregate["Success"] = len(aggregate["Errors"]) == 0

    if args.output_json:
        print(json.dumps(aggregate, separators=(",", ":")))
    else:
        print("\n=== Summary ===")
        print(f"Index table links added: {aggregate['IndexLinksAdded']}")
        print(f"Backtick references converted: {aggregate['BacktickLinksAdded']}")
        print(f"Related sections added: {aggregate['RelatedSectionsAdded']}")
        print(f"Total files modified: {aggregate['FilesModified']}")
        if aggregate["Errors"]:
            print("\nWarnings/Errors:")
            for err in aggregate["Errors"]:
                print(f"  - {err}")

    # Always exit 0 (fail-open for hooks)
    return 0


if __name__ == "__main__":
    sys.exit(main())
