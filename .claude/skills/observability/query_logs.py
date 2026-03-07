#!/usr/bin/env python3
"""Query structured JSON log files for agent-legible observability.

Parses structured JSON log files (one JSON object per line) and filters
by time range, log level, service name, and free-text pattern.

EXIT CODES (ADR-035):
    0 - Success: Query completed, results printed as JSON
    1 - Error: Invalid arguments or file not found
    2 - Error: Invalid log format
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path


def parse_timestamp(value: str) -> datetime:
    """Parse ISO 8601 timestamp string to datetime."""
    value = value.strip()
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)


def matches_filters(
    entry: dict,
    *,
    level: str | None = None,
    service: str | None = None,
    pattern: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
) -> bool:
    """Check whether a log entry matches all provided filters."""
    if level and entry.get("level", "").upper() != level.upper():
        return False

    if service and entry.get("service", "") != service:
        return False

    if since or until:
        ts_raw = entry.get("timestamp") or entry.get("ts") or entry.get("time")
        if not ts_raw:
            return False
        try:
            ts = parse_timestamp(str(ts_raw))
        except (ValueError, TypeError):
            return False
        if since and ts < since:
            return False
        if until and ts > until:
            return False

    if pattern:
        message = entry.get("message") or entry.get("msg") or ""
        if not re.search(pattern, message, re.IGNORECASE):
            return False

    return True


def query_log_file(
    path: Path,
    *,
    level: str | None = None,
    service: str | None = None,
    pattern: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = 100,
) -> list[dict]:
    """Read a JSON-lines log file and return matching entries."""
    results: list[dict] = []
    with path.open(encoding="utf-8") as fh:
        for line_num, raw_line in enumerate(fh, start=1):
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            try:
                entry = json.loads(raw_line)
            except json.JSONDecodeError:
                continue
            if not isinstance(entry, dict):
                continue
            if matches_filters(
                entry,
                level=level,
                service=service,
                pattern=pattern,
                since=since,
                until=until,
            ):
                entry["_source_line"] = line_num
                results.append(entry)
                if len(results) >= limit:
                    break
    return results


def query_metrics_file(path: Path) -> dict:
    """Read a JSON metrics file and return its contents."""
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        print(json.dumps({"error": "Metrics file must contain a JSON object"}))
        sys.exit(2)
    return data


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="Query structured JSON logs for agent observability.",
    )
    parser.add_argument(
        "path",
        type=Path,
        help="Path to a JSON-lines log file or JSON metrics file.",
    )
    parser.add_argument(
        "--level",
        choices=["DEBUG", "INFO", "WARN", "WARNING", "ERROR", "CRITICAL"],
        help="Filter by log level.",
    )
    parser.add_argument(
        "--service",
        help="Filter by service name.",
    )
    parser.add_argument(
        "--pattern",
        help="Regex pattern to match against message field.",
    )
    parser.add_argument(
        "--since",
        help="ISO 8601 timestamp lower bound (inclusive).",
    )
    parser.add_argument(
        "--until",
        help="ISO 8601 timestamp upper bound (inclusive).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Maximum entries to return (default: 100).",
    )
    parser.add_argument(
        "--metrics",
        action="store_true",
        help="Treat file as a JSON metrics snapshot instead of logs.",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Print a summary of log levels instead of full entries.",
    )
    return parser


def summarize(entries: list[dict]) -> dict:
    """Produce a level-count summary from log entries."""
    counts: dict[str, int] = {}
    for entry in entries:
        lvl = entry.get("level", "UNKNOWN").upper()
        counts[lvl] = counts.get(lvl, 0) + 1
    return {"total": len(entries), "by_level": counts}


def main(argv: list[str] | None = None) -> int:
    """Entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.path.exists():
        print(json.dumps({"error": f"File not found: {args.path}"}))
        return 1

    if args.metrics:
        result = query_metrics_file(args.path)
        print(json.dumps(result, indent=2, default=str))
        return 0

    since = parse_timestamp(args.since) if args.since else None
    until = parse_timestamp(args.until) if args.until else None

    entries = query_log_file(
        args.path,
        level=args.level,
        service=args.service,
        pattern=args.pattern,
        since=since,
        until=until,
        limit=args.limit,
    )

    if args.summary:
        print(json.dumps(summarize(entries), indent=2))
    else:
        print(json.dumps(entries, indent=2, default=str))

    return 0


if __name__ == "__main__":
    sys.exit(main())
