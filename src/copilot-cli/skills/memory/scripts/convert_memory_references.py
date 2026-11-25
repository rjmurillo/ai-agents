#!/usr/bin/env python3
"""Convert backtick memory references to proper Markdown links.

Processes markdown files in .serena/memories/ and converts backtick
references like `memory-name` to [memory-name](memory-name.md),
but only when the referenced file exists.

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


def _convert_backtick_refs(content: str, memory_names: dict[str, bool]) -> str:
    """Convert backtick references to markdown links.

    Pattern: `memory-name` -> [memory-name](memory-name.md)
    Excludes:
    - File paths (containing / or \\)
    - Code snippets
    - Already linked items (preceded by [ or ( or followed by ] or ))
    - Names with spaces
    """
    pattern = re.compile(r"(?<![\[\(])`([a-z0-9]+(?:-[a-z0-9]+)*)`(?![\]\)])")

    def replace_backtick(match: re.Match[str]) -> str:
        memory_name = match.group(1)
        if memory_name in memory_names:
            return f"[{memory_name}]({memory_name}.md)"
        return match.group(0)

    return pattern.sub(replace_backtick, content)


def process_files(
    memories_path: Path,
    files_to_process: list[Path] | None = None,
    output_json: bool = False,
    dry_run: bool = False,
) -> ConversionStats:
    """Process memory files and convert backtick references to links.

    With ``dry_run`` no file is written; FilesModified counts the files that
    would change.

    Returns statistics dict with FilesProcessed, FilesModified, LinksAdded, Errors.
    """
    all_memory_files = sorted(memories_path.glob("*.md"))
    memory_names = _build_memory_names(memories_path)

    if files_to_process:
        normalized = {f.resolve() for f in files_to_process}
        target_files = [f for f in all_memory_files if f.resolve() in normalized]
    else:
        target_files = all_memory_files

    if not output_json:
        print(f"Found {len(all_memory_files)} memory files")

    stats: ConversionStats = process_link_files(
        target_files,
        memory_names,
        ConversionOptions((_convert_backtick_refs,), output_json, dry_run),
    )
    return stats


_HELP_EPILOG = """\
examples:
  %(prog)s --dry-run
  %(prog)s --memories-path .serena/memories --output-json

exit codes:
  0  references converted, or nothing to convert
  1  a file failed to convert, no project root, or path outside the project
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Convert backtick memory references to Markdown links.",
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
        help="Specific files to process. Defaults to all *.md files.",
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
