#!/usr/bin/env python3
"""Extract episode data from session logs for the reflexion memory system.

Parses session logs and extracts structured episode data per ADR-038.
Extraction targets: session metadata, decisions, events, metrics, and lessons.

Session logs are JSON (see ``scripts/validate_session_json.py`` and the
``session-migration`` skill). The JSON path is primary: ``outcome`` is derived
from the ``protocolCompliance.sessionEnd`` MUST gates and events are typed from
the ``workLog`` structure, NOT from substring matching, which previously
mistyped every JSON line containing "fail"/"error" as an error event and forced
``outcome: failure`` (issue #2036). A legacy markdown path remains for the
older ``.md`` session logs still present in the archive; the format is detected
per file.

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
    if re.search(r'route|delegate|agent|handoff', lower):  # nosemgrep: skill-ldap-injection
        return "routing"
    return "implementation"


def parse_decisions(lines: list[str], timestamp: str | None = None) -> list[dict[str, Any]]:
    """Extract decisions from session log."""
    decisions: list[dict[str, Any]] = []
    decision_index = 0
    in_decision_section = False
    ts = timestamp if timestamp is not None else datetime.now(UTC).isoformat()

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
                "timestamp": ts,
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
                "timestamp": ts,
                "type": "implementation",
                "context": "",
                "chosen": line.strip(),
                "rationale": "",
                "outcome": "success",
                "effects": [],
            })

    return decisions


def parse_events(lines: list[str], timestamp: str | None = None) -> list[dict]:
    """Extract events from session log."""
    events = []
    event_index = 0
    ts = timestamp if timestamp is not None else datetime.now(UTC).isoformat()

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
                "timestamp": ts,
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
                "timestamp": ts,
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
                "timestamp": ts,
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
                "timestamp": ts,
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


# ---------------------------------------------------------------------------
# JSON session-log path (primary; schema: session / protocolCompliance /
# workLog / endingCommit). See scripts/validate_session_json.py.
# ---------------------------------------------------------------------------

# A counted failure ("3 failed", "2 errors") is a real failure signal; a bare
# substring "fails"/"error" inside prose is not. Requiring [1-9]\d* avoids the
# "0 errors" false positive that corrupted episodes under the markdown path.
_FAIL_COUNT_RE = re.compile(r"\b([1-9]\d*)\s+(?:failed|failures|errors?)\b", re.IGNORECASE)
_PASS_COUNT_RE = re.compile(r"\b(\d+)\s+(?:passed|passing)\b", re.IGNORECASE)
_SHA_RE = re.compile(r"\b[0-9a-f]{7,40}\b")
_FILES_RE = re.compile(r"\b(\d+)\s+files?\b", re.IGNORECASE)
_DECISION_RE = re.compile(
    r"\b(chose|decided|selected|opted|design decision|approach|reclassif)",
    re.IGNORECASE,
)


def _entry_field(entry: Any, key: str) -> str:
    """Return a work-log entry field, or '' when the entry is not a dict."""
    return str(entry.get(key, "")) if isinstance(entry, dict) else ""


def _entry_title(entry: Any) -> str:
    """Milestone content for a work-log entry: task, else action, else outcome.

    Work-log entries appear in three shapes across the log history: a bare
    string, ``{action, outcome}`` (older), and ``{task, outcome, evidence}``
    (newer). All three are handled; a string entry is its own title.
    """
    if isinstance(entry, str):
        return entry.strip()
    if isinstance(entry, dict):
        return str(entry.get("task") or entry.get("action") or entry.get("outcome") or "").strip()
    return ""


def _entry_text(entry: Any) -> str:
    """All free-text of a work-log entry, joined for signal detection."""
    if isinstance(entry, str):
        return entry
    if isinstance(entry, dict):
        return " ".join(str(entry.get(k, "")) for k in ("task", "action", "outcome", "evidence", "result"))
    return ""


def looks_like_json_session(content: str) -> dict[str, Any] | None:
    """Return the parsed object when content is a JSON session log, else None."""
    try:
        data = json.loads(content)
    except (json.JSONDecodeError, ValueError):
        return None
    if isinstance(data, dict) and "session" in data and "protocolCompliance" in data:
        return data
    return None


def _gate_complete(data: dict, phase: str, gate: str) -> bool:
    g = data.get("protocolCompliance", {}).get(phase, {}).get(gate, {})
    return isinstance(g, dict) and bool(g.get("Complete"))


def _collect_shas(data: dict, *, include_starting: bool) -> list[str]:
    """Distinct commit SHAs from the structured commit fields and work-log
    evidence. Excludes the starting commit by default (it is the base, not a
    commit the session produced)."""
    seen: list[str] = []
    fields = [str(data.get("endingCommit", ""))]
    if include_starting:
        fields.append(str(data.get("session", {}).get("startingCommit", "")))
    for entry in data.get("workLog", []):
        fields.append(_entry_text(entry))
    for field in fields:
        for sha in _SHA_RE.findall(field):
            if sha not in seen:
                seen.append(sha)
    return seen


def json_timestamp(data: dict) -> str:
    date = str(data.get("session", {}).get("date", "")).strip()
    if date:
        try:
            dt = datetime.fromisoformat(date)
            if dt.tzinfo is not None:
                return dt.astimezone(UTC).isoformat()
            return dt.replace(tzinfo=UTC).isoformat()
        except ValueError:
            pass
    return datetime.now(UTC).isoformat()


def json_outcome(data: dict) -> str:
    """Derive outcome from the session-end MUST gates and work-log results.

    The authoritative signal is the ``sessionEnd`` MUST gates: a session whose
    checklist, commit, and validation gates are all complete succeeded; an
    incomplete session is partial. ``failure`` requires an explicit counted
    failure in a work-log result AND an incomplete gate set, never a bare
    substring match.
    """
    must = ("checklistComplete", "changesCommitted", "validationPassed")
    all_complete = all(_gate_complete(data, "sessionEnd", g) for g in must)

    explicit_failure = any(
        _FAIL_COUNT_RE.search(_entry_text(e)) for e in data.get("workLog", [])
    )

    if explicit_failure and not all_complete:
        return "failure"
    return "success" if all_complete else "partial"


def json_events(data: dict, now_iso: str) -> list[dict]:
    """Type events from the work-log structure, not substring matching."""
    events: list[dict] = []
    idx = 0

    def add(evt_type: str, content: str) -> None:
        nonlocal idx
        idx += 1
        events.append({
            "id": f"e{idx:03d}",
            "timestamp": now_iso,
            "type": evt_type,
            "content": content,
            "caused_by": [],
            "leads_to": [],
        })

    for entry in data.get("workLog", []):
        title = _entry_title(entry)
        if title:
            add("milestone", title)
        text = _entry_text(entry)
        if _PASS_COUNT_RE.search(text):
            add("test", (_entry_field(entry, "evidence") or _entry_field(entry, "outcome") or text).strip())
        if _FAIL_COUNT_RE.search(text):
            add("error", text.strip())

    ending = str(data.get("endingCommit", ""))
    if _SHA_RE.fullmatch(ending.strip()):
        add("commit", f"Commit: {ending.strip()}")

    return events


def json_decisions(data: dict, now_iso: str) -> list[dict]:
    """Surface work-log entries that describe a choice as decisions."""
    decisions: list[dict] = []
    idx = 0
    for entry in data.get("workLog", []):
        text = _entry_text(entry)
        if not _DECISION_RE.search(text):
            continue
        title = _entry_title(entry)
        outcome = _entry_field(entry, "outcome").strip()
        idx += 1
        decisions.append({
            "id": f"d{idx:03d}",
            "timestamp": now_iso,
            "type": get_decision_type(text),
            "context": title,
            "chosen": outcome or title,
            "rationale": _entry_field(entry, "evidence").strip(),
            "outcome": "success",
            "effects": [],
        })
    return decisions


def json_metrics(data: dict) -> dict:
    ending = str(data.get("endingCommit", "")).strip()
    commit_count = 1 if _SHA_RE.fullmatch(ending) else 0
    metrics = {
        "duration_minutes": 0,
        "tool_calls": 0,
        "errors": 0,
        "recoveries": 0,
        "commits": commit_count,
        "files_changed": 0,
    }
    for entry in data.get("workLog", []):
        text = _entry_text(entry)
        fail = _FAIL_COUNT_RE.search(text)
        if fail:
            metrics["errors"] += int(fail.group(1))
        files = _FILES_RE.search(text)
        if files:
            metrics["files_changed"] += int(files.group(1))
    return metrics


def _json_lessons(data: dict) -> list[str]:
    """Extract lessons/learnings from JSON session log."""
    raw = data.get("learnings", [])
    if not isinstance(raw, list):
        return []
    lessons: list[str] = []
    for item in raw:
        if isinstance(item, str):
            lessons.append(item.strip())
        elif isinstance(item, dict):
            text = str(item.get("text") or item.get("content") or item.get("lesson") or "").strip()
            if text:
                lessons.append(text)
    return lessons


def _find_archive_file(session_id: str, extension: str) -> Path | None:
    """Find an archive file for a session ID with the given extension.

    Searches both `.agents/archive/sessions/` and `.agents/archive/session/`
    for files matching the session ID pattern. Returns the shortest-named match
    (preferring exact matches) to ensure deterministic selection across platforms.
    """
    script_dir = Path(__file__).resolve().parent
    base_archive = script_dir.parent.parent.parent.parent / ".agents" / "archive"
    archive_dirs = [base_archive / "sessions", base_archive / "session"]
    pattern = f"{session_id}*.{extension}"
    for archive_dir in archive_dirs:
        if not archive_dir.is_dir():
            continue
        matches = list(archive_dir.glob(pattern))
        if matches:
            matches.sort(key=lambda p: (len(p.name), p.name))
            return matches[0]
    return None


def _find_archive_markdown(session_id: str) -> Path | None:
    """Find the archive markdown file for a session ID, if it exists."""
    return _find_archive_file(session_id, "md")


def _find_archive_json(session_id: str) -> Path | None:
    """Find the archive JSON file for a session ID, if it exists."""
    return _find_archive_file(session_id, "json")


def _filter_markdown_events(events: list[dict]) -> list[dict]:
    """Filter events from markdown to avoid substring-based false positives.

    Error events from `parse_events` use substring matching which causes issue
    #2036. Apply the counted-failure guard to error events: keep only those
    whose content contains a counted failure pattern like "3 failed".
    """
    filtered = []
    for evt in events:
        if evt.get("type") == "error":
            content = evt.get("content", "")
            if not _FAIL_COUNT_RE.search(content):
                continue
        filtered.append(evt)
    return filtered


def extract_from_json(data: dict, *, archive_fallback: bool = True) -> dict:
    """Build the episode component bundle from a JSON session log.

    When `archive_fallback` is True and the JSON workLog is empty, attempts to
    locate and parse the corresponding archive file (JSON first, then markdown)
    to preserve rich event/decision/lesson data from migrated sessions.
    """
    session_ts = json_timestamp(data)
    session = data.get("session", {})
    work_log = data.get("workLog", [])

    events = json_events(data, session_ts)
    decisions = json_decisions(data, session_ts)
    lessons = _json_lessons(data)

    if archive_fallback and not work_log:
        session_num = session.get("number")
        session_date = str(session.get("date", "")).strip()
        if session_num and session_date:
            session_id = f"{session_date}-session-{session_num}"
            archive_json_path = _find_archive_json(session_id)
            if archive_json_path and archive_json_path.is_file():
                try:
                    archive_content = archive_json_path.read_text(encoding="utf-8")
                    archive_data = looks_like_json_session(archive_content)
                    if archive_data and archive_data.get("workLog"):
                        archive_events = json_events(archive_data, session_ts)
                        archive_decisions = json_decisions(archive_data, session_ts)
                        archive_lessons = _json_lessons(archive_data)
                        if not events:
                            events = archive_events
                        if not decisions:
                            decisions = archive_decisions
                        if not lessons:
                            lessons = archive_lessons
                except (OSError, json.JSONDecodeError):
                    pass
            if not events or not decisions or not lessons:
                archive_md_path = _find_archive_markdown(session_id)
                if archive_md_path and archive_md_path.is_file():
                    try:
                        md_content = archive_md_path.read_text(encoding="utf-8")
                        md_lines = md_content.splitlines()
                        if not events:
                            md_events = parse_events(md_lines, session_ts)
                            events = _filter_markdown_events(md_events)
                        if not decisions:
                            decisions = parse_decisions(md_lines, session_ts)
                        if not lessons:
                            lessons = parse_lessons(md_lines)
                    except OSError:
                        pass

    return {
        "timestamp": json_timestamp(data),
        "task": str(session.get("objective", "")).strip(),
        "outcome": json_outcome(data),
        "decisions": decisions,
        "events": events,
        "metrics": json_metrics(data),
        "lessons": lessons,
    }


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
    if ".." in args.session_log_path.parts:
        msg = "Security: path must not contain traversal sequences."
        print(json.dumps({"Error": msg}), file=sys.stderr)
        return 2
    session_log_path = args.session_log_path.resolve()

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

    session_id = get_session_id_from_path(session_log_path)
    print(f"Extracting episode from: {session_log_path}", file=sys.stderr)

    json_data = looks_like_json_session(content)
    if json_data is not None:
        print("  Parsing JSON session log...", file=sys.stderr)
        bundle = extract_from_json(json_data)
        timestamp = bundle["timestamp"]
        task = bundle["task"]
        outcome = bundle["outcome"]
        decisions = bundle["decisions"]
        events = bundle["events"]
        metrics = bundle["metrics"]
        lessons = bundle["lessons"]
    else:
        print("  Parsing legacy markdown session log...", file=sys.stderr)
        lines = content.splitlines()
        metadata = parse_session_metadata(lines)
        decisions = parse_decisions(lines)
        events = parse_events(lines)
        lessons = parse_lessons(lines)
        metrics = parse_metrics(lines)
        outcome = get_session_outcome(metadata, events)
        timestamp = datetime.now(UTC).isoformat()
        if metadata.get("date"):
            try:
                timestamp = datetime.fromisoformat(metadata["date"]).isoformat()
            except ValueError:
                print(
                    f"  WARNING: Could not parse date '{metadata['date']}', "
                    "using current time",
                    file=sys.stderr,
                )
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
