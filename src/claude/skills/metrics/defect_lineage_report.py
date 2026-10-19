#!/usr/bin/env python3
"""Render defect lineage records without calling a fixed finding live (issue #5638).

Records fall in four mutually exclusive buckets. Only ``live`` holds findings
that are present at the recorded SHA. ``historical`` keeps the mechanism evidence
of findings that no longer hold. ``unverified`` is a finding the last recheck
could not settle. ``observation`` is a follow-up chain that claims no defect,
such as planned work, so a follow-up is never labeled a defect by default.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Mapping, Sequence
from typing import Any

_here = os.path.dirname(os.path.abspath(__file__))
if _here not in sys.path:
    sys.path.insert(0, _here)

from defect_lineage_record import (  # noqa: E402
    detection_delay_seconds,
    repair_delay_seconds,
    require_valid,
)

BUCKETS = ("live", "unverified", "historical", "observation")
_TITLES = {
    "live": "Live findings at the recorded SHA",
    "unverified": "Unverified at the recorded SHA",
    "historical": "Historical mechanism evidence (not live)",
    "observation": "Observations (no defect claimed)",
}


def bucket_of(record: Mapping[str, Any]) -> str:
    """Return the report bucket for a valid record."""
    if record["supports"] == ["observation"]:
        return "observation"
    status = record["status"]
    if status in ("CURRENT", "REVERTED"):
        return "live"
    if status == "UNVERIFIED":
        return "unverified"
    return "historical"


def describe_delay(seconds: int) -> str:
    """State detection timing against the merge at seconds resolution."""
    if seconds > 0:
        return f"{seconds} s after merge"
    if seconds < 0:
        return f"{-seconds} s before merge"
    return "same second as merge (order not provable)"


def build_summary(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Validate records and group them. Raises LineageError on the first invalid one."""
    grouped: dict[str, list[dict[str, Any]]] = {name: [] for name in BUCKETS}
    for record in records:
        valid = require_valid(dict(record))
        grouped[bucket_of(valid)].append(_entry(valid))
    counts = {name: len(items) for name, items in grouped.items()}
    return {"counts": counts, "buckets": grouped}


def _entry(record: Mapping[str, Any]) -> dict[str, Any]:
    last = record["status_history"][-1]
    delay = detection_delay_seconds(record)
    return {
        "id": record["id"],
        "repository": record["repository"],
        "claim": record["claim"],
        "supports": record["supports"],
        "introduction_pr": record["introduction"]["pr"],
        "introduction_merged_at": record["introduction"]["merged_at"],
        "detection_source": record["detection"]["source"],
        "detection_at": record["detection"]["at"],
        "detection_delay_seconds": delay,
        "detection_timing": describe_delay(delay),
        "follow_up": record["follow_up"],
        "repair_delay_seconds": repair_delay_seconds(record),
        "status": record["status"],
        "live_sha": last["live_sha"],
        "checked_at": last["checked_at"],
        "basis": last["basis"],
        "history_length": len(record["status_history"]),
        "recheck_command": record["recheck"]["command"],
        "limitations": record["limitations"],
    }


def _follow_up_line(entry: Mapping[str, Any]) -> str:
    follow_up = entry["follow_up"]
    if not follow_up:
        return "- Follow-up: none recorded"
    merged = follow_up["merged_at"] or "not merged"
    line = f"- Follow-up: PR #{follow_up['pr']} ({follow_up['kind']}), merged {merged}"
    repair = entry["repair_delay_seconds"]
    return line if repair is None else f"{line}, {repair} s after detection"


def _render_entry(entry: Mapping[str, Any]) -> list[str]:
    lines = [
        f"### {entry['id']}",
        "",
        f"- Claim: {entry['claim']}",
        f"- Introduced: PR #{entry['introduction_pr']}, merged {entry['introduction_merged_at']}",
        f"- Detected: {entry['detection_source']} at {entry['detection_at']} "
        f"({entry['detection_timing']})",
        _follow_up_line(entry),
        f"- Evidence supports: {', '.join(entry['supports'])}",
        f"- Status: {entry['status']} at {entry['live_sha']} (checked {entry['checked_at']}, "
        f"{entry['history_length']} recorded checks)",
        f"- Basis: {entry['basis']}",
        f"- Recheck: `{entry['recheck_command']}`",
        "- Does not prove:",
    ]
    lines.extend(f"  - {item}" for item in entry["limitations"])
    lines.append("")
    return lines


def render_markdown(summary: Mapping[str, Any]) -> str:
    """Render the grouped summary. Every bucket prints, even when empty."""
    counts = summary["counts"]
    lines = ["# Defect lineage report", ""]
    lines.append("| Bucket | Records |")
    lines.append("|---|---|")
    lines.extend(f"| {_TITLES[name]} | {counts[name]} |" for name in BUCKETS)
    lines.append("")
    for name in BUCKETS:
        lines.extend([f"## {_TITLES[name]}", ""])
        entries = summary["buckets"][name]
        if not entries:
            lines.extend(["None.", ""])
        for entry in entries:
            lines.extend(_render_entry(entry))
    return "\n".join(lines).rstrip() + "\n"


def render_json(summary: Mapping[str, Any]) -> str:
    """Render the grouped summary as JSON."""
    return json.dumps(summary, indent=2, sort_keys=True) + "\n"
