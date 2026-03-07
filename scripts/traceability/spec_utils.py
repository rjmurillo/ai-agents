"""Shared utilities for traceability spec operations.

Provides YAML frontmatter parsing, spec file location, path validation,
and spec ID format validation used by multiple traceability scripts.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

from scripts.traceability.traceability_cache import (
    get_cached_spec,
    get_file_hash,
    set_cached_spec,
)

SPEC_ID_PATTERN = re.compile(r"^(REQ|DESIGN|TASK)-[A-Z0-9]+$")

TYPE_TO_SUBDIR = {
    "REQ": "requirements",
    "DESIGN": "design",
    "TASK": "tasks",
}


def is_valid_spec_id(spec_id: str) -> bool:
    """Check whether a spec ID matches the TYPE-ID format."""
    return bool(SPEC_ID_PATTERN.match(spec_id))


def get_spec_type(spec_id: str) -> str:
    """Extract the type prefix from a spec ID (e.g., 'REQ' from 'REQ-001')."""
    return spec_id.split("-")[0]


def get_spec_subdir(spec_id: str) -> str:
    """Return the subdirectory name for a spec type."""
    return TYPE_TO_SUBDIR.get(get_spec_type(spec_id), "")


def find_spec_file(spec_id: str, base_path: Path) -> Path | None:
    """Locate the file for a given spec ID under the base path."""
    subdir = get_spec_subdir(spec_id)
    if not subdir:
        return None
    file_path = base_path / subdir / f"{spec_id}.md"
    if file_path.exists():
        return file_path
    return None


def parse_yaml_frontmatter(
    file_path: Path, use_cache: bool = True
) -> dict[str, Any] | None:
    """Parse YAML frontmatter from a spec markdown file.

    Returns a dict with keys: type, id, status, related, filePath.
    Returns None if the file has no valid frontmatter.
    """
    if use_cache:
        fhash = get_file_hash(file_path)
        if fhash:
            cached = get_cached_spec(file_path, fhash)
            if cached:
                return cached

    try:
        content = file_path.read_text(encoding="utf-8")
    except OSError:
        return None

    if not content:
        return None

    match = re.match(r"(?s)^---\r?\n(.+?)\r?\n---", content)
    if not match:
        return None

    yaml_block = match.group(1)
    result: dict[str, Any] = {
        "type": "",
        "id": "",
        "status": "",
        "related": [],
        "filePath": str(file_path),
    }

    type_match = re.search(r"(?m)^type:\s*(.+)$", yaml_block)
    if type_match:
        result["type"] = type_match.group(1).strip()

    id_match = re.search(r"(?m)^id:\s*(.+)$", yaml_block)
    if id_match:
        result["id"] = id_match.group(1).strip()

    status_match = re.search(r"(?m)^status:\s*(.+)$", yaml_block)
    if status_match:
        result["status"] = status_match.group(1).strip()

    related_match = re.search(
        r"(?s)related:\s*\r?\n((?:\s+-\s+.+\r?\n?)+)", yaml_block
    )
    if related_match:
        related_block = related_match.group(1)
        result["related"] = re.findall(r"-\s+([A-Z]+-[A-Z0-9]+)", related_block)

    if use_cache:
        fhash = get_file_hash(file_path)
        if fhash:
            set_cached_spec(file_path, fhash, result)

    return result


def parse_frontmatter_with_content(
    file_path: Path,
) -> dict[str, Any] | None:
    """Parse frontmatter and return it along with the raw content.

    Returns a dict with keys: frontmatter, body, related, content.
    Used by scripts that need to modify frontmatter in place.
    """
    try:
        content = file_path.read_text(encoding="utf-8")
    except OSError:
        return None

    if not content:
        return None

    match = re.match(r"(?s)^(---\r?\n.+?\r?\n---\r?\n)(.*)", content)
    if not match:
        return None

    frontmatter = match.group(1)
    body = match.group(2)

    yaml_block = re.sub(r"^---\r?\n", "", frontmatter)
    yaml_block = re.sub(r"\r?\n---\r?\n$", "", yaml_block)

    related: list[str] = []
    related_match = re.search(
        r"(?s)related:\s*\r?\n((?:\s+-\s+.+\r?\n?)+)", yaml_block
    )
    if related_match:
        related = re.findall(r"-\s+([A-Z]+-[A-Z0-9]+)", related_match.group(1))

    return {
        "frontmatter": frontmatter,
        "body": body,
        "related": related,
        "content": content,
    }


def load_all_specs(base_path: Path, use_cache: bool = True) -> dict[str, Any]:
    """Load all specs from the base path, organized by type.

    Returns a dict with keys: requirements, designs, tasks, all.
    Each value is a dict mapping spec ID to parsed spec data.
    """
    specs: dict[str, dict[str, Any]] = {
        "requirements": {},
        "designs": {},
        "tasks": {},
        "all": {},
    }

    for subdir, prefix, category in [
        ("requirements", "REQ-", "requirements"),
        ("design", "DESIGN-", "designs"),
        ("tasks", "TASK-", "tasks"),
    ]:
        dir_path = base_path / subdir
        if not dir_path.exists():
            continue
        for md_file in sorted(dir_path.glob(f"{prefix}*.md")):
            spec = parse_yaml_frontmatter(md_file, use_cache=use_cache)
            if spec and spec["id"]:
                specs[category][spec["id"]] = spec
                specs["all"][spec["id"]] = spec

    return specs


def get_repo_root() -> Path | None:
    """Get the git repository root, or None if not in a repo."""
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
    return None


def validate_specs_path(specs_path: str) -> Path:
    """Resolve and validate a specs path, checking for path traversal.

    Raises SystemExit(1) on invalid path.
    """
    resolved = Path(specs_path).resolve()
    if not resolved.exists():
        raise SystemExit(f"Specs path not found: {specs_path}")

    repo_root = get_repo_root()
    if repo_root and not Path(specs_path).is_absolute():
        allowed_base = str(repo_root.resolve()) + "/"
        if not str(resolved).startswith(allowed_base):
            raise SystemExit(
                f"Path traversal attempt detected: '{specs_path}' is outside the repository root."
            )

    return resolved
