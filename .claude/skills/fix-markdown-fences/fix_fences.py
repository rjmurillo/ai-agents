#!/usr/bin/env python3
"""Fix malformed markdown code fence closings.

Problem: Closing fences with language identifiers (```python instead of ```)
Solution: Scan markdown files and repair closing fences to plain ```
"""

import re
import sys
from pathlib import Path


def validate_and_resolve_path(path_str: str, allowed_base: Path) -> Path | None:
    """
    Validate that a path string is safe and resolve it against a trusted base directory.
    This prevents directory traversal by ensuring the final path stays within allowed_base.

    Args:
        path_str: Path string provided by the user.
        allowed_base: Base directory that the resolved path must remain within.

    Returns:
        A resolved Path object if the path is safe, or None otherwise.
    """
    # Normalize inputs
    raw = str(path_str)
    base = allowed_base.resolve()

    try:
        # Treat all user input as relative to the trusted base and resolve it.
        # Using strict=False so that existence of the path is not required for validation.
        resolved_path = (base / raw).resolve(strict=False)

        # Ensure the resolved path is contained within the allowed base
        resolved_path.relative_to(base)
        return resolved_path
    except (ValueError, OSError):
        # Any resolution or containment error means the path is unsafe
        return None


def fix_markdown_fences(content: str) -> str:
    """Fix malformed code fence closings in markdown content.
    
    Args:
        content: Raw markdown string
        
    Returns:
        Fixed markdown string
    """
    lines = content.splitlines()
    result: list[str] = []
    in_code_block = False
    block_indent = ""
    
    opening_pattern = re.compile(r'^(\s*)```(\w+)')
    closing_pattern = re.compile(r'^(\s*)```\s*$')
    
    for line in lines:
        opening_match = opening_pattern.match(line)
        closing_match = closing_pattern.match(line)
        
        if opening_match:
            if in_code_block:
                # Malformed: closing fence has language identifier
                # Insert proper closing fence before this line
                result.append(f"{block_indent}```")
            # Start new block
            result.append(line)
            block_indent = opening_match.group(1)
            in_code_block = True
        elif closing_match:
            result.append(line)
            in_code_block = False
            block_indent = ""
        else:
            result.append(line)
    
    # Handle file ending inside code block
    if in_code_block:
        result.append(f"{block_indent}```")
    
    return '\n'.join(result)


def fix_markdown_files(
    directory: Path,
    pattern: str = "**/*.md",
    dry_run: bool = False
) -> list[str]:
    """Fix all markdown files in directory.

    Args:
        directory: Root directory to scan
        pattern: Glob pattern for markdown files
        dry_run: If True, report changes without writing

    Returns:
        List of fixed file paths
    """
    # SECURITY: Validate directory is safe before globbing (prevents CWE-22)
    if not validate_path_safety(str(directory), allowed_base=Path.cwd()):
        raise ValueError(f"Invalid directory: {directory} contains unsafe characters or is outside allowed directory")

    fixed: list[str] = []

    for file_path in directory.glob(pattern):
        content = file_path.read_text(encoding='utf-8')
        fixed_content = fix_markdown_fences(content)
        
        if content != fixed_content:
            if not dry_run:
                file_path.write_text(fixed_content, encoding='utf-8')
            fixed.append(str(file_path))
    
    return fixed


def main() -> int:
    """CLI entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Fix malformed markdown code fence closings'
    )
    parser.add_argument(
        'directories',
        nargs='+',
        help='Directories to scan for markdown files'
    )
    parser.add_argument(
        '--pattern',
        default='**/*.md',
        help='Glob pattern for markdown files (default: **/*.md)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Report changes without writing files'
    )
    
    args = parser.parse_args()

    total_fixed = 0
    for dir_path in args.directories:
        # SECURITY: Validate path safety and resolve to trusted path (prevents CWE-22)
        directory = validate_and_resolve_path(dir_path, allowed_base=Path.cwd())
        if directory is None:
            print(f"Error: {dir_path} contains unsafe characters or is outside allowed directory", file=sys.stderr)
            continue

        if not directory.exists():
            print(f"Warning: {dir_path} does not exist", file=sys.stderr)
            continue
            
        fixed = fix_markdown_files(directory, args.pattern, args.dry_run)
        for f in fixed:
            prefix = "[dry-run] " if args.dry_run else ""
            print(f"{prefix}Fixed: {f}")
        total_fixed += len(fixed)
    
    if total_fixed == 0:
        print("No files needed fixing")
    else:
        action = "would fix" if args.dry_run else "fixed"
        print(f"\nTotal: {action} {total_fixed} file(s)")
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
