"""CLI entry point for memory enhancement tools.

Provides commands for verifying citations in Serena memories.
"""

import argparse
import json
import sys
from pathlib import Path

from .citations import verify_all_memories, verify_memory
from .models import Memory


def format_human_result(result) -> str:
    """Format verification result for human readability.

    Args:
        result: VerificationResult instance

    Returns:
        Formatted string with pass/fail status and details
    """
    if result.valid:
        status = "✅ VALID"
    else:
        status = "❌ STALE"

    confidence_pct = result.confidence * 100
    output = [
        f"{status} - {result.memory_id}",
        f"Confidence: {confidence_pct:.1f}%",
        f"Citations: {result.valid_count}/{result.total_citations} valid",
    ]

    if result.stale_citations:
        output.append("\nStale citations:")
        for citation in result.stale_citations:
            output.append(f"  - {citation.path}:{citation.line or ''}")
            output.append(f"    Reason: {citation.mismatch_reason}")

    return "\n".join(output)


def format_json_result(result) -> dict:
    """Format verification result as JSON-serializable dict.

    Args:
        result: VerificationResult instance

    Returns:
        Dictionary representation
    """
    return {
        "memory_id": result.memory_id,
        "valid": result.valid,
        "confidence": result.confidence,
        "total_citations": result.total_citations,
        "valid_count": result.valid_count,
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


def cmd_verify(args):
    """Verify citations in a single memory.

    Args:
        args: Parsed command-line arguments
    """
    # Try as direct path first
    memory_path = Path(args.memory)
    if not memory_path.exists():
        # Try as memory ID in default directory
        memory_path = Path(".serena/memories") / f"{args.memory}.md"

    if not memory_path.exists():
        print(f"Error: Memory not found: {args.memory}", file=sys.stderr)
        sys.exit(1)

    try:
        memory = Memory.from_serena_file(memory_path)
        result = verify_memory(memory)

        if args.json:
            print(json.dumps(format_json_result(result), indent=2))
        else:
            print(format_human_result(result))

        # Exit with error code if stale
        sys.exit(0 if result.valid else 1)

    except Exception as e:
        print(f"Error verifying memory: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_verify_all(args):
    """Verify citations in all memories.

    Args:
        args: Parsed command-line arguments
    """
    memories_dir = Path(args.dir)
    if not memories_dir.exists():
        print(f"Error: Directory not found: {args.dir}", file=sys.stderr)
        sys.exit(1)

    try:
        results = verify_all_memories(memories_dir)

        if args.json:
            print(json.dumps([format_json_result(r) for r in results], indent=2))
        else:
            # Summary
            total = len(results)
            valid = sum(1 for r in results if r.valid)
            stale = total - valid

            print(f"Verified {total} memories: {valid} valid, {stale} stale\n")

            # List stale memories
            if stale > 0:
                print("Stale memories:")
                for result in results:
                    if not result.valid:
                        print(f"\n{format_human_result(result)}")

        # Exit with error code if any stale
        sys.exit(0 if all(r.valid for r in results) else 1)

    except Exception as e:
        print(f"Error verifying memories: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="memory_enhancement",
        description="Memory enhancement tools for Serena + Forgetful",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Verify command
    verify_parser = subparsers.add_parser("verify", help="Verify citations in a memory")
    verify_parser.add_argument(
        "memory", help="Memory ID or file path (e.g., memory-001 or path/to/memory.md)"
    )
    verify_parser.add_argument("--json", action="store_true", help="Output as JSON")
    verify_parser.set_defaults(func=cmd_verify)

    # Verify-all command
    verify_all_parser = subparsers.add_parser(
        "verify-all", help="Verify citations in all memories"
    )
    verify_all_parser.add_argument(
        "--dir", default=".serena/memories", help="Memory directory (default: .serena/memories)"
    )
    verify_all_parser.add_argument("--json", action="store_true", help="Output as JSON")
    verify_all_parser.set_defaults(func=cmd_verify_all)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
