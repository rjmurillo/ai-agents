#!/usr/bin/env python3
"""Orchestrate memory cross-reference scripts for pre-commit hook integration.

Unified entry point for three memory cross-reference scripts:
1. convert_index_table_links (tables first)
2. convert_memory_references (backticks second)
3. improve_memory_graph_density (related sections last)

IMPORTANT: Always exits with code 0 (success) regardless of errors.
This is intentional for fail-open git hook behavior. Callers MUST parse
the JSON output (via --output-json) to determine actual success/failure.

Exit Codes:
    0  - Always (fail-open for hooks)

See: ADR-035 Exit Code Standardization
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path


def run_script(script_path: str, common_args: list[str]) -> dict | None:
    """Run a sub-script with --output-json and parse result."""
    cmd = [sys.executable, script_path, "--output-json"] + common_args
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=60,
        )
        if result.stdout.strip():
            return json.loads(result.stdout.strip())
    except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError) as e:
        return {"Error": str(e)}
    return None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Orchestrate memory cross-reference scripts."
    )
    parser.add_argument("--files-to-process", nargs="*", default=None)
    parser.add_argument("--memories-path", type=str, default="")
    parser.add_argument("--output-json", action="store_true")
    parser.add_argument("--skip-path-validation", action="store_true")
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent

    aggregate = {
        "IndexLinksAdded": 0,
        "BacktickLinksAdded": 0,
        "RelatedSectionsAdded": 0,
        "FilesModified": 0,
        "Errors": [],
        "Success": True,
    }

    common_args: list[str] = []
    if args.memories_path:
        common_args.extend(["--memories-path", args.memories_path])
    if args.files_to_process:
        common_args.extend(["--files-to-process"] + args.files_to_process)
    if args.skip_path_validation:
        common_args.append("--skip-path-validation")

    scripts = [
        ("Convert-IndexTableLinks", "convert_index_table_links.py", "IndexLinksAdded", "LinksAdded"),
        ("Convert-MemoryReferences", "convert_memory_references.py", "BacktickLinksAdded", "LinksAdded"),
        ("Improve-MemoryGraphDensity", "improve_memory_graph_density.py", "RelatedSectionsAdded", "RelationshipsAdded"),
    ]

    for step_num, (label, script_name, agg_key, result_key) in enumerate(scripts, 1):
        if not args.output_json:
            print(f"\n=== Step {step_num}/3: {label} ===")

        script_path = str(script_dir / script_name)

        try:
            result = run_script(script_path, common_args)
            if result:
                if "Error" in result and isinstance(result["Error"], str):
                    aggregate["Errors"].append(f"{label}: {result['Error']}")
                else:
                    aggregate[agg_key] = result.get(result_key, 0)
                    files_mod = result.get("FilesModified", 0)
                    if files_mod > 0:
                        aggregate["FilesModified"] += files_mod
                    errors = result.get("Errors", [])
                    if errors:
                        aggregate["Errors"].extend(errors)
        except Exception as e:
            aggregate["Errors"].append(f"{label}: {e}")
            if not args.output_json:
                print(f"Warning: {label} failed: {e}", file=sys.stderr)

    aggregate["Success"] = len(aggregate["Errors"]) == 0

    if args.output_json:
        print(json.dumps(aggregate))
    else:
        print(f"\n=== Summary ===")
        print(f"Index table links added: {aggregate['IndexLinksAdded']}")
        print(f"Backtick references converted: {aggregate['BacktickLinksAdded']}")
        print(f"Related sections added: {aggregate['RelatedSectionsAdded']}")
        print(f"Total files modified: {aggregate['FilesModified']}")
        if aggregate["Errors"]:
            print("\nWarnings/Errors:")
            for err in aggregate["Errors"]:
                print(f"  - {err}")

    sys.exit(0)


if __name__ == "__main__":
    main()
