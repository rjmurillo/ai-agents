"""CLI for memory enhancement tools."""

import argparse
import json
import sys
from pathlib import Path

from .graph import (
    find_blocking_dependencies,
    find_related_memories,
    find_root_memories,
    find_superseded_chain,
    traverse_graph,
)
from .models import LinkType


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Memory Enhancement Tools for Serena memories"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # graph command
    graph_parser = subparsers.add_parser("graph", help="Traverse memory graph")
    graph_parser.add_argument("root", help="Root memory ID")
    graph_parser.add_argument(
        "--depth", type=int, default=3, help="Max traversal depth (default: 3)"
    )
    graph_parser.add_argument(
        "--dir",
        default=".serena/memories",
        help="Memories directory (default: .serena/memories)",
    )
    graph_parser.add_argument(
        "--json", action="store_true", help="Output as JSON"
    )

    # related command
    related_parser = subparsers.add_parser(
        "related", help="Find memories linking to target"
    )
    related_parser.add_argument("memory", help="Target memory ID")
    related_parser.add_argument(
        "--dir",
        default=".serena/memories",
        help="Memories directory (default: .serena/memories)",
    )

    # roots command
    roots_parser = subparsers.add_parser(
        "roots", help="Find root memories (no incoming links)"
    )
    roots_parser.add_argument(
        "--dir",
        default=".serena/memories",
        help="Memories directory (default: .serena/memories)",
    )

    # superseded command
    superseded_parser = subparsers.add_parser(
        "superseded", help="Find superseded memory chain"
    )
    superseded_parser.add_argument("memory", help="Starting memory ID")
    superseded_parser.add_argument(
        "--dir",
        default=".serena/memories",
        help="Memories directory (default: .serena/memories)",
    )

    # blocking command
    blocking_parser = subparsers.add_parser(
        "blocking", help="Find blocking dependencies"
    )
    blocking_parser.add_argument("memory", help="Target memory ID")
    blocking_parser.add_argument(
        "--dir",
        default=".serena/memories",
        help="Memories directory (default: .serena/memories)",
    )

    args = parser.parse_args()
    memories_dir = Path(args.dir)

    # Verify memories directory exists
    if not memories_dir.exists():
        print(f"Error: Memories directory not found: {memories_dir}", file=sys.stderr)
        sys.exit(1)

    try:
        if args.command == "graph":
            result = traverse_graph(args.root, memories_dir, args.depth)
            if args.json:
                output = {
                    "root": args.root,
                    "visited_count": result.visited_count,
                    "max_depth": result.max_depth_reached,
                    "edges": [
                        {
                            "source": e.source_id,
                            "target": e.target_id,
                            "type": e.link_type.value,
                        }
                        for e in result.edges
                    ],
                }
                print(json.dumps(output, indent=2))
            else:
                print(
                    f"Graph from '{args.root}' "
                    f"(visited: {result.visited_count}, "
                    f"depth: {result.max_depth_reached}):"
                )
                for node, links in result.nodes.items():
                    if links:
                        targets = [
                            f"{link.target_id} ({link.link_type.value})"
                            for link in links
                        ]
                        print(f"  {node} -> {', '.join(targets)}")
                    else:
                        print(f"  {node} (no outgoing links)")

        elif args.command == "related":
            related = find_related_memories(args.memory, memories_dir)
            print(f"Memories linking to '{args.memory}':")
            if related:
                for r in related:
                    print(f"  - {r}")
            else:
                print("  (none)")

        elif args.command == "roots":
            roots = find_root_memories(memories_dir)
            print(f"Root memories (no incoming links): {len(roots)}")
            for r in roots:
                print(f"  - {r}")

        elif args.command == "superseded":
            chain = find_superseded_chain(args.memory, memories_dir)
            print(f"Superseded chain from '{args.memory}':")
            if chain:
                for c in chain:
                    print(f"  - {c}")
            else:
                print("  (none)")

        elif args.command == "blocking":
            blocking = find_blocking_dependencies(args.memory, memories_dir)
            print(f"Blocking dependencies for '{args.memory}':")
            if blocking:
                for b in blocking:
                    print(f"  - {b}")
            else:
                print("  (none)")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
