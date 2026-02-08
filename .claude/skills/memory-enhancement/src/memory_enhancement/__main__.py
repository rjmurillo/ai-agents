"""CLI entry point for memory enhancement.

Usage:
    python -m memory_enhancement verify <memory-id-or-path> [--json] [--repo-root PATH]
    python -m memory_enhancement verify-all [--dir PATH] [--json] [--repo-root PATH]
    python -m memory_enhancement graph <memory_id> [--mode bfs|dfs] [--max-depth N] [--json]
    python -m memory_enhancement graph --cycles [--json] [--dir PATH]
    python -m memory_enhancement graph --score <memory_id> [--json] [--dir PATH]
"""

import argparse
import json
import sys
from pathlib import Path

from .citations import VerificationResult, verify_all_memories, verify_memory
from .graph import MemoryGraph
from .models import Memory

DEFAULT_MEMORIES_DIR = ".serena/memories"


def _find_memory(memory_id: str, memories_dir: Path, repo_root: Path) -> Path:
    """Resolve a memory ID or path to a file path.

    Tries: literal path (if within repo_root), then {memory_id}.md in
    memories_dir, then bare filename in memories_dir.

    Raises FileNotFoundError if not found.
    """
    repo_root_resolved = repo_root.resolve()

    # Check if memory_id is a direct path within the repo root.
    candidate = Path(memory_id)
    if candidate.exists():
        try:
            candidate.resolve().relative_to(repo_root_resolved)
            return candidate
        except (ValueError, OSError):
            pass  # Outside repo root, fall through to ID-based search.

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
        memory_path = _find_memory(args.memory_id, memories_dir, repo_root)
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


def cmd_graph(args: argparse.Namespace) -> int:
    """Handle graph traversal, cycle detection, and relationship scoring."""
    repo_root = Path(args.repo_root).resolve()
    memories_dir = (repo_root / args.dir).resolve()

    if not str(memories_dir).startswith(str(repo_root)):
        print(f"Error: Memories directory is outside the repository: {args.dir}", file=sys.stderr)
        return 2

    if not memories_dir.exists():
        print(f"Error: Memories directory not found: {memories_dir}", file=sys.stderr)
        return 2

    try:
        graph = MemoryGraph.from_directory(memories_dir)
    except OSError as e:
        print(f"Error: Failed to load memories: {e}", file=sys.stderr)
        return 2

    if args.cycles:
        return _graph_cycles(graph, args)

    if args.score:
        return _graph_score(graph, args)

    return _graph_traverse(graph, args)


def _graph_traverse(graph: MemoryGraph, args: argparse.Namespace) -> int:
    """Run BFS or DFS traversal and print results."""
    if not args.memory_id:
        print("Error: memory_id is required for traversal", file=sys.stderr)
        return 2

    traverse_fn = graph.bfs if args.mode == "bfs" else graph.dfs

    try:
        nodes = traverse_fn(args.memory_id, max_depth=args.max_depth)
    except KeyError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2

    if args.json:
        data = {
            "start": args.memory_id,
            "mode": args.mode,
            "max_depth": args.max_depth,
            "nodes": [
                {
                    "memory_id": n.memory_id,
                    "depth": n.depth,
                    "link_type": n.link_type,
                    "parent_id": n.parent_id,
                }
                for n in nodes
            ],
        }
        print(json.dumps(data, indent=2))
    else:
        depth_label = f", max_depth={args.max_depth}" if args.max_depth is not None else ""
        mode_label = args.mode.upper()
        print(f"Graph traversal from '{args.memory_id}' ({mode_label}{depth_label}):")
        for node in nodes:
            suffix = f" ({node.link_type})" if node.link_type else ""
            print(f"  [{node.depth}] {node.memory_id}{suffix}")
        print(f"\nNodes visited: {len(nodes)}")

    return 0


def _graph_cycles(graph: MemoryGraph, args: argparse.Namespace) -> int:
    """Detect and report cycles in the memory graph."""
    cycles = graph.find_cycles()

    if args.json:
        data = {
            "cycles": cycles,
            "count": len(cycles),
        }
        print(json.dumps(data, indent=2))
    else:
        print("Cycle detection results:")
        if cycles:
            for i, cycle in enumerate(cycles, 1):
                print(f"  Cycle {i}: {' -> '.join(cycle)}")
            print(f"\nFound {len(cycles)} cycle(s).")
        else:
            print("  No cycles found.")

    return 1 if cycles else 0


def _graph_score(graph: MemoryGraph, args: argparse.Namespace) -> int:
    """Score and display relationships for a memory."""
    if not args.memory_id:
        print("Error: memory_id is required with --score", file=sys.stderr)
        return 2

    try:
        scores = graph.score_relationships(args.memory_id)
    except KeyError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2

    if args.json:
        data = {
            "memory_id": args.memory_id,
            "relationships": [
                {
                    "target_id": s.target_id,
                    "score": round(s.score, 2),
                    "link_type": s.link_type,
                    "distance": s.distance,
                }
                for s in scores
            ],
        }
        print(json.dumps(data, indent=2))
    else:
        print(f"Relationship scores for '{args.memory_id}':")
        for s in scores:
            print(f"  {s.target_id}: {s.score:.2f} ({s.link_type}, distance={s.distance})")
        print(f"\nTotal relationships: {len(scores)}")

    return 0


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

    graph_parser = subparsers.add_parser(
        "graph", help="Graph traversal and analysis", parents=[common]
    )
    graph_parser.add_argument(
        "memory_id", nargs="?", default=None,
        help="Memory ID for traversal or scoring",
    )
    graph_parser.add_argument(
        "--mode", choices=["bfs", "dfs"], default="bfs",
        help="Traversal algorithm (default: bfs)",
    )
    graph_parser.add_argument(
        "--max-depth", type=int, default=None,
        help="Maximum traversal depth",
    )
    graph_parser.add_argument(
        "--cycles", action="store_true",
        help="Detect cycles instead of traversal",
    )
    graph_parser.add_argument(
        "--score", action="store_true",
        help="Show relationship scores instead of traversal",
    )

    args = parser.parse_args()

    if args.command == "verify":
        return cmd_verify(args)
    elif args.command == "verify-all":
        return cmd_verify_all(args)
    elif args.command == "graph":
        return cmd_graph(args)

    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
