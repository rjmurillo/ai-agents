"""CLI entry point for the memory enhancement layer.

Usage: python -m scripts.memory_enhancement <command> [options]

Commands:
  verify      Verify citations in memories
  health      Generate a health report
  graph       Traverse the memory graph
  confidence  Show or update confidence scores
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from pathlib import Path

from .confidence import update_confidence_scores
from .graph import build_memory_graph, traverse
from .health import format_report, generate_health_report
from .models import VerificationResult
from .serena_integration import load_memories
from .verification import verify_all_citations


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and dispatch to the appropriate command handler.

    Args:
        argv: Command-line arguments. Uses sys.argv if None.

    Returns:
        Exit code: 0 for success, 1 for errors.
    """
    parser = _build_parser()
    args = parser.parse_args(argv)

    if not hasattr(args, "func"):
        parser.print_help()
        return 1

    func: Callable[[argparse.Namespace], int] = args.func
    return func(args)


def _build_parser() -> argparse.ArgumentParser:
    """Construct the argument parser with subcommands."""
    parser = argparse.ArgumentParser(
        prog="memory_enhancement",
        description="Memory Enhancement Layer for AI Agents",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path.cwd(),
        help="Repository root directory (default: cwd)",
    )
    parser.add_argument(
        "--memories-dir",
        type=Path,
        default=None,
        help="Memories directory (default: <repo-root>/.serena/memories)",
    )

    subparsers = parser.add_subparsers(title="commands")

    _add_verify_command(subparsers)
    _add_verify_all_command(subparsers)
    _add_health_command(subparsers)
    _add_graph_command(subparsers)
    _add_confidence_command(subparsers)

    return parser


def _add_verify_command(subparsers: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    """Register the verify subcommand."""
    verify_parser = subparsers.add_parser("verify", help="Verify citations")
    verify_parser.add_argument("--memory-id", type=str, default=None, help="Specific memory ID")
    verify_parser.set_defaults(func=_cmd_verify)


def _add_verify_all_command(subparsers: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    """Register the verify-all subcommand (CI compatibility)."""
    va_parser = subparsers.add_parser("verify-all", help="Verify all memory citations")
    va_parser.add_argument("--json", dest="json_output", action="store_true", help="Output as JSON")
    va_parser.set_defaults(func=_cmd_verify_all)


def _add_health_command(subparsers: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    """Register the health subcommand."""
    health_parser = subparsers.add_parser("health", help="Generate health report")
    health_parser.set_defaults(func=_cmd_health)


def _add_graph_command(subparsers: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    """Register the graph subcommand."""
    graph_parser = subparsers.add_parser("graph", help="Traverse memory graph")
    graph_parser.add_argument("--start", type=str, required=True, help="Starting memory ID")
    graph_parser.add_argument("--depth", type=int, default=3, help="Max traversal depth")
    graph_parser.set_defaults(func=_cmd_graph)


def _add_confidence_command(subparsers: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    """Register the confidence subcommand."""
    conf_parser = subparsers.add_parser("confidence", help="Show confidence scores")
    # Write-back (--update) deferred to a future PR.
    conf_parser.set_defaults(func=_cmd_confidence)


def _resolve_memories_dir(args: argparse.Namespace) -> Path:
    """Resolve the memories directory from args or default."""
    if args.memories_dir is not None:
        return Path(args.memories_dir)
    return Path(args.repo_root) / ".serena" / "memories"


def _cmd_verify(args: argparse.Namespace) -> int:
    """Execute the verify command."""
    memories_dir = _resolve_memories_dir(args)
    memories = load_memories(memories_dir)

    if args.memory_id:
        memories = [m for m in memories if m.memory_id == args.memory_id]
        if not memories:
            print(f"Memory not found: {args.memory_id}", file=sys.stderr)
            return 1

    found_issues = False
    for memory in memories:
        results = verify_all_citations(memory, args.repo_root)
        _print_verification_results(memory.memory_id, results)
        if any(not r.is_valid for r in results):
            found_issues = True

    return 1 if found_issues else 0


def _cmd_verify_all(args: argparse.Namespace) -> int:
    """Verify all memory citations, with optional JSON output.

    JSON format: flat array of objects with 'valid' field (CI compatible).
    """
    memories_dir = _resolve_memories_dir(args)
    memories = load_memories(memories_dir)
    flat_results: list[dict[str, object]] = []
    found_issues = False

    for memory in memories:
        results = verify_all_citations(memory, args.repo_root)
        if any(not r.is_valid for r in results):
            found_issues = True
        for r in results:
            flat_results.append({
                "memory_id": memory.memory_id,
                "target": r.citation.target,
                "source_type": r.citation.source_type.value,
                "valid": r.is_valid,
                "reason": r.reason,
            })

    if args.json_output:
        print(json.dumps(flat_results, indent=2))
    else:
        report = generate_health_report(memories_dir, args.repo_root)
        print(format_report(report))

    return 1 if found_issues else 0


def _cmd_health(args: argparse.Namespace) -> int:
    """Execute the health command."""
    memories_dir = _resolve_memories_dir(args)
    report = generate_health_report(memories_dir, args.repo_root)
    print(format_report(report))
    return 0


def _cmd_graph(args: argparse.Namespace) -> int:
    """Execute the graph command."""
    memories_dir = _resolve_memories_dir(args)
    graph = build_memory_graph(memories_dir)

    try:
        results = traverse(graph, args.start, max_depth=args.depth)
    except KeyError:
        print(f"Memory not found: {args.start}", file=sys.stderr)
        return 1

    if not results:
        print(f"No linked memories found from: {args.start}")
        return 0

    for memory_id, depth, link_type in results:
        indent = "  " * depth
        print(f"{indent}{memory_id} ({link_type}, depth={depth})")
    return 0


def _cmd_confidence(args: argparse.Namespace) -> int:
    """Execute the confidence command."""
    memories_dir = _resolve_memories_dir(args)
    scores = update_confidence_scores(memories_dir, args.repo_root)

    if not scores:
        print("No memories found.")
        return 0

    for memory_id, score in sorted(scores.items()):
        print(f"{memory_id}: {score:.3f}")
    return 0


def _print_verification_results(
    memory_id: str, results: list[VerificationResult]
) -> None:
    """Print verification results for a single memory."""
    if not results:
        print(f"{memory_id}: no citations")
        return

    print(f"\n{memory_id}:")
    for result in results:
        status = "[PASS]" if result.is_valid else "[FAIL]"
        print(f"  {status} {result.citation.target} - {result.reason}")


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
