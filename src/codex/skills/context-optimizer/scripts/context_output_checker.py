"""Generated context output checks for one source document."""

from __future__ import annotations

import re
from pathlib import Path

from context_output_index import _detail_file_contents, build_index
from context_output_parsing import parse_sections
from context_output_storage import _detail_names, _read_text, _resolved_repo_root
from path_validation import validate_path_within_repo


def _index_references(index_content: str) -> list[str]:
    """Return detail references from an index in source order."""
    return [reference.strip() for reference in re.findall(r"\(see:\s*([^)]+)\)", index_content)]


def _check_index(
    expected_index: str,
    index_path: Path,
    repo_root: Path,
    staged: bool,
) -> list[str]:
    """Check one generated index without writing to disk."""
    actual_index = _read_text(index_path, repo_root, staged)
    if actual_index is None:
        return [f"Missing index file: {index_path}"]
    if actual_index == expected_index:
        return []

    actual_references = _index_references(actual_index)
    expected_references = _index_references(expected_index)
    issue_name = (
        "Index reference mismatch"
        if actual_references and actual_references != expected_references
        else "Index drift"
    )
    return [f"{issue_name}: {index_path}"]


def _check_details(
    expected_details: dict[str, str],
    detail_dir: Path,
    repo_root: Path,
    staged: bool,
) -> list[str]:
    """Check one generated detail directory without writing to disk."""
    if not staged and not detail_dir.exists():
        return [f"Missing detail file: {detail_dir / filename}" for filename in expected_details]
    if not staged and not detail_dir.is_dir():
        return [f"Detail path is not a directory: {detail_dir}"]

    actual_names = _detail_names(detail_dir, repo_root, staged)
    expected_names = set(expected_details)
    issues = [
        f"Missing detail file: {detail_dir / filename}"
        for filename in sorted(expected_names - actual_names)
    ]
    issues.extend(
        f"Extra detail file: {detail_dir / filename}"
        for filename in sorted(actual_names - expected_names)
    )
    for filename in sorted(expected_names & actual_names):
        file_path = detail_dir / filename
        actual_content = _read_text(file_path, repo_root, staged)
        if actual_content is None:
            issues.append(f"Detail path is not a file: {file_path}")
        elif actual_content != expected_details[filename]:
            issues.append(f"Detail drift: {file_path}")
    return issues


def check_generated_files(
    content: str,
    detail_dir: Path,
    index_path: Path,
    detail_dir_ref: str,
    repo_root: Path | None = None,
    staged: bool = False,
) -> list[str]:
    """Check generated index and detail files without writing to disk."""
    effective_root = _resolved_repo_root(repo_root)
    sections = parse_sections(content)
    expected_details = _detail_file_contents(sections)
    expected_index = build_index(sections, detail_dir_ref)
    validated_dir = validate_path_within_repo(detail_dir, effective_root)
    validated_index = validate_path_within_repo(index_path, effective_root)
    issues = _check_index(expected_index, validated_index, effective_root, staged)
    issues.extend(_check_details(expected_details, validated_dir, effective_root, staged))
    return issues
