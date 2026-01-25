"""CLI entry point for memory enhancement layer.

Usage:
    python -m memory_enhancement verify <memory-id-or-path>
    python -m memory_enhancement verify-all [--dir .serena/memories]
    python -m memory_enhancement health [--format {text|markdown}]
    python -m memory_enhancement graph <root> [--strategy {bfs|dfs}] [--max-depth N]
"""

import argparse
import json
import sys
from pathlib import Path

from .citations import verify_memory, verify_all_memories
from .graph import MemoryGraph, TraversalStrategy
from .health import generate_health_report
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

    # health command
    health_parser = subparsers.add_parser("health", help="Generate memory health report")
    health_parser.add_argument("--dir", default=".serena/memories", help="Memories directory")
    health_parser.add_argument("--format", choices=["text", "markdown"], default="text", help="Output format")

    # graph command
    graph_parser = subparsers.add_parser("graph", help="Traverse memory relationship graph")
    graph_parser.add_argument("root", help="Root memory ID")
    graph_parser.add_argument("--dir", default=".serena/memories", help="Memories directory")
    graph_parser.add_argument("--strategy", choices=["bfs", "dfs"], default="bfs", help="Traversal strategy")
    graph_parser.add_argument("--max-depth", type=int, help="Maximum traversal depth")

    args = parser.parse_args()

    if args.command == "verify":
        path = Path(args.memory)
        if not path.exists():
            path = Path(f".serena/memories/{args.memory}.md")
        if not path.exists():
            print(f"Memory not found: {args.memory}", file=sys.stderr)
            sys.exit(1)

        # CWE-22 path traversal protection: validate path is within expected directories
        try:
            resolved = path.resolve()
            cwd_resolved = Path.cwd().resolve()
            if not str(resolved).startswith(str(cwd_resolved) + "/"):
                print(f"Security error: Path traversal detected: {args.memory}", file=sys.stderr)
                sys.exit(1)
        except (ValueError, OSError) as e:
            print(f"Invalid path: {e}", file=sys.stderr)
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

    elif args.command == "health":
        report = generate_health_report(Path(args.dir), format=args.format)
        if args.format == "markdown":
            print(report)
        else:
            print(json.dumps(report, indent=2))
        sys.exit(0)

    elif args.command == "graph":
        # Load memory graph
        try:
            graph = MemoryGraph(Path(args.dir))
        except FileNotFoundError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

        # Verify root memory exists
        if not graph.get_memory(args.root):
            print(f"Error: Root memory not found: {args.root}", file=sys.stderr)
            sys.exit(1)

        # Parse strategy
        strategy = TraversalStrategy.BFS if args.strategy == "bfs" else TraversalStrategy.DFS

        # Traverse graph
        try:
            result = graph.traverse(
                root_id=args.root,
                strategy=strategy,
                max_depth=args.max_depth
            )
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

        # Output results
        if args.json:
            print(json.dumps({
                "root_id": result.root_id,
                "strategy": result.strategy.value,
                "max_depth": result.max_depth,
                "nodes": [
                    {
                        "memory_id": node.memory.id,
                        "depth": node.depth,
                        "parent": node.parent,
                        "link_type": node.link_type.value if node.link_type else None
                    }
                    for node in result.nodes
                ],
                "cycles": [{"from": f, "to": t} for f, t in result.cycles]
            }))
        else:
            print(f"Graph Traversal ({result.strategy.value.upper()})")
            print(f"Root: {result.root_id}")
            print(f"Nodes visited: {len(result.nodes)}")
            print(f"Max depth: {result.max_depth}")
            print(f"Cycles detected: {len(result.cycles)}")
            print()
            print("Traversal order:")
            for node in result.nodes:
                indent = "  " * node.depth
                link_info = f" [{node.link_type.value}]" if node.link_type else ""
                parent_info = f" (from {node.parent})" if node.parent else " (root)"
                print(f"{indent}- {node.memory.id}{link_info}{parent_info}")

            if result.cycles:
                print()
                print("Cycles:")
                for from_id, to_id in result.cycles:
                    print(f"  - {from_id} -> {to_id}")

        sys.exit(0)


if __name__ == "__main__":
    main()
