#!/usr/bin/env python3
"""Display the traceability graph in various formats.

Visualizes the traceability graph showing relationships between requirements,
designs, and tasks. Supports text (tree), Mermaid.js, and JSON output.

EXIT CODES:
  0 - Success
  1 - Error (invalid path, spec not found, etc.)

See: ADR-035 Exit Code Standardization
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.traceability.spec_utils import (  # noqa: E402
    is_valid_spec_id,
    load_all_specs,
    validate_specs_path,
)


def build_graph(specs: dict[str, Any]) -> dict[str, Any]:
    """Build a graph structure from loaded specs.

    Returns a dict with nodes, edges, forward_refs, and backward_refs.
    forward_refs maps a spec to specs that reference it (children).
    backward_refs maps a spec to specs it references (parents).
    """
    graph: dict[str, Any] = {
        "nodes": {},
        "edges": [],
        "forward_refs": {},
        "backward_refs": {},
    }

    for spec_id, spec in specs["all"].items():
        graph["nodes"][spec_id] = {
            "id": spec_id,
            "type": spec.get("type", ""),
            "status": spec.get("status", ""),
        }
        graph["forward_refs"][spec_id] = []
        graph["backward_refs"][spec_id] = []

    for spec_id, spec in specs["all"].items():
        for related_id in spec.get("related", []):
            if related_id not in specs["all"]:
                continue
            graph["edges"].append({"from": spec_id, "to": related_id})
            graph["forward_refs"][related_id].append(spec_id)
            graph["backward_refs"][spec_id].append(related_id)

    return graph


def get_connected_ids(
    graph: dict[str, Any],
    root_id: str,
    direction: str,
    max_depth: int,
    current_depth: int = 0,
    visited: set[str] | None = None,
) -> list[str]:
    """Traverse the graph in a given direction ('forward' or 'backward').

    Returns all reachable node IDs up to max_depth (0 = unlimited).
    """
    if visited is None:
        visited = set()
    if root_id in visited:
        return []
    visited.add(root_id)

    result = [root_id]
    if max_depth != 0 and current_depth >= max_depth:
        return result

    ref_key = "forward_refs" if direction == "forward" else "backward_refs"
    for neighbor in graph[ref_key].get(root_id, []):
        result.extend(
            get_connected_ids(graph, neighbor, direction, max_depth, current_depth + 1, visited)
        )
    return result


def format_text_graph(
    graph: dict[str, Any],
    specs: dict[str, Any],
    root_id: str | None,
    max_depth: int,
    show_orphans: bool,
) -> str:
    """Render the graph as an ASCII tree."""
    lines: list[str] = []
    visited: set[str] = set()

    def write_node(node_id: str, level: int) -> None:
        if node_id in visited:
            return
        visited.add(node_id)
        indent = "  " * level
        node = graph["nodes"][node_id]
        status = node.get("status", "")
        marker = "[x]" if status in ("complete", "done", "implemented") else (
            "[~]" if status == "approved" else "[ ]"
        )
        lines.append(f"{indent}{marker} {node_id} ({node['type']})")
        if max_depth == 0 or level < max_depth:
            for child_id in sorted(graph["forward_refs"].get(node_id, [])):
                write_node(child_id, level + 1)

    lines.append("Traceability Graph")
    lines.append("==================")
    lines.append("")

    if root_id:
        if root_id not in graph["nodes"]:
            return f"Error: Spec '{root_id}' not found"
        write_node(root_id, 0)
    else:
        lines.append("Requirements:")
        for req_id in sorted(specs["requirements"]):
            write_node(req_id, 1)

        if show_orphans:
            orphaned_designs = [
                did for did in specs["designs"]
                if not graph["forward_refs"].get(did) and did not in visited
            ]
            if orphaned_designs:
                lines.append("")
                lines.append("Orphaned Designs:")
                for did in sorted(orphaned_designs):
                    write_node(did, 1)

            orphaned_tasks = [
                tid for tid in specs["tasks"]
                if not graph["backward_refs"].get(tid) and tid not in visited
            ]
            if orphaned_tasks:
                lines.append("")
                lines.append("Orphaned Tasks:")
                for tid in sorted(orphaned_tasks):
                    write_node(tid, 1)

    return "\n".join(lines)


def format_mermaid_graph(
    graph: dict[str, Any],
    specs: dict[str, Any],
    root_id: str | None,
    max_depth: int,
) -> str:
    """Render the graph as a Mermaid.js diagram."""
    nodes_to_include = _get_included_nodes(graph, root_id, max_depth)

    lines = ["```mermaid", "graph TD"]

    for nid in sorted(nodes_to_include):
        node = graph["nodes"][nid]
        safe_id = nid.replace("-", "_")
        ntype = node.get("type", "")
        if ntype == "requirement":
            shape = f"[{nid}]"
        elif ntype == "design":
            shape = f"([{nid}])"
        elif ntype == "task":
            shape = "{" + nid + "}"
        else:
            shape = f"[{nid}]"
        lines.append(f"    {safe_id}{shape}")

    lines.append("")

    for edge in graph["edges"]:
        if edge["from"] in nodes_to_include and edge["to"] in nodes_to_include:
            from_id = edge["from"].replace("-", "_")
            to_id = edge["to"].replace("-", "_")
            lines.append(f"    {from_id} --> {to_id}")

    lines.append("")
    lines.append("    classDef req fill:#e3f2fd,stroke:#1976d2,color:#000")
    lines.append("    classDef design fill:#fff3e0,stroke:#f57c00,color:#000")
    lines.append("    classDef task fill:#e8f5e9,stroke:#388e3c,color:#000")
    lines.append("    classDef complete fill:#c8e6c9,stroke:#2e7d32,color:#000")

    req_nodes, design_nodes, task_nodes, complete_nodes = [], [], [], []
    for nid in nodes_to_include:
        node = graph["nodes"][nid]
        safe_id = nid.replace("-", "_")
        if node.get("status") in ("complete", "done", "implemented"):
            complete_nodes.append(safe_id)
        elif node.get("type") == "requirement":
            req_nodes.append(safe_id)
        elif node.get("type") == "design":
            design_nodes.append(safe_id)
        elif node.get("type") == "task":
            task_nodes.append(safe_id)

    if req_nodes:
        lines.append(f"    class {','.join(req_nodes)} req")
    if design_nodes:
        lines.append(f"    class {','.join(design_nodes)} design")
    if task_nodes:
        lines.append(f"    class {','.join(task_nodes)} task")
    if complete_nodes:
        lines.append(f"    class {','.join(complete_nodes)} complete")

    lines.append("```")
    return "\n".join(lines)


def format_json_graph(
    graph: dict[str, Any],
    root_id: str | None,
    max_depth: int,
) -> str:
    """Render the graph as JSON with nodes, edges, and stats."""
    nodes_to_include = _get_included_nodes(graph, root_id, max_depth)

    nodes = [
        {"id": nid, "type": graph["nodes"][nid]["type"], "status": graph["nodes"][nid]["status"]}
        for nid in sorted(nodes_to_include)
    ]
    edges = [
        {"from": e["from"], "to": e["to"]}
        for e in graph["edges"]
        if e["from"] in nodes_to_include and e["to"] in nodes_to_include
    ]

    result = {
        "nodes": nodes,
        "edges": edges,
        "stats": {"nodeCount": len(nodes), "edgeCount": len(edges)},
    }
    return json.dumps(result, indent=2)


def _get_included_nodes(
    graph: dict[str, Any], root_id: str | None, max_depth: int
) -> set[str]:
    """Determine which nodes to include based on root and depth."""
    if root_id:
        if root_id not in graph["nodes"]:
            return set()
        descendants = get_connected_ids(graph, root_id, "forward", max_depth)
        ancestors = get_connected_ids(graph, root_id, "backward", max_depth)
        return set(descendants) | set(ancestors)
    return set(graph["nodes"].keys())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Display the traceability graph.")
    parser.add_argument("--specs-path", default=".agents/specs", help="Path to specs directory")
    parser.add_argument(
        "--format",
        choices=["text", "mermaid", "json"],
        default="text",
        help="Output format (default: text)",
    )
    parser.add_argument("--root-id", default=None, help="Start graph from a specific spec ID")
    parser.add_argument("--depth", type=int, default=0, help="Max traversal depth (0 = unlimited)")
    parser.add_argument("--dry-run", action="store_true", help="Validate parameters only")
    parser.add_argument("--show-orphans", action="store_true", help="Include orphaned specs")
    parser.add_argument("--no-cache", action="store_true", help="Bypass cache")
    args = parser.parse_args(argv)

    if args.root_id and not is_valid_spec_id(args.root_id):
        print(f"Invalid RootId format: {args.root_id}. Expected: TYPE-ID (e.g., REQ-001)", file=sys.stderr)
        return 1

    try:
        resolved_path = validate_specs_path(args.specs_path)
    except SystemExit:
        return 1

    if args.dry_run:
        print("Dry-run test successful")
        return 0

    specs = load_all_specs(resolved_path, use_cache=not args.no_cache)

    if args.root_id and args.root_id not in specs["all"]:
        print(f"Spec not found: {args.root_id}", file=sys.stderr)
        return 1

    graph = build_graph(specs)

    if args.format == "text":
        output = format_text_graph(graph, specs, args.root_id, args.depth, args.show_orphans)
    elif args.format == "mermaid":
        output = format_mermaid_graph(graph, specs, args.root_id, args.depth)
    else:
        output = format_json_graph(graph, args.root_id, args.depth)

    print(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
