#!/usr/bin/env python3
"""Reconstruct multi-agent call graphs from session log trace IDs.

Scans session logs in .agents/sessions/ for trace correlation fields
(traceId, parentSessionId) and reconstructs the full delegation tree.

Output formats: text (tree), json, mermaid.

EXIT CODES (ADR-035):
    0 - Success
    1 - No matching sessions found or invalid arguments
    2 - File I/O or config error
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parent.parent
_SESSIONS_DIR = _PROJECT_ROOT / ".agents" / "sessions"


@dataclass
class SessionNode:
    """A node in the agent call graph."""

    session_id: str
    trace_id: str
    parent_session_id: str
    branch: str
    objective: str
    date: str
    children: list[SessionNode] = field(default_factory=list)


def parse_session_file(path: Path) -> dict[str, Any] | None:
    """Parse a session log JSON file. Returns None on failure."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (json.JSONDecodeError, OSError):
        return None


def session_id_from_filename(path: Path) -> str:
    """Extract session identifier from filename (e.g. 2026-03-09-session-700)."""
    return path.stem


def collect_traced_sessions(sessions_dir: Path) -> dict[str, list[SessionNode]]:
    """Scan session logs and group by trace_id.

    Returns:
        Dict mapping trace_id to list of SessionNode objects.
    """
    traces: dict[str, list[SessionNode]] = {}

    if not sessions_dir.is_dir():
        return traces

    for path in sorted(sessions_dir.glob("*.json")):
        data = parse_session_file(path)
        if data is None:
            continue

        session = data.get("session", {})
        trace_id = session.get("traceId", "")
        if not trace_id:
            continue

        node = SessionNode(
            session_id=session_id_from_filename(path),
            trace_id=trace_id,
            parent_session_id=session.get("parentSessionId", ""),
            branch=session.get("branch", ""),
            objective=session.get("objective", ""),
            date=session.get("date", ""),
        )

        traces.setdefault(trace_id, []).append(node)

    return traces


def build_tree(nodes: list[SessionNode]) -> list[SessionNode]:
    """Build a tree from a flat list of nodes using parentSessionId links.

    Returns root nodes (those without a parent or whose parent is not in the set).
    """
    by_id: dict[str, SessionNode] = {n.session_id: n for n in nodes}
    roots: list[SessionNode] = []

    for node in nodes:
        if node.parent_session_id and node.parent_session_id in by_id:
            by_id[node.parent_session_id].children.append(node)
        else:
            roots.append(node)

    return roots


def format_text(roots: list[SessionNode], trace_id: str) -> str:
    """Render the call graph as an indented text tree."""
    lines: list[str] = [f"Trace: {trace_id}"]

    def walk(node: SessionNode, depth: int) -> None:
        prefix = "  " * depth + ("|- " if depth > 0 else "")
        lines.append(f"{prefix}{node.session_id}: {node.objective}")
        for child in node.children:
            walk(child, depth + 1)

    for root in roots:
        walk(root, 0)

    return "\n".join(lines)


def format_json(roots: list[SessionNode], trace_id: str) -> str:
    """Render the call graph as JSON."""

    def to_dict(node: SessionNode) -> dict[str, Any]:
        result: dict[str, Any] = {
            "sessionId": node.session_id,
            "traceId": node.trace_id,
            "date": node.date,
            "branch": node.branch,
            "objective": node.objective,
        }
        if node.parent_session_id:
            result["parentSessionId"] = node.parent_session_id
        if node.children:
            result["children"] = [to_dict(c) for c in node.children]
        return result

    graph = {
        "traceId": trace_id,
        "roots": [to_dict(r) for r in roots],
    }
    return json.dumps(graph, indent=2)


def format_mermaid(roots: list[SessionNode], trace_id: str) -> str:
    """Render the call graph as a Mermaid flowchart."""
    lines: list[str] = ["graph TD", f"    %% Trace: {trace_id}"]

    def sanitize(s: str) -> str:
        return s.replace('"', "'").replace("\n", " ")[:60]

    def walk(node: SessionNode) -> None:
        node_label = sanitize(node.objective) if node.objective else node.session_id
        lines.append(f'    {node.session_id}["{node_label}"]')
        for child in node.children:
            lines.append(f"    {node.session_id} --> {child.session_id}")
            walk(child)

    for root in roots:
        walk(root)

    return "\n".join(lines)


FORMATTERS = {
    "text": format_text,
    "json": format_json,
    "mermaid": format_mermaid,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--trace-id",
        default="",
        help="Filter to a specific trace ID. If omitted, shows all traces.",
    )
    parser.add_argument(
        "--format",
        choices=list(FORMATTERS.keys()),
        default="text",
        help="Output format (default: text).",
    )
    parser.add_argument(
        "--sessions-dir",
        type=Path,
        default=_SESSIONS_DIR,
        help="Path to sessions directory.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    sessions_dir: Path = args.sessions_dir

    # Security: Prevent path traversal. Resolve the path to its canonical form.
    # For command-line tools, absolute paths outside the project root are allowed,
    # relying on OS permissions for access control.
    resolved_sessions_dir = sessions_dir.resolve()

    if not resolved_sessions_dir.is_dir():
        print(
            f"Error: Sessions directory not found or is not a directory: {resolved_sessions_dir}",
            file=sys.stderr,
        )
        return 2

    traces = collect_traced_sessions(resolved_sessions_dir)

    if not traces:
        print("No traced sessions found.", file=sys.stderr)
        return 1

    target_trace_id: str = args.trace_id
    formatter = FORMATTERS[args.format]

    if target_trace_id:
        if target_trace_id not in traces:
            print(f"Trace ID not found: {target_trace_id}", file=sys.stderr)
            return 1
        roots = build_tree(traces[target_trace_id])
        print(formatter(roots, target_trace_id))
    else:
        for trace_id, nodes in traces.items():
            roots = build_tree(nodes)
            print(formatter(roots, trace_id))
            print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
