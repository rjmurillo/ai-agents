#!/usr/bin/env python3
"""Extract markdown sections into separate files and generate a pipe-delimited index.

Implements the Vercel extract-and-index pattern for 60-80% token reduction.
Parses markdown into sections by heading, writes each section to a detail file,
and produces a compact index with references to those files.

Exit Codes:
    0: Success
    1: Error - Input file not found or read failure
    2: Error - Invalid arguments
    3: Error - Output write failure
    4: Error - tiktoken not installed

See: ADR-035 Exit Code Standardization

References:
    - Vercel Research: .agents/analysis/vercel-passive-context-vs-skills-research.md
    - Issue: #1109
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from path_validation import validate_path_within_repo

try:
    import tiktoken
except ImportError:
    print(
        "Error: tiktoken library not installed.\n"
        "Install with: uv pip install -e '.[dev]' (from repository root)\n"
        "Or: pip install tiktoken",
        file=sys.stderr,
    )
    sys.exit(4)


@dataclass
class Section:
    """A parsed markdown section."""

    heading: str
    level: int
    content: str
    slug: str


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
    encoding = tiktoken.get_encoding("cl100k_base")
    return len(encoding.encode(text))


def slugify(heading: str) -> str:
    """Convert a heading to a filesystem-safe slug.

    Args:
        heading: The heading text.

    Returns:
        A lowercase, hyphenated slug safe for filenames.
    """
    slug = heading.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = slug.strip("-")
    return slug or "untitled"


def parse_sections(content: str) -> list[Section]:
    """Parse markdown content into sections split by headings.

    Splits on H1 and H2 headings. Content before the first heading
    becomes a section with heading "preamble".

    Args:
        content: Raw markdown text.

    Returns:
        List of Section objects.
    """
    lines = content.split("\n")
    sections: list[Section] = []
    current_heading = "preamble"
    current_level = 0
    current_lines: list[str] = []

    for line in lines:
        match = re.match(r"^(#{1,2})\s+(.+)$", line)
        if match:
            # Flush previous section
            body = "\n".join(current_lines).strip()
            if body or current_heading != "preamble":
                sections.append(
                    Section(
                        heading=current_heading,
                        level=current_level,
                        content=body,
                        slug=slugify(current_heading),
                    )
                )
            current_heading = match.group(2).strip()
            current_level = len(match.group(1))
            current_lines = []
        else:
            current_lines.append(line)

    # Flush last section
    body = "\n".join(current_lines).strip()
    if body or current_heading != "preamble":
        sections.append(
            Section(
                heading=current_heading,
                level=current_level,
                content=body,
                slug=slugify(current_heading),
            )
        )

    return sections


def summarize_section(section: Section) -> str:
    """Produce a one-line summary of a section for the index.

    Extracts the first non-empty, non-heading line as a brief description.
    Falls back to "(see detail file)" when content is only code or tables.

    Args:
        section: The section to summarize.

    Returns:
        A short summary string.
    """
    in_code_block = False
    for line in section.content.split("\n"):
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            continue
        if not stripped:
            continue
        # Skip table separators and short markers
        if re.match(r"^[\-|#>]", stripped) and len(stripped) < 4:
            continue
        if re.match(r"^\|[-:\s|]+\|$", stripped):
            continue
        # Use first meaningful line, truncated
        summary = stripped.lstrip("-*> ").rstrip()
        if len(summary) > 80:
            summary = summary[:77] + "..."
        return summary
    return "(see detail file)"


def build_index(sections: list[Section], detail_dir: str) -> str:
    """Build a pipe-delimited index referencing detail files.

    Format follows the Vercel pattern:
        [Heading]
        |summary (see: detail_dir/slug.md)

    Args:
        sections: Parsed sections.
        detail_dir: Relative path to the detail files directory.

    Returns:
        The index content as a string.
    """
    lines: list[str] = []
    for section in sections:
        if section.heading == "preamble" and not section.content:
            continue
        heading_display = section.heading
        if section.heading == "preamble":
            heading_display = "Overview"
        lines.append(f"[{heading_display}]")
        summary = summarize_section(section)
        detail_path = f"{detail_dir}/{section.slug}.md"
        lines.append(f"|{summary} (see: {detail_path})")
    return "\n".join(lines)


def write_detail_files(
    sections: list[Section],
    detail_dir: Path,
    repo_root: Path | None = None,
) -> int:
    """Write each section to a separate detail file.

    Args:
        sections: Parsed sections.
        detail_dir: Directory to write detail files into.
        repo_root: Repository root for path validation. Auto-detected if None.

    Returns:
        Number of files written.

    Raises:
        PermissionError: If detail_dir resolves outside the repo root.
    """
    validated_dir = validate_path_within_repo(detail_dir, repo_root)
    validated_dir.mkdir(parents=True, exist_ok=True)

    written = 0
    seen_slugs: dict[str, int] = {}
    for section in sections:
        slug = section.slug
        if slug in seen_slugs:
            seen_slugs[slug] += 1
            slug = f"{slug}-{seen_slugs[slug]}"
        else:
            seen_slugs[slug] = 0

        file_path = validated_dir / f"{slug}.md"
        heading_prefix = "#" * max(section.level, 1)
        file_content = f"{heading_prefix} {section.heading}\n\n{section.content}\n"
        file_path.write_text(file_content, encoding="utf-8")
        written += 1

    return written


def extract_and_index(
    content: str,
    detail_dir: Path,
    detail_dir_ref: str,
    repo_root: Path | None = None,
) -> ExtractionResult:
    """Run the full extract-and-index pipeline.

    Args:
        content: Raw markdown text.
        detail_dir: Filesystem path to write detail files.
        detail_dir_ref: Relative path string used in index references.
        repo_root: Repository root for path validation.

    Returns:
        ExtractionResult with index content and metrics.
    """
    sections = parse_sections(content)
    files_written = write_detail_files(sections, detail_dir, repo_root)
    index_content = build_index(sections, detail_dir_ref)

    original_tokens = count_tokens(content)
    index_tokens = count_tokens(index_content)
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


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Extract markdown sections and generate a pipe-delimited index",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "-i",
        "--input",
        required=True,
        type=Path,
        help="Input markdown file path",
    )

    parser.add_argument(
        "-d",
        "--detail-dir",
        required=True,
        type=Path,
        help="Directory for extracted detail files",
    )

    parser.add_argument(
        "-r",
        "--detail-ref",
        type=str,
        default=None,
        help="Relative path for index references (default: same as --detail-dir)",
    )

    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Output index file path (default: stdout as JSON)",
    )

    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Verbose output",
    )

    args = parser.parse_args()

    if not args.input.exists():
        print(f"Error: Input file not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    detail_ref = args.detail_ref or str(args.detail_dir)

    try:
        resolved_input = validate_path_within_repo(args.input)
        content = resolved_input.read_text(encoding="utf-8")
    except Exception as e:
        print(f"Error reading input file: {e}", file=sys.stderr)
        sys.exit(1)

    if args.verbose:
        print(f"Extracting sections from: {args.input}", file=sys.stderr)

    result = extract_and_index(content, args.detail_dir, detail_ref)

    if args.output:
        try:
            resolved_output = validate_path_within_repo(args.output)
            resolved_output.write_text(result.index_content, encoding="utf-8")
            if args.verbose:
                print(
                    f"Index written to: {args.output}\n"
                    f"Metrics: {result.metrics.original_tokens} -> "
                    f"{result.metrics.index_tokens} tokens "
                    f"({result.metrics.reduction_percent}% reduction)",
                    file=sys.stderr,
                )
        except PermissionError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(3)
        except Exception as e:
            print(f"Error writing output file: {e}", file=sys.stderr)
            sys.exit(3)
    else:
        output_dict = asdict(result)
        print(json.dumps(output_dict, indent=2))

    sys.exit(0)


if __name__ == "__main__":
    main()
