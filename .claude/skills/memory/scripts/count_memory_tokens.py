#!/usr/bin/env python3
"""
Count tokens in Serena memory files using OpenAI's tiktoken.

Uses cl100k_base encoding (GPT-4/Claude). Caches results for performance.
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

try:
    import tiktoken
except ImportError:
    print("Error: tiktoken not installed. Run: pip install tiktoken", file=sys.stderr)
    sys.exit(1)


def get_file_hash(file_path: Path) -> str:
    """Compute SHA-256 hash of file for cache invalidation."""
    return hashlib.sha256(file_path.read_bytes()).hexdigest()


def load_cache(cache_path: Path) -> dict[str, Any]:
    """Load token count cache from JSON."""
    if not cache_path.exists():
        return {}
    try:
        cache_data: dict[str, Any] = json.loads(cache_path.read_text())
        return cache_data
    except (json.JSONDecodeError, OSError):
        return {}


def save_cache(cache_path: Path, cache: dict[str, dict]) -> None:
    """Save token count cache to JSON."""
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache, indent=2))


def count_tokens(text: str, encoding_name: str = "cl100k_base") -> int:
    """Count tokens using tiktoken encoding."""
    encoding = tiktoken.get_encoding(encoding_name)
    return len(encoding.encode(text))


def get_memory_token_count(
    memory_path: Path,
    cache_path: Path | None = None,
    force: bool = False
) -> int:
    """
    Count tokens in memory file with caching.

    Args:
        memory_path: Path to memory markdown file
        cache_path: Path to cache JSON file (default: .serena/.token-cache.json)
        force: Force recount even if cached

    Returns:
        Token count for the file
    """
    if not memory_path.exists():
        raise FileNotFoundError(f"Memory file not found: {memory_path}")

    # Default cache location
    if cache_path is None:
        cache_path = memory_path.parent.parent / ".token-cache.json"

    # Load cache
    cache = load_cache(cache_path)

    # Check cache
    file_key = str(memory_path)
    file_hash = get_file_hash(memory_path)

    if not force and file_key in cache:
        cached_entry = cache[file_key]
        if isinstance(cached_entry, dict) and cached_entry.get("hash") == file_hash:
            # Cache hit
            token_count_value: int = cached_entry["token_count"]
            return token_count_value

    # Cache miss or force recount
    content = memory_path.read_text(encoding="utf-8")
    token_count = count_tokens(content)

    # Update cache
    cache[file_key] = {
        "hash": file_hash,
        "token_count": token_count,
        "file_size": memory_path.stat().st_size
    }
    save_cache(cache_path, cache)

    return token_count


def count_directory(
    directory: Path,
    pattern: str = "*.md",
    cache_path: Path | None = None,
    force: bool = False
) -> dict[str, int]:
    """
    Count tokens for all memory files in directory.

    Args:
        directory: Directory containing memory files
        pattern: Glob pattern for files (default: *.md)
        cache_path: Path to cache JSON file
        force: Force recount even if cached

    Returns:
        Dictionary mapping file paths to token counts
    """
    if not directory.exists():
        raise FileNotFoundError(f"Directory not found: {directory}")

    results = {}
    for file_path in sorted(directory.glob(pattern)):
        if file_path.is_file():
            try:
                results[str(file_path)] = get_memory_token_count(
                    file_path, cache_path, force
                )
            except Exception as e:
                print(f"Warning: Failed to count {file_path}: {e}", file=sys.stderr)

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Count tokens in Serena memory files using tiktoken"
    )
    parser.add_argument(
        "path",
        type=Path,
        help="Memory file or directory to analyze"
    )
    parser.add_argument(
        "-r", "--recurse",
        action="store_true",
        help="Recursively process directory"
    )
    parser.add_argument(
        "-c", "--cache",
        type=Path,
        default=None,
        help="Cache file path (default: .serena/.token-cache.json)"
    )
    parser.add_argument(
        "-f", "--force",
        action="store_true",
        help="Force recount, ignore cache"
    )
    parser.add_argument(
        "--pattern",
        type=str,
        default="*.md",
        help="File pattern for directory mode (default: *.md)"
    )
    parser.add_argument(
        "--total",
        action="store_true",
        help="Show total token count for directory"
    )

    args = parser.parse_args()

    try:
        if args.path.is_file():
            # Single file mode
            count = get_memory_token_count(args.path, args.cache, args.force)
            print(f"{args.path}: {count:,} tokens")
        elif args.path.is_dir():
            # Directory mode
            pattern = f"**/{args.pattern}" if args.recurse else args.pattern
            results = count_directory(args.path, pattern, args.cache, args.force)

            if not results:
                print(f"No files matching '{pattern}' in {args.path}", file=sys.stderr)
                sys.exit(1)

            # Print results
            total = 0
            for file_path, count in results.items():
                print(f"{file_path}: {count:,} tokens")
                total += count

            if args.total or len(results) > 1:
                print(f"\nTotal: {total:,} tokens across {len(results)} files")
        else:
            print(f"Error: Path not found: {args.path}", file=sys.stderr)
            sys.exit(1)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
