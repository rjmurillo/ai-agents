#!/usr/bin/env python3
"""Convert backtick memory references to proper Markdown links.

Processes markdown files in .serena/memories/ and converts backtick
references like `memory-name` to [memory-name](memory-name.md).
Only converts if the referenced file exists.

Exit Codes:
    0  - Success: Conversion completed
    1  - Error: Git repository or path error

See: ADR-035 Exit Code Standardization
"""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path


def get_project_root() -> str:
    """Find project root via git or directory traversal."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / ".git").exists():
            return str(current)
        current = current.parent

    print("Could not find project root", file=sys.stderr)
    sys.exit(1)


def validate_path_containment(path: str, project_root: str) -> bool:
    """CWE-22: Ensure path is within project root."""
    resolved = os.path.realpath(path)
    root = os.path.realpath(project_root)
    root_with_sep = root.rstrip(os.sep) + os.sep
    return resolved.startswith(root_with_sep) or resolved == root


def get_memory_names(memories_path: Path) -> dict[str, bool]:
    """Build set of memory file base names."""
    names: dict[str, bool] = {}
    if not memories_path.is_dir():
        return names
    for f in memories_path.glob("*.md"):
        names[f.stem] = True
    return names


def count_md_links(content: str) -> int:
    """Count markdown links in content."""
    return len(re.findall(r"\[[^\]]+\]\([^\)]+\.md\)", content))


def convert_backtick_refs(content: str, memory_names: dict[str, bool]) -> str:
    """Convert backtick references to markdown links."""
    pattern = r"(?<![\[\(])`([a-z0-9]+(?:-[a-z0-9]+)*)`(?![\]\)])"

    def replace_ref(match: re.Match) -> str:
        memory_name = match.group(1)
        if memory_name in memory_names:
            return f"[{memory_name}]({memory_name}.md)"
        return match.group(0)

    return re.sub(pattern, replace_ref, content)


def process_files(
    memories_path: Path,
    files_to_process: list[Path] | None,
    output_json: bool,
) -> dict:
    """Process memory files and convert backtick references."""
    all_memory_files = sorted(memories_path.glob("*.md"))

    if files_to_process:
        normalized = {os.path.realpath(str(f)) for f in files_to_process}
        memory_files = [
            f for f in all_memory_files
            if os.path.realpath(str(f)) in normalized
        ]
    else:
        memory_files = all_memory_files

    memory_names = get_memory_names(memories_path)

    stats = {
        "FilesProcessed": 0,
        "FilesModified": 0,
        "LinksAdded": 0,
        "Errors": [],
    }

    if not output_json:
        print(f"Found {len(all_memory_files)} memory files")

    for file_path in memory_files:
        stats["FilesProcessed"] += 1

        try:
            content = file_path.read_text(encoding="utf-8")
            if not content.strip():
                continue

            original_content = content
            content = convert_backtick_refs(content, memory_names)

            if content != original_content:
                file_path.write_text(content, encoding="utf-8")
                if not output_json:
                    print(f"Updated: {file_path.name}")
                stats["FilesModified"] += 1
                original_count = count_md_links(original_content)
                new_count = count_md_links(content)
                stats["LinksAdded"] += new_count - original_count
        except Exception as e:
            error_msg = f"Error processing {file_path.name}: {e}"
            stats["Errors"].append(error_msg)
            if not output_json:
                print(f"Warning: {error_msg}", file=sys.stderr)

    return stats


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert backtick memory references to Markdown links."
    )
    parser.add_argument("--memories-path", type=str, default="")
    parser.add_argument("--files-to-process", nargs="*", default=None)
    parser.add_argument("--output-json", action="store_true")
    parser.add_argument("--skip-path-validation", action="store_true")
    args = parser.parse_args()

    project_root = get_project_root()

    if args.memories_path:
        if not args.skip_path_validation:
            if not validate_path_containment(args.memories_path, project_root):
                print(
                    "Security: MemoriesPath must be within project directory.",
                    file=sys.stderr,
                )
                sys.exit(1)
        memories_path = Path(os.path.realpath(args.memories_path))
    else:
        memories_path = Path(project_root) / ".serena" / "memories"

    files_to_process = None
    if args.files_to_process:
        files_to_process = [Path(f) for f in args.files_to_process]

    stats = process_files(memories_path, files_to_process, args.output_json)

    if args.output_json:
        print(json.dumps(stats))
    else:
        print(f"\nConversion complete. Modified {stats['FilesModified']} files.")


if __name__ == "__main__":
    main()
