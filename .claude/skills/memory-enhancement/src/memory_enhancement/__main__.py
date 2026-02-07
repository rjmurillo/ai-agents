"""CLI entry point for memory enhancement.

Usage:
    python -m memory_enhancement verify <memory-id-or-path> [--json] [--repo-root PATH]
    python -m memory_enhancement verify-all [--dir PATH] [--json] [--repo-root PATH]
"""

import argparse
import json
import sys
from pathlib import Path

from .citations import VerificationResult, verify_all_memories, verify_memory
from .models import Memory

DEFAULT_MEMORIES_DIR = ".serena/memories"


def _find_memory(memory_id: str, memories_dir: Path) -> Path:
    """Resolve a memory ID or path to a file path.

    Tries: literal path, then {memory_id}.md in memories_dir,
    then bare filename in memories_dir.

    Raises FileNotFoundError if not found.
    """
    candidate = Path(memory_id)
    if candidate.exists():
        return candidate

    candidate = memories_dir / f"{memory_id}.md"
    if candidate.exists():
        return candidate

    candidate = memories_dir / memory_id
    if candidate.exists():
        return candidate

    msg = (
        f"Memory not found: {memory_id}. "
        f"Searched: {memory_id}, {memories_dir / f'{memory_id}.md'}"
    )
    raise FileNotFoundError(msg)


def _result_to_dict(result: VerificationResult) -> dict:
    """Convert a VerificationResult to a JSON-serializable dict."""
    return {
        "memory_id": result.memory_id,
        "valid": result.valid,
        "total_citations": result.total_citations,
        "valid_count": result.valid_count,
        "confidence": round(result.confidence, 2),
        "stale_citations": [
            {
                "path": c.path,
                "line": c.line,
                "snippet": c.snippet,
                "mismatch_reason": c.mismatch_reason,
            }
            for c in result.stale_citations
        ],
    }


def _print_result(result: VerificationResult) -> None:
    """Print a human-readable verification result."""
    status = "VALID" if result.valid else "STALE"
    icon = "[PASS]" if result.valid else "[FAIL]"
    print(f"{icon} {result.memory_id}: {status}")
    print(f"  Citations: {result.valid_count}/{result.total_citations} valid")
    print(f"  Confidence: {result.confidence:.2f}")

    for citation in result.stale_citations:
        loc = citation.path
        if citation.line is not None:
            loc += f":{citation.line}"
        print(f"  [STALE] {loc}")
        print(f"    Reason: {citation.mismatch_reason}")


def cmd_verify(args: argparse.Namespace) -> int:
    """Verify citations in a single memory."""
    import yaml

    memories_dir = Path(args.dir)
    repo_root = Path(args.repo_root)

    try:
        memory_path = _find_memory(args.memory_id, memories_dir)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2

    try:
        memory = Memory.from_file(memory_path)
    except (yaml.YAMLError, UnicodeDecodeError, OSError) as e:
        print(f"Error: Cannot parse {memory_path}: {e}", file=sys.stderr)
        return 2

    if not memory.citations:
        if args.json:
            print(json.dumps({"memory_id": memory.id, "valid": True, "total_citations": 0}))
        else:
            print(f"[PASS] {memory.id}: No citations to verify")
        return 0

    result = verify_memory(memory, repo_root)

    if args.json:
        print(json.dumps(_result_to_dict(result), indent=2))
    else:
        _print_result(result)

    return 0 if result.valid else 1


def cmd_verify_all(args: argparse.Namespace) -> int:
    """Verify citations in all memories."""
    memories_dir = Path(args.dir)
    repo_root = Path(args.repo_root)

    if not memories_dir.exists():
        print(f"Error: Memories directory not found: {memories_dir}", file=sys.stderr)
        return 2

    results = verify_all_memories(memories_dir, repo_root)

    if args.json:
        print(json.dumps([_result_to_dict(r) for r in results], indent=2))
    else:
        if not results:
            print("No memories with citations found.")
            return 0

        stale_count = sum(1 for r in results if not r.valid)
        total = len(results)

        for result in results:
            _print_result(result)
            print()

        print(f"Summary: {total - stale_count}/{total} memories valid")
        if stale_count > 0:
            print(f"  {stale_count} memory/memories have stale citations")

    has_stale = any(not r.valid for r in results)
    return 1 if has_stale else 0


def main() -> int:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="memory_enhancement",
        description="Memory citation verification and enhancement",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Common arguments added to each subparser so they can appear after the subcommand
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--repo-root",
        default=".",
        help="Repository root directory (default: current directory)",
    )
    common.add_argument("--json", action="store_true", help="JSON output")
    common.add_argument(
        "--dir", default=DEFAULT_MEMORIES_DIR, help="Memories directory"
    )

    verify_parser = subparsers.add_parser(
        "verify", help="Verify a single memory", parents=[common]
    )
    verify_parser.add_argument("memory_id", help="Memory ID or file path")

    subparsers.add_parser(
        "verify-all", help="Verify all memories", parents=[common]
    )

    args = parser.parse_args()

    if args.command == "verify":
        return cmd_verify(args)
    elif args.command == "verify-all":
        return cmd_verify_all(args)

    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
