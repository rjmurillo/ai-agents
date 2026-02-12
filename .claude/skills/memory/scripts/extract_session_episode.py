#!/usr/bin/env python3
"""Extract episode data from session logs for the reflexion memory system.

Parses session log markdown files and extracts structured episode data
per ADR-038. Extraction targets: session metadata, decisions, events,
metrics, and lessons learned.

Exit codes follow ADR-035:
    0 - Success
    1 - Logic error (invalid session log or extraction failed)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def get_session_id_from_path(path: Path) -> str:
    """Extract session ID from log file path."""
    stem = path.stem
    match = re.search(r'(\d{4}-\d{2}-\d{2}-session-\d+)', stem)
    if match:
        return match.group(1)
    match = re.search(r'(session-\d+)', stem)
    if match:
        return match.group(1)
    return stem


def parse_session_metadata(lines: list[str]) -> dict:
    """Extract metadata from session log header."""
    metadata: dict = {
        "title": "",
        "date": "",
        "status": "",
        "objectives": [],
        "deliverables": [],
    }
    in_section = ""

    for line in lines:
        # Title (first H1)
        title_match = re.match(r'^#\s+(.+)$', line)
        if title_match and not metadata["title"]:
            metadata["title"] = title_match.group(1)
            continue

        # Date field
        m = re.match(r'^\*\*Date\*\*:\s*(.+)$', line)
        if m:
            metadata["date"] = m.group(1).strip()
            continue

        # Status field
        m = re.match(r'^\*\*Status\*\*:\s*(.+)$', line)
        if m:
            metadata["status"] = m.group(1).strip()
            continue

        # Objectives section
        if re.match(r'^##\s*Objectives?', line):
            in_section = "objectives"
            continue

        # Deliverables section
        if re.match(r'^##\s*Deliverables?', line):
            in_section = "deliverables"
            continue

        # New section ends current
        if re.match(r'^##\s', line):
            in_section = ""
            continue

        # Collect list items
        m = re.match(r'^\s*[-*]\s+(.+)$', line)
        if m:
            item = m.group(1).strip()
            if in_section == "objectives":
                metadata["objectives"].append(item)
            elif in_section == "deliverables":
                metadata["deliverables"].append(item)

    return metadata


def get_decision_type(text: str) -> str:
    """Categorize decision type from text."""
    lower = text.lower()
    if re.search(r'design|architect|schema|structure', lower):
        return "design"
    if re.search(r'test|pester|coverage|assert', lower):
        return "test"
    if re.search(r'recover|fix|retry|fallback', lower):
        return "recovery"
    if re.search(r'route|delegate|agent|handoff', lower):
        return "routing"
    return "implementation"


def parse_decisions(lines: list[str]) -> list[dict[str, Any]]:
    """Extract decisions from session log."""
    decisions: list[dict[str, Any]] = []
    decision_index = 0
    in_decision_section = False
    now_iso = datetime.now(UTC).isoformat()

    for i, line in enumerate(lines):
        if re.match(r'^##\s*Decisions?', line):
            in_decision_section = True
            continue

        if in_decision_section and re.match(r'^##\s', line):
            in_decision_section = False

        # Decision patterns in various formats
        decision_text = None
        m1 = re.match(r'^\*\*Decision\*\*:\s*(.+)$', line)
        m2 = re.match(r'^Decision:\s*(.+)$', line)
        m3 = (
            re.match(r'^\s*[-*]\s+\*\*(.+?)\*\*:\s*(.+)$', line)
            if in_decision_section
            else None
        )

        if m1:
            decision_text = m1.group(1)
        elif m2:
            decision_text = m2.group(1)
        elif m3:
            decision_text = f"{m3.group(1)}: {m3.group(2)}"

        if decision_text:
            decision_index += 1
            context = ""
            if i > 0:
                ctx_match = re.match(r'^\s*[-*]\s+(.+)$', lines[i - 1])
                if ctx_match:
                    context = ctx_match.group(1)

            decisions.append({
                "id": f"d{decision_index:03d}",
                "timestamp": now_iso,
                "type": get_decision_type(decision_text),
                "context": context,
                "chosen": decision_text,
                "rationale": "",
                "outcome": "success",
                "effects": [],
            })
            continue

        # Capture decisions from work log entries
        if (
            re.search(r'chose|decided|selected|opted for', line)
            and not line.startswith('#')
        ):
            decision_index += 1
            decisions.append({
                "id": f"d{decision_index:03d}",
                "timestamp": now_iso,
                "type": "implementation",
                "context": "",
                "chosen": line.strip(),
                "rationale": "",
                "outcome": "success",
                "effects": [],
            })

    return decisions


def parse_events(lines: list[str]) -> list[dict]:
    """Extract events from session log."""
    events = []
    event_index = 0
    now_iso = datetime.now(UTC).isoformat()

    for line in lines:
        evt = None

        # Commit events
        m = re.search(r'commit[ted]?\s+(?:as\s+)?([a-f0-9]{7,40})', line)
        if not m:
            m = re.search(r'([a-f0-9]{7,40})\s+\w+\(.+\):', line)
        if m:
            event_index += 1
            evt = {
                "id": f"e{event_index:03d}",
                "timestamp": now_iso,
                "type": "commit",
                "content": f"Commit: {m.group(1)}",
                "caused_by": [],
                "leads_to": [],
            }

        # Error events
        if (
            re.search(r'error|fail|exception', line, re.IGNORECASE)
            and not line.startswith('#')
        ):
            event_index += 1
            evt = {
                "id": f"e{event_index:03d}",
                "timestamp": now_iso,
                "type": "error",
                "content": line.strip(),
                "caused_by": [],
                "leads_to": [],
            }

        # Milestone events
        if (
            re.search(r'completed?|done|finished|success', line, re.IGNORECASE)
            and re.match(r'^[-*]\s+(?!\*)', line)
        ):
            event_index += 1
            content = re.sub(r'^[-*]\s*', '', line.strip())
            evt = {
                "id": f"e{event_index:03d}",
                "timestamp": now_iso,
                "type": "milestone",
                "content": content,
                "caused_by": [],
                "leads_to": [],
            }

        # Test events
        if re.search(r'test[s]?\s+(pass|fail|run)', line, re.IGNORECASE) or 'Pester' in line:
            event_index += 1
            evt = {
                "id": f"e{event_index:03d}",
                "timestamp": now_iso,
                "type": "test",
                "content": line.strip(),
                "caused_by": [],
                "leads_to": [],
            }

        if evt:
            events.append(evt)

    return events


def parse_lessons(lines: list[str]) -> list[str]:
    """Extract lessons learned from session log."""
    lessons = []
    in_lessons_section = False

    for line in lines:
        if re.match(r'^##\s*(Lessons?\s*Learned?|Key\s*Learnings?|Takeaways?)', line):
            in_lessons_section = True
            continue

        if in_lessons_section and re.match(r'^##\s', line):
            in_lessons_section = False

        m = re.match(r'^\s*[-*]\s+(.+)$', line)
        if in_lessons_section and m:
            lessons.append(m.group(1).strip())
        elif (
            re.search(r'lesson|learned|takeaway|note for future', line, re.IGNORECASE)
            and not line.startswith('#')
        ):
            lessons.append(line.strip())

    return list(dict.fromkeys(lessons))


def parse_metrics(lines: list[str]) -> dict:
    """Extract metrics from session log."""
    metrics = {
        "duration_minutes": 0,
        "tool_calls": 0,
        "errors": 0,
        "recoveries": 0,
        "commits": 0,
        "files_changed": 0,
    }

    for line in lines:
        # Duration
        m = re.search(r'(\d+)\s*minutes?', line)
        if not m:
            m = re.search(r'duration:\s*(\d+)', line, re.IGNORECASE)
        if m:
            metrics["duration_minutes"] = int(m.group(1))

        # Count commits
        if re.search(r'[a-f0-9]{7,40}', line):
            metrics["commits"] += 1

        # Count errors
        if (
            re.search(r'error|fail|exception', line, re.IGNORECASE)
            and not line.startswith('#')
        ):
            metrics["errors"] += 1

        # Count files
        m = re.search(r'(\d+)\s+files?\s+(changed|modified|created)', line)
        if m:
            metrics["files_changed"] += int(m.group(1))

    return metrics


def get_session_outcome(metadata: dict, events: list[dict]) -> str:
    """Determine overall session outcome."""
    status = (metadata.get("status") or "").lower()

    if re.search(r'complete|done|success', status):
        return "success"
    if re.search(r'partial|in.?progress|blocked', status):
        return "partial"
    if re.search(r'fail|abort|error', status):
        return "failure"

    error_count = sum(1 for e in events if e.get("type") == "error")
    milestone_count = sum(1 for e in events if e.get("type") == "milestone")

    if error_count > milestone_count:
        return "failure"
    if milestone_count > 0:
        return "success"
    return "partial"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extract episode data from session logs.",
    )
    parser.add_argument(
        "session_log_path", type=Path,
        help="Path to the session log file to extract from",
    )
    parser.add_argument(
        "--output-path", type=Path, default=None,
        help="Output directory for episode JSON",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Overwrite existing episode file if it exists",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    session_log_path = args.session_log_path

    if not session_log_path.is_file():
        print(
            json.dumps({"Error": f"Session log not found: {session_log_path}"}),
            file=sys.stderr,
        )
        return 1

    # Determine output path
    if args.output_path:
        output_path = args.output_path
    else:
        script_dir = Path(__file__).resolve().parent
        output_path = (
            script_dir.parent.parent.parent.parent
            / ".agents" / "memory" / "episodes"
        )

    # Read session log
    try:
        content = session_log_path.read_text(encoding="utf-8")
    except OSError as e:
        print(
            json.dumps({
                "Error": f"Failed to read session log: {e}",
            }),
            file=sys.stderr,
        )
        return 1

    lines = content.splitlines()
    session_id = get_session_id_from_path(session_log_path)

    print(f"Extracting episode from: {session_log_path}", file=sys.stderr)

    # Parse components
    print("  Parsing metadata...", file=sys.stderr)
    metadata = parse_session_metadata(lines)

    print("  Parsing decisions...", file=sys.stderr)
    decisions = parse_decisions(lines)

    print("  Parsing events...", file=sys.stderr)
    events = parse_events(lines)

    print("  Parsing lessons...", file=sys.stderr)
    lessons = parse_lessons(lines)

    print("  Parsing metrics...", file=sys.stderr)
    metrics = parse_metrics(lines)

    # Determine outcome
    outcome = get_session_outcome(metadata, events)

    # Parse timestamp
    timestamp = datetime.now(UTC).isoformat()
    if metadata.get("date"):
        try:
            parsed = datetime.fromisoformat(metadata["date"])
            timestamp = parsed.isoformat()
        except ValueError:
            print(
                f"  WARNING: Could not parse date '{metadata['date']}', "
                "using current time",
                file=sys.stderr,
            )

    # Build episode
    task = (
        metadata["objectives"][0]
        if metadata["objectives"]
        else metadata["title"]
    )
    episode = {
        "id": f"episode-{session_id}",
        "session": session_id,
        "timestamp": timestamp,
        "outcome": outcome,
        "task": task,
        "decisions": decisions,
        "events": events,
        "metrics": metrics,
        "lessons": lessons,
    }

    # Ensure output directory exists
    output_path.mkdir(parents=True, exist_ok=True)

    # Write episode file
    episode_file = output_path / f"episode-{session_id}.json"

    if episode_file.exists() and not args.force:
        print(
            json.dumps({
                "Error": f"Episode file already exists: {episode_file}. Use --force to overwrite.",
            }),
            file=sys.stderr,
        )
        return 1

    try:
        episode_file.write_text(
            json.dumps(episode, indent=2) + "\n",
            encoding="utf-8",
        )
    except OSError as e:
        print(
            json.dumps({"Error": f"Failed to write episode file: {e}"}),
            file=sys.stderr,
        )
        return 1

    # Summary
    print("\nEpisode extracted:", file=sys.stderr)
    print(f"  ID:        {episode['id']}", file=sys.stderr)
    print(f"  Session:   {session_id}", file=sys.stderr)
    print(f"  Outcome:   {outcome}", file=sys.stderr)
    print(f"  Decisions: {len(decisions)}", file=sys.stderr)
    print(f"  Events:    {len(events)}", file=sys.stderr)
    print(f"  Lessons:   {len(lessons)}", file=sys.stderr)
    print(f"  Output:    {episode_file}", file=sys.stderr)

    # Output episode JSON to stdout for pipeline usage
    print(json.dumps(episode, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
