#!/usr/bin/env python3
# taste-lint: ignore file-size
"""Extract markdown sections into separate files and generate a pipe-delimited index.

Implements the Vercel extract-and-index pattern for 60-80% token reduction.
Parses markdown into sections by heading, writes each section to a detail file,
and produces a compact index with references to those files.

Exit Codes:
    0: Success
    1: Error - Input failure or generated-output drift
    2: Error - Invalid arguments or manifest configuration
    3: Error - Path, Git index, or output access failure
    4: Error - tiktoken not installed

See: ADR-035 Exit Code Standardization

References:
    - Vercel Research: .agents/analysis/vercel-passive-context-vs-skills-research.md
    - Issue: #1109
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from context_output_index import _detail_file_contents, build_index, summarize_section
from context_output_manifest import check_generated_files, check_manifest
from context_output_parsing import Section, parse_sections, slugify
from path_validation import validate_path_within_repo

__all__ = (
    "Section",
    "ExtractionMetrics",
    "ExtractionResult",
    "count_tokens",
    "slugify",
    "parse_sections",
    "summarize_section",
    "build_index",
    "write_detail_files",
    "check_generated_files",
    "check_manifest",
    "extract_and_index",
)


@dataclass
class ExtractionMetrics:
    """Metrics for the extraction operation."""

    original_tokens: int
    index_tokens: int
    reduction_percent: float
    sections_extracted: int
    detail_files_written: int


@dataclass
class ExtractionResult:
    """Result of the extract-and-index operation."""

    success: bool
    index_content: str
    metrics: ExtractionMetrics
    detail_dir: str


def count_tokens(text: str) -> int:
    """Count tokens using tiktoken (cl100k_base encoding)."""
    try:
        import tiktoken
    except ImportError as error:
        raise RuntimeError(
            "tiktoken library not installed. Install with: uv pip install -e '.[dev]'"
        ) from error
    encoding = tiktoken.get_encoding("cl100k_base")
    return len(encoding.encode(text))


def write_detail_files(
    sections: list[Section],
    detail_dir: Path,
    repo_root: Path | None = None,
) -> int:
    """Write each section to a separate detail file."""
    validated_dir = validate_path_within_repo(detail_dir, repo_root)
    validated_dir.mkdir(parents=True, exist_ok=True)

    detail_files = _detail_file_contents(sections)
    for filename, file_content in detail_files.items():
        file_path = validated_dir / filename
        file_path.write_text(file_content, encoding="utf-8")
    return len(detail_files)


def extract_and_index(
    content: str,
    detail_dir: Path,
    detail_dir_ref: str,
    repo_root: Path | None = None,
) -> ExtractionResult:
    """Run the full extract-and-index pipeline."""
    sections = parse_sections(content)
    index_content = build_index(sections, detail_dir_ref)

    original_tokens = count_tokens(content)
    index_tokens = count_tokens(index_content)
    files_written = write_detail_files(sections, detail_dir, repo_root)
    reduction = 0.0
    if original_tokens > 0:
        reduction = round((1 - (index_tokens / original_tokens)) * 100, 1)

    metrics = ExtractionMetrics(
        original_tokens=original_tokens,
        index_tokens=index_tokens,
        reduction_percent=reduction,
        sections_extracted=len(sections),
        detail_files_written=files_written,
    )

    return ExtractionResult(
        success=True,
        index_content=index_content,
        metrics=metrics,
        detail_dir=str(detail_dir),
    )


if __name__ == "__main__":
    from context_output_cli import main as run_cli

    run_cli(sys.modules[__name__])
