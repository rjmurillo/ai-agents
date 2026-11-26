"""File conversion and statistics shared by the memory link commands."""

from __future__ import annotations

import re
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict


def _find_project_root(fallback_dir: Path | None = None) -> Path:
    """Find project root via git or directory traversal."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--git-common-dir"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if result.returncode == 0:
            git_common = Path(result.stdout.strip())
            if not git_common.is_absolute():
                git_common = (Path.cwd() / git_common).resolve()
            else:
                git_common = git_common.resolve()
            return git_common.parent
    except FileNotFoundError:
        pass

    # Walk up from the caller's directory, never the script's own install
    # tree: a vendored plugin copy must not edit itself as the project.
    search = (fallback_dir or Path.cwd()).resolve()
    while search != search.parent:
        if (search / ".git").exists():
            return search
        search = search.parent
    raise SystemExit("Could not find project root (no .git directory found)")


def _validate_path_within_project(memories_path: str, project_root: Path) -> Path:
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


Converter = Callable[[str, dict[str, bool]], str]


class ConversionCounts(TypedDict):
    FilesProcessed: int
    FilesModified: int
    LinksAdded: int
    Errors: list[str]


class ConversionStats(ConversionCounts, total=False):
    DryRun: bool


@dataclass(frozen=True, slots=True)
class ConversionOptions:
    transforms: Sequence[Converter]
    output_json: bool
    dry_run: bool


def _count_md_links(content: str) -> int:
    return len(re.findall(r"\[[^\]]+\]\([^)]+\.md\)", content))


def process_link_files(
    files: list[Path], memory_names: dict[str, bool], options: ConversionOptions
) -> ConversionStats:
    stats: ConversionStats = {
        "FilesProcessed": 0,
        "FilesModified": 0,
        "LinksAdded": 0,
        "Errors": [],
    }
    for file_path in files:
        stats["FilesProcessed"] += 1
        try:
            original = file_path.read_text(encoding="utf-8")
            if not original:
                continue
            content = original
            for transform in options.transforms:
                content = transform(content, memory_names)
            if content != original:
                if not options.dry_run:
                    file_path.write_text(content, encoding="utf-8")
                if not options.output_json:
                    action = "Would update" if options.dry_run else "Updated"
                    print(f"{action}: {file_path.name}")
                stats["FilesModified"] += 1
                stats["LinksAdded"] += _count_md_links(content) - _count_md_links(original)
        except Exception as exc:
            # Both commands keep processing other files after conversion or I/O errors.
            message = f"Error processing {file_path.name}: {exc}"
            stats["Errors"].append(message)
            if not options.output_json:
                print(f"WARNING: {message}", file=sys.stderr)
    if options.dry_run:
        stats["DryRun"] = True
    return stats
