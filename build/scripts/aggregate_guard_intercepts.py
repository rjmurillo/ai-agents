#!/usr/bin/env python3
"""Aggregate push-guard EVENT lines into a per-guard summary.

Consumes telemetry written by ``push_guard_base.py`` (one JSON object
per line, ``EVENT=`` prefix optional) and emits a JSON summary keyed by
guard name. The summary feeds ``classify_guard_maturity.py``.

Sources:

1. Directory (default ``.agents/telemetry/*.jsonl``).
2. STDIN piped from a one-shot ``git push 2>&1`` capture.
3. Explicit ``--source <file_or_dir>``.

Aggregator is lenient: malformed lines are silently skipped (return None
from ``_parse_event_line``); they never raise. Volume is expected to be
high enough that warning per-line would be noise; the test suite asserts
the silent-skip contract. ``--guard <name>`` lets a caller include a guard
in the output even when it had zero events (so the classifier can mark
it Inert).

Per-guard summary fields: total_events, blocks, fail_opens, block_rate,
fail_open_rate, first_event, last_event, days_since_first_event,
days_since_last_event.

Hook Maturity Model fitness is computed downstream; this script stays
pure aggregation so its output is cacheable and replayable.

Exit codes (per AGENTS.md):
    0 = ok
    1 = logic error (no events and no --guard)
    2 = config error (bad --now or unreadable --source)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_SOURCE = REPO_ROOT / ".agents" / "telemetry"
EVENT_PREFIX = "EVENT="


def _parse_event_line(line: str) -> dict | None:
    """Return parsed event dict or None for malformed input."""
    raw = line.strip()
    if not raw:
        return None
    if raw.startswith(EVENT_PREFIX):
        raw = raw[len(EVENT_PREFIX):]
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    if "guard" not in payload or "outcome" not in payload:
        return None
    return payload


def _events_from_path(source: Path) -> list[tuple[dict, datetime]]:
    """Yield (event, timestamp) tuples from a file or directory."""
    files: list[Path] = []
    if source.is_dir():
        files.extend(sorted(source.glob("*.jsonl")))
    elif source.is_file():
        files.append(source)
    else:
        print(f"warning: source not found: {source}", file=sys.stderr)
        return []
    out: list[tuple[dict, datetime]] = []
    for fp in files:
        try:
            mtime = datetime.fromtimestamp(fp.stat().st_mtime, tz=timezone.utc)
        except OSError:
            mtime = datetime.now(tz=timezone.utc)
        try:
            with fp.open("r", encoding="utf-8") as fh:
                for line in fh:
                    event = _parse_event_line(line)
                    if event is None:
                        continue
                    ts = _event_timestamp(event, mtime)
                    out.append((event, ts))
        except OSError as exc:
            print(f"warning: cannot read {fp}: {exc}", file=sys.stderr)
            continue
    return out


def _events_from_stdin() -> list[tuple[dict, datetime]]:
    """Read EVENT= lines from stdin; non-event lines are ignored."""
    if sys.stdin.isatty():
        return []
    now = datetime.now(tz=timezone.utc)
    out: list[tuple[dict, datetime]] = []
    for line in sys.stdin:
        if EVENT_PREFIX not in line:
            continue
        idx = line.find(EVENT_PREFIX)
        event = _parse_event_line(line[idx:])
        if event is None:
            continue
        out.append((event, _event_timestamp(event, now)))
    return out


def _event_timestamp(event: dict, fallback: datetime) -> datetime:
    raw = event.get("timestamp")
    if not isinstance(raw, str):
        return fallback
    try:
        # Accept both Z-suffix and +00:00 ISO forms.
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return fallback


def aggregate(events: list[tuple[dict, datetime]], extra_guards: list[str], now: datetime) -> dict:
    """Reduce events to per-guard summary."""
    summary: dict[str, dict] = {}
    for guard in extra_guards:
        summary.setdefault(guard, _empty_summary(guard))
    for event, ts in events:
        guard = event.get("guard")
        if not isinstance(guard, str) or not guard:
            continue
        s = summary.setdefault(guard, _empty_summary(guard))
        s["total_events"] += 1
        outcome = event.get("outcome")
        if outcome == "block":
            s["blocks"] += 1
        elif outcome == "fail_open":
            s["fail_opens"] += 1
        if s["_first_dt"] is None or ts < s["_first_dt"]:
            s["_first_dt"] = ts
        if s["_last_dt"] is None or ts > s["_last_dt"]:
            s["_last_dt"] = ts
    for s in summary.values():
        _finalize_summary(s, now)
    return summary


def _empty_summary(guard: str) -> dict:
    return {
        "guard": guard,
        "total_events": 0,
        "blocks": 0,
        "fail_opens": 0,
        "block_rate": 0.0,
        "fail_open_rate": 0.0,
        "first_event": None,
        "last_event": None,
        "days_since_first_event": None,
        "days_since_last_event": None,
        "_first_dt": None,
        "_last_dt": None,
    }


def _finalize_summary(s: dict, now: datetime) -> None:
    total = s["total_events"]
    if total > 0:
        s["block_rate"] = s["blocks"] / total
        s["fail_open_rate"] = s["fail_opens"] / total
    first_dt = s.pop("_first_dt")
    last_dt = s.pop("_last_dt")
    if first_dt is not None:
        s["first_event"] = first_dt.isoformat()
        s["days_since_first_event"] = max(0.0, (now - first_dt).total_seconds() / 86400.0)
    if last_dt is not None:
        s["last_event"] = last_dt.isoformat()
        s["days_since_last_event"] = max(0.0, (now - last_dt).total_seconds() / 86400.0)


def _build_argparser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Aggregate push-guard EVENT lines into a per-guard summary.",
    )
    parser.add_argument(
        "--source",
        default=None,
        help=("File or directory of EVENT JSONL. Defaults to "
              ".agents/telemetry/ when present, else stdin."),
    )
    parser.add_argument(
        "--stdin",
        action="store_true",
        help="Read EVENT= lines from stdin (overrides --source).",
    )
    parser.add_argument(
        "--guard",
        action="append",
        default=[],
        help=("Include this guard name in the output even if it had zero "
              "events. Repeatable. Useful for marking Inert guards."),
    )
    parser.add_argument(
        "--now",
        default=None,
        help=("Override 'now' for age math (ISO 8601). Used by tests so "
              "fixtures produce stable output."),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_argparser()
    args = parser.parse_args(argv)

    if args.now:
        try:
            now = datetime.fromisoformat(args.now.replace("Z", "+00:00"))
        except ValueError:
            print(f"error: invalid --now: {args.now}", file=sys.stderr)
            return 2
    else:
        now = datetime.now(tz=timezone.utc)

    if args.stdin:
        events = _events_from_stdin()
    elif args.source:
        events = _events_from_path(Path(args.source))
    elif DEFAULT_SOURCE.exists():
        events = _events_from_path(DEFAULT_SOURCE)
    elif not sys.stdin.isatty():
        events = _events_from_stdin()
    else:
        print(
            f"warning: default telemetry source not found: {DEFAULT_SOURCE}; "
            "no events to aggregate (use --source or --stdin).",
            file=sys.stderr,
        )
        events = []

    summary = aggregate(events, args.guard, now)
    if not summary:
        print(
            "error: no guards found and no --guard listed; nothing to summarize.",
            file=sys.stderr,
        )
        return 1
    json.dump(summary, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write(os.linesep)
    return 0


if __name__ == "__main__":
    sys.exit(main())
