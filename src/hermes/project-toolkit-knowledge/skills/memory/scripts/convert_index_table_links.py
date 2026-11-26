#!/usr/bin/env python3
"""Convert file references in index table cells to proper Markdown links.

Processes index files (*-index.md) with tables that contain file references
and converts them to proper markdown links for better Obsidian navigation.

Exit codes follow ADR-035:
    0 - Success
    1 - Logic error (processing failure)
    2 - Configuration error (invalid path)
"""

import argparse
import json
import re
import subprocess as subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from memory_link_processing import (
    ConversionOptions,
    ConversionStats,
    _build_memory_names,
    _find_project_root,
    _validate_path_within_project,
    process_link_files,
)
from memory_link_processing import (
    _count_md_links as _count_md_links,
)


def _convert_single_refs(content: str, memory_names: dict[str, bool]) -> str:
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


def _convert_comma_refs(content: str, memory_names: dict[str, bool]) -> str:
    """Convert comma-separated file lists in table cells to markdown links.

    Pattern: | file1, file2, file3 | -> | [file1](file1.md), [file2](file2.md) |
    """
    comma_pattern = re.compile(r"\|\s*([a-z][a-z0-9-]+(?:,\s*[a-z][a-z0-9-]+)+)\s*\|")

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


def process_files(
    memories_path: Path,
    files_to_process: list[Path] | None = None,
    output_json: bool = False,
    dry_run: bool = False,
) -> ConversionStats:
    """Process index files and convert references to links.

    With ``dry_run`` no file is written; FilesModified counts the files that
    would change.

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

    stats: ConversionStats = process_link_files(
        index_files,
        memory_names,
        ConversionOptions((_convert_single_refs, _convert_comma_refs), output_json, dry_run),
    )
    return stats


_HELP_EPILOG = """\
examples:
  %(prog)s --dry-run
  %(prog)s --memories-path .serena/memories --output-json

exit codes:
  0  files converted, or nothing to convert
  1  a file failed to convert, no project root, or path outside the project
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Convert file references in index table cells to Markdown links.",
        epilog=_HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
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
        "--dry-run",
        action="store_true",
        help="Report which files would change and how many links would be added; write nothing.",
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
            memories_path = _validate_path_within_project(args.memories_path, project_root)
    else:
        memories_path = project_root / ".serena" / "memories"

    files_to_process = [Path(f) for f in args.files] if args.files else None

    stats = process_files(
        memories_path, files_to_process, output_json=args.output_json, dry_run=args.dry_run
    )

    if args.output_json:
        print(json.dumps(stats, separators=(",", ":")))
    else:
        verb = "Dry run complete. Would modify" if args.dry_run else "Conversion complete. Modified"
        print(f"\n{verb} {stats['FilesModified']} files.")

    return 1 if stats["Errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
