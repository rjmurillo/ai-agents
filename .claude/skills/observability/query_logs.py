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
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Maximum length for user-supplied regex patterns (CWE-400 ReDoS protection)
_MAX_PATTERN_LENGTH = 1000


def _get_workspace_root() -> Path:
    """Return the workspace root directory for path containment checks.

    Uses git rev-parse when available, falls back to the skill directory's
    ancestor (4 levels up from .claude/skills/observability/query_logs.py).
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
        return Path(result.stdout.strip()).resolve()
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        return Path(__file__).resolve().parents[3]


def validate_file_path(path: Path) -> Path:
    """Resolve and validate that a file path stays within the workspace root.

    Prevents CWE-22 path traversal by resolving symlinks and ensuring the
    canonical path is a descendant of the workspace root.

    Returns:
        The resolved Path.

    Raises:
        ValueError: If the resolved path escapes the workspace root.
    """
    workspace_root = _get_workspace_root()
    resolved = path.resolve()
    if not resolved.is_relative_to(workspace_root):
        raise ValueError(
            f"Path {path} resolves outside workspace root ({workspace_root})"
        )
    return resolved


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
        try:
            compiled = re.compile(pattern, re.IGNORECASE)
        except re.error:
            return False
        if not compiled.search(message):
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

    # CWE-22: Validate path stays within workspace root
    try:
        resolved_path = validate_file_path(args.path)
    except ValueError as exc:
        print(json.dumps({"error": str(exc)}))
        return 1

    if not resolved_path.exists():
        print(json.dumps({"error": f"File not found: {args.path}"}))
        return 1

    if args.metrics:
        result = query_metrics_file(resolved_path)
        print(json.dumps(result, indent=2, default=str))
        return 0

    # CWE-400: Validate pattern length and syntax before use
    if args.pattern:
        if len(args.pattern) > _MAX_PATTERN_LENGTH:
            print(json.dumps({
                "error": f"Pattern too long ({len(args.pattern)} chars, "
                         f"max {_MAX_PATTERN_LENGTH})",
            }))
            return 1
        try:
            re.compile(args.pattern)
        except re.error as exc:
            print(json.dumps({"error": f"Invalid regex pattern: {exc}"}))
            return 1

    since = parse_timestamp(args.since) if args.since else None
    until = parse_timestamp(args.until) if args.until else None

    entries = query_log_file(
        resolved_path,
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
