"""Validate generated context outputs named by an explicit manifest."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from context_output_checker import check_generated_files
from context_output_storage import (
    _detail_names,
    _manifest_path_value,
    _output_files,
    _read_text,
    _repo_relative_path,
    _resolved_repo_root,
)
from path_validation import validate_path_within_repo


@dataclass(frozen=True)
class ManifestEntry:
    """One source and its generated output locations."""

    source: str
    index: str
    detail_dir: str
    detail_ref: str


@dataclass(frozen=True)
class ManifestConfig:
    """Validated manifest entries and their complete output scope."""

    entries: list[ManifestEntry]
    output_root: str


@dataclass(frozen=True)
class ManifestReport:
    """Results from checking every manifest entry."""

    sources_checked: int
    indexes_checked: int
    details_checked: int
    details_found: int
    issues: list[str]


def load_manifest(
    manifest_path: Path,
    repo_root: Path | None = None,
    staged: bool = False,
) -> ManifestConfig:
    """Load and validate the explicit context-output manifest."""
    effective_root = _resolved_repo_root(repo_root)
    resolved_manifest = validate_path_within_repo(manifest_path, effective_root)
    manifest_text = _read_text(resolved_manifest, effective_root, staged)
    if manifest_text is None:
        raise FileNotFoundError(f"Manifest file not found: {manifest_path}")

    data = json.loads(manifest_text)
    if not isinstance(data, dict) or not isinstance(data.get("entries"), list):
        raise ValueError("Manifest must contain an 'entries' array")
    if not data["entries"]:
        raise ValueError("Manifest entries array must not be empty")
    if set(data) - {"entries", "output_root"} or "output_root" not in data:
        raise ValueError("Manifest requires only entries and output_root")

    output_root = _manifest_path_value(data["output_root"], "output_root")
    output_root_path = Path(output_root)
    validate_path_within_repo(output_root_path, effective_root)
    required = ("source", "index", "detail_dir")
    allowed = set(required) | {"detail_ref"}
    entries: list[ManifestEntry] = []
    seen: set[tuple[str, str, str]] = set()
    claimed_paths: list[tuple[str, str, Path]] = []

    for raw_entry in data["entries"]:
        if not isinstance(raw_entry, dict):
            raise ValueError("Each manifest entry must be an object")
        if set(raw_entry) - allowed or not set(required) <= set(raw_entry):
            raise ValueError(
                "Each manifest entry requires only source, index, "
                "detail_dir, and optional detail_ref"
            )
        values = {field: _manifest_path_value(raw_entry.get(field), field) for field in required}
        detail_ref = _manifest_path_value(
            raw_entry.get("detail_ref", values["detail_dir"]),
            "detail_ref",
        )
        if Path(detail_ref) != Path(values["detail_dir"]):
            raise ValueError("Manifest detail_ref must match detail_dir")

        for field, value in values.items():
            path = Path(value)
            validate_path_within_repo(path, effective_root)
            if field != "source" and not path.is_relative_to(output_root_path):
                raise ValueError(f"Manifest {field} must be inside output_root")
            for previous_field, previous_value, previous_path in claimed_paths:
                overlaps = path.is_relative_to(previous_path) or previous_path.is_relative_to(path)
                if overlaps:
                    raise ValueError(
                        f"Manifest path overlap: {field} '{value}' conflicts with "
                        f"{previous_field} '{previous_value}'"
                    )
            claimed_paths.append((field, value, path))

        identity = (values["source"], values["index"], values["detail_dir"])
        if identity in seen:
            raise ValueError(f"Duplicate manifest entry: {values['source']}")
        seen.add(identity)
        entries.append(ManifestEntry(**values, detail_ref=detail_ref))

    return ManifestConfig(entries=entries, output_root=output_root)


def check_manifest(
    manifest_path: Path,
    repo_root: Path | None = None,
    staged: bool = False,
) -> ManifestReport:
    """Check every source and generated output named by the manifest."""
    from context_output_index import _detail_file_contents
    from context_output_parsing import parse_sections

    effective_root = _resolved_repo_root(repo_root)
    manifest = load_manifest(manifest_path, effective_root, staged)
    issues: list[str] = []
    expected_details_count = 0
    found_details_count = 0
    expected_outputs: set[str] = set()
    allowed_detail_files: set[str] = set()

    for entry in manifest.entries:
        source_path = validate_path_within_repo(Path(entry.source), effective_root)
        index_path = validate_path_within_repo(Path(entry.index), effective_root)
        detail_dir = validate_path_within_repo(Path(entry.detail_dir), effective_root)
        expected_outputs.add(_repo_relative_path(index_path, effective_root))
        allowed_detail_files.update(_output_files(detail_dir, effective_root, staged))
        found_details_count += len(_detail_names(detail_dir, effective_root, staged))

        content = _read_text(source_path, effective_root, staged)
        if content is None:
            issues.append(f"Missing source file: {entry.source}")
            continue

        expected_details = _detail_file_contents(parse_sections(content))
        expected_details_count += len(expected_details)
        expected_outputs.update(
            _repo_relative_path(detail_dir / filename, effective_root)
            for filename in expected_details
        )
        entry_issues = check_generated_files(
            content,
            detail_dir,
            index_path,
            entry.detail_ref,
            effective_root,
            staged,
        )
        issues.extend(f"{entry.source}: {issue}" for issue in entry_issues)

    output_root = validate_path_within_repo(Path(manifest.output_root), effective_root)
    actual_outputs = _output_files(output_root, effective_root, staged)
    allowed_outputs = expected_outputs | allowed_detail_files
    issues.extend(
        f"Extra context output: {path}" for path in sorted(actual_outputs - allowed_outputs)
    )

    return ManifestReport(
        sources_checked=len(manifest.entries),
        indexes_checked=len(manifest.entries),
        details_checked=expected_details_count,
        details_found=found_details_count,
        issues=issues,
    )
