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
    if not resolved.is_relative_to(root_resolved):
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


def _count_md_links(content: str) -> int:
    """Count markdown links ending in .md."""
    return len(re.findall(r"\[[^\]]+\]\([^)]+\.md\)", content))


def _convert_backtick_refs(
    content: str, memory_names: dict[str, bool]
) -> str:
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
) -> dict:
    """Process memory files and convert backtick references to links.

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

    stats: dict[str, Any] = {
        "FilesProcessed": 0,
        "FilesModified": 0,
        "LinksAdded": 0,
        "Errors": [],
    }

    for file_path in target_files:
        stats["FilesProcessed"] += 1
        try:
            content = file_path.read_text(encoding="utf-8")
            if not content:
                continue

            original_content = content
            content = _convert_backtick_refs(content, memory_names)

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
        description="Convert backtick memory references to Markdown links.",
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
