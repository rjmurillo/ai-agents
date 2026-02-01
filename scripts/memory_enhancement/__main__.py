"""CLI entry point for memory enhancement layer.

Usage:
    python -m memory_enhancement verify <memory-id-or-path> [--json]
    python -m memory_enhancement verify-all [--dir .serena/memories] [--json]
    python -m memory_enhancement health [--dir .serena/memories] [--format {text|markdown|json}]
    python -m memory_enhancement graph <root> [--dir .serena/memories] [--strategy {bfs|dfs}] [--max-depth N] [--json]
    python -m memory_enhancement add-citation <memory-id> --file <path> [--line <num>] [--snippet <text>] [--dry-run]
    python -m memory_enhancement update-confidence <memory-id-or-path>
    python -m memory_enhancement list-citations <memory-id-or-path>

Global Options:
    --json    Output results as JSON (available for verify, verify-all, graph)

Exit Codes:
    0 - Success
    1 - Validation error (stale citations, invalid input)
    2 - File/memory not found
    3 - I/O error
    4 - Security error (path traversal)
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

import yaml

from .citations import verify_memory, verify_all_memories
from .graph import MemoryGraph, TraversalStrategy
from .health import generate_health_report
from .models import Memory
from .serena import add_citation_to_memory, update_confidence, list_citations_with_status

# Exit codes
EXIT_SUCCESS = 0
EXIT_VALIDATION_ERROR = 1
EXIT_NOT_FOUND = 2
EXIT_IO_ERROR = 3
EXIT_SECURITY_ERROR = 4


def _resolve_memory_path(memory_arg: str, exit_code: int = EXIT_NOT_FOUND) -> Path:
    """Resolve memory path with CWE-22 path traversal protection.

    Args:
        memory_arg: Memory ID or file path from CLI argument
        exit_code: Exit code to use if memory not found

    Returns:
        Resolved Path to the memory file

    Exits:
        With exit_code if memory not found
        With EXIT_SECURITY_ERROR if path traversal detected
    """
    path = Path(memory_arg)
    if not path.exists():
        path = Path(f".serena/memories/{memory_arg}.md")
    if not path.exists():
        print(f"Memory not found: {memory_arg}", file=sys.stderr)
        sys.exit(exit_code)

    # CWE-22 path traversal protection using relative_to() for robust containment check
    try:
        resolved = path.resolve()
        cwd_resolved = Path.cwd().resolve()
        resolved.relative_to(cwd_resolved)
    except ValueError:
        print(f"Security error: Path traversal detected: {memory_arg}", file=sys.stderr)
        sys.exit(EXIT_SECURITY_ERROR)
    except OSError as e:
        print(f"Invalid path: {e}", file=sys.stderr)
        sys.exit(EXIT_SECURITY_ERROR)

    return resolved


def _resolve_directory_path(dir_arg: str) -> Path:
    """Resolve directory path with CWE-22 path traversal protection.

    Args:
        dir_arg: Directory path from CLI argument

    Returns:
        Resolved Path to the directory

    Exits:
        With EXIT_NOT_FOUND if directory not found
        With EXIT_SECURITY_ERROR if path traversal detected
    """
    dir_path = Path(dir_arg)
    if not dir_path.exists():
        print(f"Directory not found: {dir_arg}", file=sys.stderr)
        sys.exit(EXIT_NOT_FOUND)
    if not dir_path.is_dir():
        print(f"Not a directory: {dir_arg}", file=sys.stderr)
        sys.exit(EXIT_VALIDATION_ERROR)

    # CWE-22 path traversal protection
    try:
        resolved = dir_path.resolve()
        cwd_resolved = Path.cwd().resolve()
        resolved.relative_to(cwd_resolved)
    except ValueError:
        print(f"Security error: Path traversal detected: {dir_arg}", file=sys.stderr)
        sys.exit(EXIT_SECURITY_ERROR)
    except OSError as e:
        print(f"Invalid path: {e}", file=sys.stderr)
        sys.exit(EXIT_SECURITY_ERROR)

    return resolved


def _handle_verify(args) -> int:
    """Handle the verify command."""
    path = _resolve_memory_path(args.memory, EXIT_VALIDATION_ERROR)
    try:
        memory = Memory.from_serena_file(path)
    except (yaml.YAMLError, ValueError, KeyError, UnicodeDecodeError, OSError) as e:
        print(f"Error: Failed to parse memory file: {e}", file=sys.stderr)
        return EXIT_VALIDATION_ERROR
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
        status = "VALID" if result.valid else "STALE"
        print(f"{status} ({result.confidence:.0%} confidence)")
        for c in result.stale_citations:
            print(f"  - {c.path}:{c.line} - {c.mismatch_reason}")

    return EXIT_SUCCESS if result.valid else EXIT_VALIDATION_ERROR


def _handle_verify_all(args) -> int:
    """Handle the verify-all command."""
    dir_path = _resolve_directory_path(args.dir)
    verify_result = verify_all_memories(dir_path)
    results = verify_result.results
    stale = [r for r in results if not r.valid]

    if args.json:
        output = {
            "results": [{
                "memory_id": r.memory_id,
                "valid": r.valid,
                "confidence": r.confidence,
            } for r in results],
            "parse_failures": verify_result.parse_failures,
        }
        print(json.dumps(output))
    else:
        print(f"Verified {len(results)} memories with citations")
        if verify_result.parse_failures > 0:
            print(f"{verify_result.parse_failures} file(s) could not be parsed", file=sys.stderr)
        if stale:
            print(f"{len(stale)} stale:")
            for r in stale:
                print(f"  - {r.memory_id}")
        else:
            print("All citations valid")

    return EXIT_SUCCESS if not stale else EXIT_VALIDATION_ERROR


def _handle_health(args) -> int:
    """Handle the health command."""
    dir_path = _resolve_directory_path(args.dir)
    # Map CLI format to internal format (both 'text' and 'markdown' produce markdown output)
    internal_format = "markdown" if args.format in ("text", "markdown") else "json"
    report = generate_health_report(dir_path, format=internal_format)

    if args.format == "json":
        print(json.dumps(report, indent=2))
    else:
        print(report)

    return EXIT_SUCCESS


def _handle_graph(args) -> int:
    """Handle the graph command."""
    dir_path = _resolve_directory_path(args.dir)

    try:
        graph = MemoryGraph(dir_path)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return EXIT_NOT_FOUND

    if not graph.get_memory(args.root):
        print(f"Error: Root memory not found: {args.root}", file=sys.stderr)
        return EXIT_NOT_FOUND

    strategy = TraversalStrategy.BFS if args.strategy == "bfs" else TraversalStrategy.DFS

    try:
        result = graph.traverse(
            root_id=args.root,
            strategy=strategy,
            max_depth=args.max_depth
        )
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return EXIT_VALIDATION_ERROR

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

    return EXIT_SUCCESS


def _handle_add_citation(args) -> int:
    """Handle the add-citation command."""
    path = _resolve_memory_path(args.memory, EXIT_NOT_FOUND)

    if args.dry_run:
        print(f"[DRY RUN] Would add citation to {path}")
        print(f"  File: {args.file}")
        print(f"  Line: {args.line if args.line else '(file-level)'}")
        print(f"  Snippet: {args.snippet if args.snippet else '(none)'}")
        return EXIT_SUCCESS

    try:
        add_citation_to_memory(
            memory_path=path,
            file_path=args.file,
            line=args.line,
            snippet=args.snippet
        )
        print(f"Citation added to {path.stem}")
        return EXIT_SUCCESS
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return EXIT_NOT_FOUND
    except (yaml.YAMLError, ValueError, KeyError, UnicodeDecodeError, OSError) as e:
        print(f"Validation failed: {e}", file=sys.stderr)
        return EXIT_VALIDATION_ERROR
    except IOError as e:
        print(f"I/O error: {e}", file=sys.stderr)
        return EXIT_IO_ERROR


def _handle_update_confidence(args) -> int:
    """Handle the update-confidence command."""
    path = _resolve_memory_path(args.memory, EXIT_NOT_FOUND)

    try:
        memory = Memory.from_serena_file(path)
    except (yaml.YAMLError, ValueError, KeyError, UnicodeDecodeError, OSError) as e:
        print(f"Error: Failed to parse memory file: {e}", file=sys.stderr)
        return EXIT_VALIDATION_ERROR

    try:
        verification = verify_memory(memory)
        update_confidence(memory, verification)
        print(f"Confidence updated: {verification.confidence:.0%}")
        if verification.stale_citations:
            print(f"Warning: {len(verification.stale_citations)} stale citations found:")
            for c in verification.stale_citations:
                print(f"  - {c.path}:{c.line} - {c.mismatch_reason}")
        return EXIT_SUCCESS
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return EXIT_NOT_FOUND
    except IOError as e:
        print(f"I/O error: {e}", file=sys.stderr)
        return EXIT_IO_ERROR


def _handle_list_citations(args) -> int:
    """Handle the list-citations command."""
    path = _resolve_memory_path(args.memory, EXIT_NOT_FOUND)

    try:
        citations = list_citations_with_status(path)
        if not citations:
            print(f"No citations in {path.stem}")
            return EXIT_SUCCESS

        print(f"Citations in {path.stem}:")
        for c in citations:
            status = "VALID" if c["valid"] else "INVALID"
            line_info = f":{c['line']}" if c["line"] else ""
            print(f"  {status} {c['path']}{line_info}")
            if not c["valid"]:
                print(f"     Reason: {c['mismatch_reason']}")
        return EXIT_SUCCESS
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return EXIT_NOT_FOUND
    except (yaml.YAMLError, ValueError, KeyError, UnicodeDecodeError, OSError) as e:
        print(f"Error: Failed to process memory file: {e}", file=sys.stderr)
        return EXIT_VALIDATION_ERROR
    except IOError as e:
        print(f"I/O error: {e}", file=sys.stderr)
        return EXIT_IO_ERROR


def _build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
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
    health_parser.add_argument("--format", choices=["text", "markdown", "json"], default="text", help="Output format")

    # graph command
    graph_parser = subparsers.add_parser("graph", help="Traverse memory relationship graph")
    graph_parser.add_argument("root", help="Root memory ID")
    graph_parser.add_argument("--dir", default=".serena/memories", help="Memories directory")
    graph_parser.add_argument("--strategy", choices=["bfs", "dfs"], default="bfs", help="Traversal strategy")
    graph_parser.add_argument("--max-depth", type=int, help="Maximum traversal depth")

    # add-citation command
    add_citation_parser = subparsers.add_parser("add-citation", help="Add citation to memory")
    add_citation_parser.add_argument("memory", help="Memory ID or file path")
    add_citation_parser.add_argument("--file", required=True, help="Relative file path from repository root")
    add_citation_parser.add_argument("--line", type=int, help="Line number (1-indexed)")
    add_citation_parser.add_argument("--snippet", help="Code snippet for fuzzy matching")
    add_citation_parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing")

    # update-confidence command
    update_confidence_parser = subparsers.add_parser("update-confidence", help="Update memory confidence score")
    update_confidence_parser.add_argument("memory", help="Memory ID or file path")

    # list-citations command
    list_citations_parser = subparsers.add_parser("list-citations", help="List citations with status")
    list_citations_parser.add_argument("memory", help="Memory ID or file path")

    return parser


def main() -> int:
    """CLI entry point."""
    parser = _build_parser()
    args = parser.parse_args()

    handlers = {
        "verify": _handle_verify,
        "verify-all": _handle_verify_all,
        "health": _handle_health,
        "graph": _handle_graph,
        "add-citation": _handle_add_citation,
        "update-confidence": _handle_update_confidence,
        "list-citations": _handle_list_citations,
    }

    return handlers[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
