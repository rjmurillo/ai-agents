#!/usr/bin/env python3
"""
Compress markdown documentation to minimal tokens using pipe-delimited format (Vercel pattern).

Implements compression techniques from Vercel research achieving 60-80% token reduction
while maintaining 100% information density. Uses tiktoken for accurate OpenAI-compatible
token counting.

Exit Codes:
    0: Success - Compression completed
    1: Error - Input file not found
    2: Error - Invalid compression level
    3: Error - Output file write failure
    4: Error - tiktoken not installed

See: ADR-035 Exit Code Standardization

References:
    - Vercel Research: .agents/analysis/vercel-passive-context-vs-skills-research.md
    - Example: SKILL-QUICK-REF.md (pipe-delimited format)
    - Issue: #1108
"""

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path

try:
    import tiktoken
except ImportError:
    print("Error: tiktoken library not installed. Run: pip install tiktoken", file=sys.stderr)
    sys.exit(4)


class CompressionLevel(Enum):
    """Compression level options."""
    LIGHT = "light"
    MEDIUM = "medium"
    AGGRESSIVE = "aggressive"


@dataclass
class CompressionMetrics:
    """Compression metrics output."""
    original_tokens: int
    compressed_tokens: int
    reduction_percent: float
    original_size: int
    compressed_size: int
    compression_level: str


@dataclass
class CompressionResult:
    """Compression operation result."""
    success: bool
    compressed_content: str
    metrics: CompressionMetrics
    index_file: str | None = None


# Abbreviation dictionary
ABBREVIATIONS = {
    'configuration': 'config',
    'repository': 'repo',
    'documentation': 'docs',
    'implementation': 'impl',
    'environment': 'env',
    'authentication': 'auth',
    'authorization': 'authz',
    'parameter': 'param',
    'reference': 'ref',
    'application': 'app',
    'information': 'info',
    'description': 'desc',
    'specification': 'spec',
    'administrator': 'admin',
    'development': 'dev',
    'production': 'prod',
    'directory': 'dir',
    'command': 'cmd',
}


def count_tokens(text: str) -> int:
    """
    Count tokens using tiktoken (OpenAI's tokenizer).

    Args:
        text: Text to tokenize

    Returns:
        Token count
    """
    encoding = tiktoken.get_encoding("cl100k_base")  # GPT-4 encoding
    return len(encoding.encode(text))


def preserve_code_blocks(content: str) -> tuple[str, list[str]]:
    """
    Extract code blocks for preservation during compression.

    Args:
        content: Markdown content

    Returns:
        Tuple of (content with placeholders, list of code blocks)
    """
    code_blocks = []
    placeholder_template = "___CODE_BLOCK_{}___ "

    def replace_code_block(match):
        block = match.group(0)
        code_blocks.append(block)
        return placeholder_template.format(len(code_blocks) - 1)

    # Match code fences (triple backticks)
    pattern = r'```[\s\S]*?```'
    processed = re.sub(pattern, replace_code_block, content)

    return processed, code_blocks


def restore_code_blocks(content: str, code_blocks: list[str]) -> str:
    """
    Restore preserved code blocks.

    Args:
        content: Content with placeholders
        code_blocks: List of original code blocks

    Returns:
        Content with code blocks restored
    """
    result = content
    for i, block in enumerate(code_blocks):
        placeholder = f"___CODE_BLOCK_{i}___"
        result = result.replace(placeholder, block)

    return result


def compress_headers(content: str, level: CompressionLevel) -> str:
    """
    Compress markdown headers to compact format.

    Args:
        content: Markdown content
        level: Compression level

    Returns:
        Content with compressed headers
    """
    # H2 headers: ## Title -> [Title]
    result = re.sub(r'^## (.+)$', r'[\1]', content, flags=re.MULTILINE)

    # H3 headers in aggressive mode: ### Title -> |Title:
    if level == CompressionLevel.AGGRESSIVE:
        result = re.sub(r'^### (.+)$', r'|\1:', result, flags=re.MULTILINE)

    return result


def compress_tables(content: str, level: CompressionLevel) -> str:
    """
    Convert markdown tables to pipe-delimited format.

    Args:
        content: Markdown content
        level: Compression level

    Returns:
        Content with compressed tables
    """
    lines = content.split('\n')
    result = []
    in_table = False
    headers = []

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        # Detect table start
        if line.startswith('|') and not in_table:
            # Check if next line is separator
            if i + 1 < len(lines) and re.match(r'^\|[-:\s|]+\|$', lines[i + 1].strip()):
                in_table = True
                # Extract headers
                headers = [h.strip() for h in line.split('|') if h.strip()]
                i += 2  # Skip header and separator
                continue

        # Process table row
        if in_table and line.startswith('|'):
            cells = [c.strip() for c in line.split('|') if c.strip()]
            pairs = []

            for header, cell in zip(headers, cells, strict=False):
                # Skip empty cells in aggressive mode
                if level == CompressionLevel.AGGRESSIVE and not cell:
                    continue

                if cell:
                    pairs.append(f"{header}: {cell}")

            if pairs:
                result.append('|' + ' |'.join(pairs))
            i += 1
        elif in_table:
            # End of table
            in_table = False
            headers = []
            result.append(line)
            i += 1
        else:
            result.append(line)
            i += 1

    return '\n'.join(result)


def compress_lists(content: str, level: CompressionLevel) -> str:
    """
    Compress bullet lists to pipe-delimited format.

    Args:
        content: Markdown content
        level: Compression level

    Returns:
        Content with compressed lists
    """
    if level != CompressionLevel.AGGRESSIVE:
        return content

    # Convert bullet lists: - Item -> |Item
    result = re.sub(r'^[\*\-]\s+(.+)$', r'|\1', content, flags=re.MULTILINE)

    return result


def remove_redundant_words(content: str, level: CompressionLevel) -> str:
    """
    Remove redundant words while preserving meaning.

    Args:
        content: Markdown content
        level: Compression level

    Returns:
        Content with redundant words removed
    """
    if level == CompressionLevel.LIGHT:
        return content

    result = content

    # Common phrase compressions (apply first)
    phrase_replacements = [
        (r'\bin order to\b', 'to'),
        (r'\bdue to the fact that\b', 'because'),
        (r'\bfor the purpose of\b', 'for'),
        (r'\bin the event that\b', 'if'),
        (r'\bat the present time\b', 'now'),
        (r'\bat this point in time\b', 'now'),
        (r'\bmake sure to\b', 'ensure'),
        (r'\bin spite of\b', 'despite'),
        (r'\bby means of\b', 'via'),
        (r'\bprior to\b', 'before'),
        (r'\bsubsequent to\b', 'after'),
    ]

    for pattern, replacement in phrase_replacements:
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)

    # Aggressive word removal
    # Remove articles and common verbs more aggressively
    if level == CompressionLevel.MEDIUM or level == CompressionLevel.AGGRESSIVE:
        # Remove articles (the, a, an) - more aggressive
        result = re.sub(r'\bthe\s+', '', result, flags=re.IGNORECASE)
        result = re.sub(r'\ba\s+', '', result, flags=re.IGNORECASE)
        result = re.sub(r'\ban\s+', '', result, flags=re.IGNORECASE)

        # Remove "to be" forms
        result = re.sub(r'\bis\s+', '', result, flags=re.IGNORECASE)
        result = re.sub(r'\bare\s+', '', result, flags=re.IGNORECASE)
        result = re.sub(r'\bwas\s+', '', result, flags=re.IGNORECASE)
        result = re.sub(r'\bwere\s+', '', result, flags=re.IGNORECASE)

    if level == CompressionLevel.AGGRESSIVE:
        # Additional aggressive removals
        result = re.sub(r'\bthis\s+', '', result, flags=re.IGNORECASE)
        result = re.sub(r'\bthat\s+', '', result, flags=re.IGNORECASE)
        result = re.sub(r'\bthese\s+', '', result, flags=re.IGNORECASE)
        result = re.sub(r'\bthose\s+', '', result, flags=re.IGNORECASE)
        result = re.sub(r'\bwill\s+', '', result, flags=re.IGNORECASE)
        result = re.sub(r'\bshall\s+', '', result, flags=re.IGNORECASE)
        result = re.sub(r'\bmust\s+', '', result, flags=re.IGNORECASE)
        result = re.sub(r'\bshould\s+', '', result, flags=re.IGNORECASE)
        result = re.sub(r'\bcan\s+', '', result, flags=re.IGNORECASE)

    return result


def apply_abbreviations(content: str) -> str:
    """
    Apply common term abbreviations.

    Args:
        content: Markdown content

    Returns:
        Content with abbreviations applied
    """
    result = content

    for term, abbrev in ABBREVIATIONS.items():
        pattern = f'\\b{term}\\b'
        result = re.sub(pattern, abbrev, result, flags=re.IGNORECASE)

    return result


def collapse_whitespace(content: str, level: CompressionLevel) -> str:
    """
    Collapse excessive whitespace.

    Args:
        content: Markdown content
        level: Compression level

    Returns:
        Content with collapsed whitespace
    """
    # Collapse multiple spaces to single space
    result = re.sub(r' {2,}', ' ', content)

    # Trim trailing whitespace from lines
    result = re.sub(r' +$', '', result, flags=re.MULTILINE)

    # Collapse newlines based on level
    if level == CompressionLevel.LIGHT:
        # Keep double newlines (paragraphs), collapse 3+
        result = re.sub(r'\n{3,}', '\n\n', result)
    elif level == CompressionLevel.MEDIUM:
        # Keep single newlines, collapse 3+
        result = re.sub(r'\n{3,}', '\n', result)
    else:  # AGGRESSIVE
        # Collapse all multiple newlines to single
        result = re.sub(r'\n{2,}', '\n', result)

    return result


def compress_markdown(content: str, level: CompressionLevel) -> str:
    """
    Apply all compression techniques.

    Args:
        content: Original markdown content
        level: Compression level

    Returns:
        Compressed content
    """
    # Phase 0: Preserve code blocks
    compressed, code_blocks = preserve_code_blocks(content)

    # Phase 1: Compress headers
    compressed = compress_headers(compressed, level)

    # Phase 2: Compress tables
    compressed = compress_tables(compressed, level)

    # Phase 3: Compress lists
    compressed = compress_lists(compressed, level)

    # Phase 4: Remove redundant words
    compressed = remove_redundant_words(compressed, level)

    # Phase 5: Apply abbreviations (aggressive only)
    if level == CompressionLevel.AGGRESSIVE:
        compressed = apply_abbreviations(compressed)

    # Phase 6: Collapse whitespace
    compressed = collapse_whitespace(compressed, level)

    # Phase 7: Restore code blocks
    compressed = restore_code_blocks(compressed, code_blocks)

    return compressed


def build_metrics(original: str, compressed: str, level: CompressionLevel) -> CompressionMetrics:
    """
    Build compression metrics.

    Args:
        original: Original content
        compressed: Compressed content
        level: Compression level

    Returns:
        Compression metrics
    """
    original_tokens = count_tokens(original)
    compressed_tokens = count_tokens(compressed)

    reduction_percent = 0.0
    if original_tokens > 0:
        reduction_percent = round((1 - (compressed_tokens / original_tokens)) * 100, 1)

    return CompressionMetrics(
        original_tokens=original_tokens,
        compressed_tokens=compressed_tokens,
        reduction_percent=reduction_percent,
        original_size=len(original),
        compressed_size=len(compressed),
        compression_level=level.value
    )


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Compress markdown documentation to minimal tokens using pipe-delimited format',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument(
        '-i', '--input',
        required=True,
        type=Path,
        help='Input markdown file path'
    )

    parser.add_argument(
        '-l', '--level',
        type=str,
        choices=['light', 'medium', 'aggressive'],
        default='medium',
        help='Compression level (default: medium)'
    )

    parser.add_argument(
        '-o', '--output',
        type=Path,
        help='Output file path (default: stdout as JSON)'
    )

    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Verbose output'
    )

    args = parser.parse_args()

    # Validate input file
    if not args.input.exists():
        print(f"Error: Input file not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    # Parse compression level
    level = CompressionLevel(args.level.lower())

    # Read input
    try:
        # Prevent path traversal (CWE-22): check for ../ sequences
        if ".." in str(args.input):
            raise PermissionError(f"Path traversal attempt detected on input path: {args.input}")
        content = args.input.read_text(encoding='utf-8')
    except Exception as e:
        print(f"Error reading input file: {e}", file=sys.stderr)
        sys.exit(1)

    # Compress
    if args.verbose:
        print(f"Compressing with level: {level.value}", file=sys.stderr)

    compressed = compress_markdown(content, level)

    # Build metrics
    metrics = build_metrics(content, compressed, level)

    # Build result
    result = CompressionResult(
        success=True,
        compressed_content=compressed,
        metrics=metrics
    )

    # Output
    if args.output:
        try:
            # Prevent path traversal (CWE-22): check for ../ sequences
            if ".." in str(args.output):
                raise PermissionError(
                    f"Path traversal attempt detected on output: {args.output}"
                )

            args.output.write_text(compressed, encoding='utf-8')
            if args.verbose:
                print(f"Compressed content written to: {args.output}", file=sys.stderr)
                print(f"Metrics: {metrics.original_tokens} → {metrics.compressed_tokens} tokens "
                      f"({metrics.reduction_percent}% reduction)", file=sys.stderr)
        except Exception as e:
            print(f"Error writing output file: {e}", file=sys.stderr)
            sys.exit(3)
    else:
        # Output JSON to stdout
        output_dict = asdict(result)
        print(json.dumps(output_dict, indent=2))

    sys.exit(0)


if __name__ == '__main__':
    main()
