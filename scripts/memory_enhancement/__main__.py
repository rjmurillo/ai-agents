"""CLI entry point for memory enhancement layer.

Usage:
    python -m memory_enhancement verify <memory-id-or-path>
    python -m memory_enhancement verify-all [--dir .serena/memories]
"""

import argparse
import json
import sys
from pathlib import Path

from .citations import verify_memory, verify_all_memories
from .models import Memory


def main():
    parser = argparse.ArgumentParser(description="Memory Enhancement Layer CLI")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # verify command
    verify_parser = subparsers.add_parser("verify", help="Verify a single memory")
    verify_parser.add_argument("memory", help="Memory ID or file path")

    # verify-all command
    verify_all_parser = subparsers.add_parser("verify-all", help="Verify all memories")
    verify_all_parser.add_argument("--dir", default=".serena/memories", help="Memories directory")

    args = parser.parse_args()

    if args.command == "verify":
        path = Path(args.memory)
        if not path.exists():
            path = Path(f".serena/memories/{args.memory}.md")
        if not path.exists():
            print(f"Memory not found: {args.memory}", file=sys.stderr)
            sys.exit(1)

        memory = Memory.from_serena_file(path)
        result = verify_memory(memory)

        if args.json:
            print(json.dumps({
                "memory_id": result.memory_id,
                "valid": result.valid,
                "confidence": result.confidence,
                "stale_citations": [
                    {"path": c.path, "line": c.line, "reason": c.mismatch_reason}
                    for c in result.stale_citations
                ],
            }))
        else:
            status = "✅ VALID" if result.valid else "❌ STALE"
            print(f"{status} ({result.confidence:.0%} confidence)")
            for c in result.stale_citations:
                print(f"  - {c.path}:{c.line} - {c.mismatch_reason}")

        sys.exit(0 if result.valid else 1)

    elif args.command == "verify-all":
        results = verify_all_memories(Path(args.dir))
        stale = [r for r in results if not r.valid]

        if args.json:
            print(json.dumps([{
                "memory_id": r.memory_id,
                "valid": r.valid,
                "confidence": r.confidence,
            } for r in results]))
        else:
            print(f"Verified {len(results)} memories with citations")
            if stale:
                print(f"❌ {len(stale)} stale:")
                for r in stale:
                    print(f"  - {r.memory_id}")
            else:
                print("✅ All citations valid")

        sys.exit(0 if not stale else 1)


if __name__ == "__main__":
    main()
