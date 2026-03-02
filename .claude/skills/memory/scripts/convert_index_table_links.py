#!/usr/bin/env python3
"""Convert file references in index table cells to proper Markdown links.

Processes index files with tables that contain file references and converts
them to proper markdown links for better Obsidian navigation.

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


def convert_single_refs(content: str, memory_names: dict[str, bool]) -> str:
    """Convert single file references in table cells."""
    def replace_single(match: re.Match) -> str:
        cell_content = match.group(0)
        file_name = match.group(1).strip()

        if re.match(r"^[\s-]+$", cell_content):
            return cell_content

        if file_name in memory_names and "[" not in cell_content:
            return f" [{file_name}]({file_name}.md) "
        return cell_content

    pattern = r"(?<=\|)\s*([a-z][a-z0-9-]+)\s*(?=\|)"
    return re.sub(pattern, replace_single, content)


def convert_comma_refs(content: str, memory_names: dict[str, bool]) -> str:
    """Convert comma-separated file lists in table cells."""
    def replace_list(match: re.Match) -> str:
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

        return "| " + ", ".join(converted) + " |"

    pattern = r"\|\s*([a-z][a-z0-9-]+(?:,\s*[a-z][a-z0-9-]+)+)\s*\|"
    return re.sub(pattern, replace_list, content)


def count_md_links(content: str) -> int:
    """Count markdown links in content."""
    return len(re.findall(r"\[[^\]]+\]\([^\)]+\.md\)", content))


def process_files(
    memories_path: Path,
    files_to_process: list[Path] | None,
    output_json: bool,
) -> dict:
    """Process index files and convert references."""
    all_index_files = sorted(memories_path.glob("*-index.md"))

    if files_to_process:
        normalized = {os.path.realpath(str(f)) for f in files_to_process}
        index_files = [
            f for f in all_index_files
            if os.path.realpath(str(f)) in normalized
        ]
    else:
        index_files = all_index_files

    memory_names = get_memory_names(memories_path)

    stats = {
        "FilesProcessed": 0,
        "FilesModified": 0,
        "LinksAdded": 0,
        "Errors": [],
    }

    if not output_json:
        print(f"Found {len(index_files)} index files and {len(memory_names)} memory files")

    for file_path in index_files:
        stats["FilesProcessed"] += 1

        try:
            content = file_path.read_text(encoding="utf-8")
            if not content.strip():
                continue

            original_content = content
            content = convert_single_refs(content, memory_names)
            content = convert_comma_refs(content, memory_names)

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
        description="Convert file references in index table cells to Markdown links."
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
