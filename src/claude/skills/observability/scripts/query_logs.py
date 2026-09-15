#!/usr/bin/env python3
"""Agent observability log query utility.

Parses and filters JSONL agent event logs for debugging and analysis.

EXIT CODES (ADR-035):
    0 - Success: Query completed and results output
    1 - Error: File not found or invalid arguments
    2 - Error: Invalid JSONL format
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def parse_event(line: str, line_number: int) -> dict | None:
    """Parse a single JSONL line into an event dict."""
    stripped = line.strip()
    if not stripped:
        return None
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        print(
            f"Warning: invalid JSON at line {line_number}, skipping",
            file=sys.stderr,
        )
        return None


def load_events(path: Path) -> list[dict]:
    """Load all events from a JSONL file."""
    events = []
    with open(path) as f:
        for i, line in enumerate(f, 1):
            event = parse_event(line, i)
            if event is not None:
                events.append(event)
    return events


def filter_events(
    events: list[dict],
    event_type: str | None = None,
    session_id: str | None = None,
    agent: str | None = None,
    level: str | None = None,
    tool_name: str | None = None,
    since: str | None = None,
    until: str | None = None,
    errors_only: bool = False,
    slow_threshold_ms: float | None = None,
) -> list[dict]:
    """Filter events by criteria."""
    filtered = []
    for event in events:
        if event_type and event.get("event_type") != event_type:
            continue
        if session_id and event.get("session_id") != session_id:
            continue
        if agent and event.get("agent") != agent:
            continue
        if level and event.get("level") != level:
            continue
        if tool_name:
            tool = event.get("tool")
            if not tool or tool.get("name") != tool_name:
                continue
        if errors_only and event.get("event_type") != "error":
            continue
        if since:
            ts = event.get("timestamp", "")
            if ts < since:
                continue
        if until:
            ts = event.get("timestamp", "")
            if ts > until:
                continue
        if slow_threshold_ms is not None:
            tool = event.get("tool")
            if not tool:
                continue
            duration = tool.get("duration_ms")
            if duration is None or duration < slow_threshold_ms:
                continue
        filtered.append(event)
    return filtered


def summarize_session(events: list[dict]) -> dict:
    """Produce a summary of events grouped by session."""
    sessions: dict[str, dict] = {}
    for event in events:
        sid = event.get("session_id", "unknown")
        if sid not in sessions:
            sessions[sid] = {
                "session_id": sid,
                "agent": event.get("agent", "unknown"),
                "event_count": 0,
                "tool_calls": 0,
                "decisions": 0,
                "errors": 0,
                "total_tool_duration_ms": 0.0,
                "first_event": event.get("timestamp", ""),
                "last_event": event.get("timestamp", ""),
            }
        s = sessions[sid]
        s["event_count"] += 1
        ts = event.get("timestamp", "")
        if ts and (not s["first_event"] or ts < s["first_event"]):
            s["first_event"] = ts
        if ts and ts > s["last_event"]:
            s["last_event"] = ts
        etype = event.get("event_type")
        if etype == "tool_call":
            s["tool_calls"] += 1
            duration = (event.get("tool") or {}).get("duration_ms", 0)
            s["total_tool_duration_ms"] += duration
        elif etype == "decision":
            s["decisions"] += 1
        elif etype == "error":
            s["errors"] += 1
    return {"sessions": list(sessions.values())}


def summarize_tools(events: list[dict]) -> dict:
    """Produce a summary of tool usage across events."""
    tools: dict[str, dict] = {}
    for event in events:
        if event.get("event_type") != "tool_call":
            continue
        tool = event.get("tool")
        if not tool:
            continue
        name = tool.get("name", "unknown")
        if name not in tools:
            tools[name] = {
                "name": name,
                "call_count": 0,
                "success_count": 0,
                "failure_count": 0,
                "total_duration_ms": 0.0,
                "max_duration_ms": 0.0,
            }
        t = tools[name]
        t["call_count"] += 1
        if tool.get("success", True):
            t["success_count"] += 1
        else:
            t["failure_count"] += 1
        duration = tool.get("duration_ms", 0)
        t["total_duration_ms"] += duration
        if duration > t["max_duration_ms"]:
            t["max_duration_ms"] = duration
    for t in tools.values():
        if t["call_count"] > 0:
            t["avg_duration_ms"] = round(
                t["total_duration_ms"] / t["call_count"], 1
            )
    return {"tools": sorted(tools.values(), key=lambda x: x["call_count"], reverse=True)}


def format_table(events: list[dict]) -> str:
    """Format events as a human-readable table."""
    if not events:
        return "No events found."
    lines = []
    hdr_ts = "Timestamp"
    hdr_type = "Type"
    hdr_agent = "Agent"
    lines.append(f"{hdr_ts:<26} {hdr_type:<14} {hdr_agent:<14} Details")
    lines.append("-" * 80)
    for event in events:
        ts = event.get("timestamp", "")[:25]
        etype = event.get("event_type", "")
        agent_name = event.get("agent", "")
        detail = ""
        if etype == "tool_call":
            tool = event.get("tool", {})
            dur = tool.get("duration_ms", "")
            tool_nm = tool.get("name", "")
            detail = f"{tool_nm} ({dur}ms)"
        elif etype == "decision":
            dec = event.get("decision", {})
            detail = dec.get("action", "")[:40]
        elif etype == "error":
            err = event.get("error", {})
            detail = err.get("message", "")[:40]
        elif etype == "metric":
            met = event.get("metric", {})
            met_name = met.get("name", "")
            met_val = met.get("value", "")
            detail = f"{met_name}={met_val}"
        else:
            detail = event.get("message", "")[:40]
        lines.append(f"{ts:<26} {etype:<14} {agent_name:<14} {detail}")
    return "\n".join(lines)


def main() -> int:
    """Entry point."""
    parser = argparse.ArgumentParser(
        description="Query agent observability logs (JSONL format)"
    )
    parser.add_argument("logfile", help="Path to JSONL log file")
    parser.add_argument("--event-type", help="Filter by event type")
    parser.add_argument("--session-id", help="Filter by session ID")
    parser.add_argument("--agent", help="Filter by agent name")
    parser.add_argument("--level", help="Filter by log level")
    parser.add_argument("--tool", dest="tool_name", help="Filter by tool name")
    parser.add_argument("--since", help="Filter events after this ISO timestamp")
    parser.add_argument("--until", help="Filter events before this ISO timestamp")
    parser.add_argument(
        "--errors-only", action="store_true", help="Show only error events"
    )
    parser.add_argument(
        "--slow",
        type=float,
        dest="slow_threshold_ms",
        help="Show tool calls slower than threshold (ms)",
    )
    parser.add_argument(
        "--output",
        choices=["json", "table", "summary-sessions", "summary-tools"],
        default="table",
        help="Output format",
    )
    args = parser.parse_args()

    path = Path(args.logfile)
    if not path.exists():
        print(f"Error: File not found: {args.logfile}", file=sys.stderr)
        return 1

    try:
        events = load_events(path)
    except Exception as e:
        print(f"Error reading log file: {e}", file=sys.stderr)
        return 2

    filtered = filter_events(
        events,
        event_type=args.event_type,
        session_id=args.session_id,
        agent=args.agent,
        level=args.level,
        tool_name=args.tool_name,
        since=args.since,
        until=args.until,
        errors_only=args.errors_only,
        slow_threshold_ms=args.slow_threshold_ms,
    )

    if args.output == "json":
        print(json.dumps(filtered, indent=2))
    elif args.output == "summary-sessions":
        print(json.dumps(summarize_session(filtered), indent=2))
    elif args.output == "summary-tools":
        print(json.dumps(summarize_tools(filtered), indent=2))
    else:
        print(format_table(filtered))

    return 0


if __name__ == "__main__":
    sys.exit(main())
