#!/usr/bin/env python3
"""Convert file references in index table cells to proper Markdown links.

Processes index files (*-index.md) with tables that contain file references
and converts them to proper markdown links for better Obsidian navigation.

Exit codes follow ADR-035:
    0 - Success
    1 - Logic error (processing failure)
    2 - Configuration error (invalid path)
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


def _find_project_root(fallback_dir: Path | None = None) -> Path:
    """Find project root via git or directory traversal."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            return Path(result.stdout.strip())
    except FileNotFoundError:
        pass

    search = fallback_dir or Path(__file__).resolve().parent
    while search != search.parent:
        if (search / ".git").exists():
            return search
        search = search.parent
    raise SystemExit("Could not find project root (no .git directory found)")


def _validate_path_within_project(
    memories_path: str, project_root: Path
) -> Path:
    """Validate that a path is within the project root (CWE-22 mitigation)."""
    resolved = Path(memories_path).resolve()
    root_resolved = project_root.resolve()
    root_prefix = str(root_resolved) + "/"
    if not (str(resolved).startswith(root_prefix) or resolved == root_resolved):
        raise SystemExit(
            f"Security: MemoriesPath must be within project directory. "
            f"Provided: {resolved}, Project root: {root_resolved}"
        )
    return resolved


def _build_memory_names(memories_path: Path) -> dict[str, bool]:
    """Build lookup of memory file base names (without .md extension)."""
    names: dict[str, bool] = {}
    for md_file in memories_path.glob("*.md"):
        names[md_file.stem] = True
    return names


def _convert_single_refs(
    content: str, memory_names: dict[str, bool]
) -> str:
    """Convert table cells with single file references to markdown links.

    Pattern: | keyword | filename | -> | keyword | [filename](filename.md) |
    """
    single_ref_pattern = re.compile(r"(?<=\|)\s*([a-z][a-z0-9-]+)\s*(?=\|)")

    def replace_single(match: re.Match[str]) -> str:
        file_name = match.group(1).strip()
        cell_content = match.group(0)
        if re.match(r"^[\s-]+$", cell_content):
            return cell_content
        if file_name in memory_names and "[" not in cell_content:
            return f" [{file_name}]({file_name}.md) "
        return cell_content

    return single_ref_pattern.sub(replace_single, content)


def _convert_comma_refs(
    content: str, memory_names: dict[str, bool]
) -> str:
    """Convert comma-separated file lists in table cells to markdown links.

    Pattern: | file1, file2, file3 | -> | [file1](file1.md), [file2](file2.md) |
    """
    comma_pattern = re.compile(
        r"\|\s*([a-z][a-z0-9-]+(?:,\s*[a-z][a-z0-9-]+)+)\s*\|"
    )

    def replace_comma(match: re.Match[str]) -> str:
        file_list = match.group(1)
        if "[" in file_list:
            return match.group(0)
        files = [f.strip() for f in file_list.split(",")]
        converted = []
        for file_name in files:
            if file_name in memory_names:
                converted.append(f"[{file_name}]({file_name}.md)")
            else:
                converted.append(file_name)
        return f"| {', '.join(converted)} |"

    return comma_pattern.sub(replace_comma, content)


def _count_md_links(content: str) -> int:
    """Count markdown links ending in .md."""
    return len(re.findall(r"\[[^\]]+\]\([^)]+\.md\)", content))


def process_files(
    memories_path: Path,
    files_to_process: list[Path] | None = None,
    output_json: bool = False,
) -> dict:
    """Process index files and convert references to links.

    Returns statistics dict with FilesProcessed, FilesModified, LinksAdded, Errors.
    """
    memory_names = _build_memory_names(memories_path)
    all_index_files = sorted(memories_path.glob("*-index.md"))

    if files_to_process:
        normalized = {f.resolve() for f in files_to_process}
        index_files = [f for f in all_index_files if f.resolve() in normalized]
    else:
        index_files = all_index_files

    all_md_files = list(memories_path.glob("*.md"))

    if not output_json:
        print(f"Found {len(index_files)} index files and {len(all_md_files)} memory files")

    stats: dict[str, Any] = {
        "FilesProcessed": 0,
        "FilesModified": 0,
        "LinksAdded": 0,
        "Errors": [],
    }

    for file_path in index_files:
        stats["FilesProcessed"] += 1
        try:
            content = file_path.read_text(encoding="utf-8")
            if not content:
                continue

            original_content = content
            content = _convert_single_refs(content, memory_names)
            content = _convert_comma_refs(content, memory_names)

            if content != original_content:
                file_path.write_text(content, encoding="utf-8")
                if not output_json:
                    print(f"Updated: {file_path.name}")
                stats["FilesModified"] += 1
                original_count = _count_md_links(original_content)
                new_count = _count_md_links(content)
                stats["LinksAdded"] += new_count - original_count
        except Exception as exc:
            msg = f"Error processing {file_path.name}: {exc}"
            stats["Errors"].append(msg)
            if not output_json:
                print(f"WARNING: {msg}", file=sys.stderr)

    return stats


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Convert file references in index table cells to Markdown links.",
    )
    parser.add_argument(
        "--memories-path",
        help="Path to memories directory. Defaults to .serena/memories.",
    )
    parser.add_argument(
        "--files",
        nargs="*",
        help="Specific files to process. Defaults to all *-index.md files.",
    )
    parser.add_argument(
        "--output-json",
        action="store_true",
        help="Output machine-parseable JSON instead of human-readable text.",
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

    stats = process_files(
        memories_path, files_to_process, output_json=args.output_json
    )

    if args.output_json:
        print(json.dumps(stats, separators=(",", ":")))
    else:
        print(f"\nConversion complete. Modified {stats['FilesModified']} files.")

    return 1 if stats["Errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
