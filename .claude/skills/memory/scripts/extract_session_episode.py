#!/usr/bin/env python3
"""Extract episode data from session logs.

Parses session log markdown files and extracts structured episode data
for the reflexion memory system per ADR-038.

Extraction targets:
- Session metadata (date, objectives, status)
- Decisions made during the session
- Events (commits, errors, milestones)
- Metrics (duration, file counts)
- Lessons learned

Exit Codes:
    0  - Success: Episode extracted
    1  - Error: Invalid session log or extraction failed

See: ADR-035 Exit Code Standardization
"""

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path


def get_session_id_from_path(path: str) -> str:
    """Extract session ID from log file path."""
    file_name = Path(path).stem
    match = re.search(r"(\d{4}-\d{2}-\d{2}-session-\d+)", file_name)
    if match:
        return match.group(1)
    match = re.search(r"(session-\d+)", file_name)
    if match:
        return match.group(1)
    return file_name


def parse_metadata(lines: list[str]) -> dict:
    """Extract metadata from session log header."""
    metadata = {
        "title": "",
        "date": "",
        "status": "",
        "objectives": [],
        "deliverables": [],
    }
    in_section = ""

    for line in lines:
        if re.match(r"^#\s+(.+)$", line) and not metadata["title"]:
            metadata["title"] = re.match(r"^#\s+(.+)$", line).group(1)
            continue

        m = re.match(r"^\*\*Date\*\*:\s*(.+)$", line)
        if m:
            metadata["date"] = m.group(1).strip()
            continue

        m = re.match(r"^\*\*Status\*\*:\s*(.+)$", line)
        if m:
            metadata["status"] = m.group(1).strip()
            continue

        if re.match(r"^##\s*Objectives?", line):
            in_section = "objectives"
            continue
        if re.match(r"^##\s*Deliverables?", line):
            in_section = "deliverables"
            continue
        if re.match(r"^##\s", line):
            in_section = ""
            continue

        m = re.match(r"^\s*[-*]\s+(.+)$", line)
        if m and in_section in ("objectives", "deliverables"):
            metadata[in_section].append(m.group(1).strip())

    return metadata


def get_decision_type(text: str) -> str:
    """Categorize decision type from text."""
    lower = text.lower()
    if re.search(r"design|architect|schema|structure", lower):
        return "design"
    if re.search(r"test|pester|coverage|assert", lower):
        return "test"
    if re.search(r"recover|fix|retry|fallback", lower):
        return "recovery"
    if re.search(r"route|delegate|agent|handoff", lower):
        return "routing"
    return "implementation"


def parse_decisions(lines: list[str]) -> list[dict]:
    """Extract decisions from session log."""
    decisions: list[dict] = []
    decision_index = 0
    in_decision_section = False

    for i, line in enumerate(lines):
        if re.match(r"^##\s*Decisions?", line):
            in_decision_section = True
            continue
        if in_decision_section and re.match(r"^##\s", line):
            in_decision_section = False

        decision_text = None
        m = re.match(r"^\*\*Decision\*\*:\s*(.+)$", line)
        if m:
            decision_text = m.group(1)
        if not decision_text:
            m = re.match(r"^Decision:\s*(.+)$", line)
            if m:
                decision_text = m.group(1)
        if not decision_text and in_decision_section:
            m = re.match(r"^\s*[-*]\s+\*\*(.+?)\*\*:\s*(.+)$", line)
            if m:
                decision_text = f"{m.group(1)}: {m.group(2)}"

        if decision_text:
            decision_index += 1
            context = ""
            if i > 0:
                prev_m = re.match(r"^\s*[-*]\s+(.+)$", lines[i - 1])
                if prev_m:
                    context = prev_m.group(1)

            decisions.append({
                "id": f"d{decision_index:03d}",
                "timestamp": datetime.now().isoformat(),
                "type": get_decision_type(decision_text),
                "context": context,
                "chosen": decision_text,
                "rationale": "",
                "outcome": "success",
                "effects": [],
            })
            continue

        if re.search(r"chose|decided|selected|opted for", line) and not line.startswith("#"):
            decision_index += 1
            decisions.append({
                "id": f"d{decision_index:03d}",
                "timestamp": datetime.now().isoformat(),
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
    events: list[dict] = []
    event_index = 0

    for line in lines:
        evt = None

        if re.search(r"commit(?:ted)?\s+(?:as\s+)?([a-f0-9]{7,40})", line):
            m = re.search(r"commit(?:ted)?\s+(?:as\s+)?([a-f0-9]{7,40})", line)
            event_index += 1
            evt = {
                "id": f"e{event_index:03d}",
                "timestamp": datetime.now().isoformat(),
                "type": "commit",
                "content": f"Commit: {m.group(1)}",
                "caused_by": [],
                "leads_to": [],
            }
        elif re.search(r"([a-f0-9]{7,40})\s+\w+\(.+\):", line):
            m = re.search(r"([a-f0-9]{7,40})\s+\w+\(.+\):", line)
            event_index += 1
            evt = {
                "id": f"e{event_index:03d}",
                "timestamp": datetime.now().isoformat(),
                "type": "commit",
                "content": f"Commit: {m.group(1)}",
                "caused_by": [],
                "leads_to": [],
            }

        if re.search(r"error|fail|exception", line, re.IGNORECASE) and not line.startswith("#"):
            event_index += 1
            evt = {
                "id": f"e{event_index:03d}",
                "timestamp": datetime.now().isoformat(),
                "type": "error",
                "content": line.strip(),
                "caused_by": [],
                "leads_to": [],
            }

        if (re.search(r"completed?|done|finished|success", line, re.IGNORECASE)
                and re.match(r"^[-*]\s+(?!\*)", line)):
            event_index += 1
            evt = {
                "id": f"e{event_index:03d}",
                "timestamp": datetime.now().isoformat(),
                "type": "milestone",
                "content": re.sub(r"^[-*]\s*", "", line.strip()),
                "caused_by": [],
                "leads_to": [],
            }

        if re.search(r"tests?\s+(pass|fail|run)", line, re.IGNORECASE) or "Pester" in line:
            event_index += 1
            evt = {
                "id": f"e{event_index:03d}",
                "timestamp": datetime.now().isoformat(),
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
    lessons: list[str] = []
    in_lessons_section = False

    for line in lines:
        if re.match(r"^##\s*(Lessons?\s*Learned?|Key\s*Learnings?|Takeaways?)", line):
            in_lessons_section = True
            continue
        if in_lessons_section and re.match(r"^##\s", line):
            in_lessons_section = False

        if in_lessons_section:
            m = re.match(r"^\s*[-*]\s+(.+)$", line)
            if m:
                lessons.append(m.group(1).strip())

        if re.search(r"lesson|learned|takeaway|note for future", line, re.IGNORECASE) and not line.startswith("#"):
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
        m = re.search(r"(\d+)\s*minutes?", line)
        if m:
            metrics["duration_minutes"] = int(m.group(1))
        m = re.search(r"duration:\s*(\d+)", line, re.IGNORECASE)
        if m:
            metrics["duration_minutes"] = int(m.group(1))

        if re.search(r"[a-f0-9]{7,40}", line):
            metrics["commits"] += 1

        if re.search(r"error|fail|exception", line, re.IGNORECASE) and not line.startswith("#"):
            metrics["errors"] += 1

        m = re.search(r"(\d+)\s+files?\s+(changed|modified|created)", line)
        if m:
            metrics["files_changed"] += int(m.group(1))

    return metrics


def get_session_outcome(metadata: dict, events: list[dict]) -> str:
    """Determine overall session outcome."""
    status = (metadata.get("status") or "").lower()

    if re.search(r"complete|done|success", status):
        return "success"
    if re.search(r"partial|in.?progress|blocked", status):
        return "partial"
    if re.search(r"fail|abort|error", status):
        return "failure"

    error_count = sum(1 for e in events if e.get("type") == "error")
    milestone_count = sum(1 for e in events if e.get("type") == "milestone")

    if error_count > milestone_count:
        return "failure"
    if milestone_count > 0:
        return "success"
    return "partial"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract episode data from session logs."
    )
    parser.add_argument("session_log_path", help="Path to session log file.")
    parser.add_argument(
        "--output-path", type=str, default="",
        help="Output directory for episode JSON."
    )
    parser.add_argument("--force", action="store_true", help="Overwrite existing.")
    args = parser.parse_args()

    session_log = Path(args.session_log_path)
    if not session_log.is_file():
        print(f"Session log not found: {session_log}", file=sys.stderr)
        sys.exit(1)

    if args.output_path:
        output_path = Path(args.output_path)
    else:
        output_path = Path(__file__).resolve().parent.parent.parent.parent.parent / ".agents" / "memory" / "episodes"

    print(f"Extracting episode from: {session_log}")

    try:
        lines = session_log.read_text(encoding="utf-8").splitlines()
    except Exception as e:
        print(f"Failed to read session log: {e}", file=sys.stderr)
        sys.exit(1)

    session_id = get_session_id_from_path(str(session_log))

    print("  Parsing metadata...")
    metadata = parse_metadata(lines)
    print("  Parsing decisions...")
    decisions = parse_decisions(lines)
    print("  Parsing events...")
    events = parse_events(lines)
    print("  Parsing lessons...")
    lessons = parse_lessons(lines)
    print("  Parsing metrics...")
    metrics = parse_metrics(lines)

    outcome = get_session_outcome(metadata, events)

    timestamp = datetime.now().isoformat()
    if metadata.get("date"):
        try:
            timestamp = datetime.fromisoformat(metadata["date"]).isoformat()
        except ValueError:
            pass

    episode = {
        "id": f"episode-{session_id}",
        "session": session_id,
        "timestamp": timestamp,
        "outcome": outcome,
        "task": metadata["objectives"][0] if metadata["objectives"] else metadata["title"],
        "decisions": decisions,
        "events": events,
        "metrics": metrics,
        "lessons": lessons,
    }

    output_path.mkdir(parents=True, exist_ok=True)
    episode_file = output_path / f"episode-{session_id}.json"

    if episode_file.exists() and not args.force:
        print(f"Episode file already exists: {episode_file}", file=sys.stderr)
        print("Use --force to overwrite.", file=sys.stderr)
        sys.exit(1)

    episode_file.write_text(json.dumps(episode, indent=2), encoding="utf-8")

    print(f"\nEpisode extracted:")
    print(f"  ID:        {episode['id']}")
    print(f"  Session:   {session_id}")
    print(f"  Outcome:   {outcome}")
    print(f"  Decisions: {len(decisions)}")
    print(f"  Events:    {len(events)}")
    print(f"  Lessons:   {len(lessons)}")
    print(f"  Output:    {episode_file}")


if __name__ == "__main__":
    main()
