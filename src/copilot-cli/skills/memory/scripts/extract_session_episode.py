#!/usr/bin/env python3
"""Extract episode data from session logs for the reflexion memory system.

Parses session logs and extracts structured episode data per ADR-038.
Extraction targets: session metadata, decisions, events, metrics, and lessons.

Session logs are JSON (see ``scripts/validate_session_json.py``). The JSON
path is primary: ``outcome`` is derived
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

        # Bold status markers (archive convention): the milestone rule above
        # excludes list markers followed by `**`, so an archived status bullet
        # like `- **Status**: COMPLETE` is otherwise dropped. Recognize a
        # completed status field as a milestone. The field name is restricted to
        # a status vocabulary so objective/decision sentences that merely begin
        # with "Complete ..." do not misfire. Refs PR #2170 (thread GA722).
        elif re.match(
            r'^[-*]\s+\*\*(?:status|result|outcome|state|resolution)\*\*\s*:\s*'
            r'(complete|completed|done|success|finished)\b',
            line,
            re.IGNORECASE,
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
        elif m and re.match(
            r'(?:lessons?\s+learned|lessons?|learned|takeaways?|note\s+for\s+future)\b',
            m.group(1),
            re.IGNORECASE,
        ):
            # Outside a Lessons section, only collect bullets whose content
            # *starts* with a lesson keyword. A substring match anywhere on the
            # line pulls in protocol-gate evidence prose ("lessons captured in
            # the PR description") and checklist items, polluting the episode.
            lessons.append(m.group(1).strip())

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
# The (?<![#\w]) lookbehind excludes '#'-prefixed identifiers (issue/PR/comment
# refs like "#760 failures") and digits glued to a preceding word. Group 2
# captures the keyword so callers can reject HTTP-status-shaped error counts.
# Refs PR #2170 (thread GANjI): leading numbers that are issue refs or status
# codes must not inflate metrics.errors.
_FAIL_COUNT_RE = re.compile(
    r"(?<![#\w])([1-9]\d*)\s+(failed|failures|errors?)\b", re.IGNORECASE
)
_PASS_COUNT_RE = re.compile(r"\b(\d+)\s+(?:passed|passing)\b", re.IGNORECASE)
_SHA_RE = re.compile(r"\b[0-9a-f]{7,40}\b")
_FILES_RE = re.compile(r"\b(\d+)\s+files?\b", re.IGNORECASE)
_DECISION_RE = re.compile(
    r"\b(chose|decided|selected|opted|adopt|prioriti|"
    r"design decision|approach|reclassif)",
    re.IGNORECASE,
)
# Defect-inventory qualifiers: an "N errors" tally describing a pre-existing
# backlog (lint debt, baseline findings) is not a count of failures this
# session produced. Refs PR #2170 (thread GA72x).
_DEFECT_INVENTORY_RE = re.compile(
    r"pre-?existing|existing files|baseline|backlog|already (?:present|there)",
    re.IGNORECASE,
)


def _as_dict(value: Any) -> dict:
    """Coerce a possibly-null JSON value to a dict (explicit null -> {})."""
    return value if isinstance(value, dict) else {}


def _valid_fail_match(text: str) -> "re.Match[str] | None":
    """First counted-failure match that is a real failure tally, else None.

    Rejects matches where the keyword is "error(s)" and the count falls in the
    HTTP status range (100-599); "404 errors"/"500 errors" are status-code
    language, not failure counts. Also rejects "error(s)" tallies qualified as
    defect inventory ("23 errors in pre-existing files"): a lint or baseline
    backlog is not a count of failures this session produced. "#"-prefixed refs
    are already excluded by the _FAIL_COUNT_RE lookbehind.
    Refs PR #2170 (threads GANjI, GA72x).
    """
    for match in _FAIL_COUNT_RE.finditer(text):
        count = int(match.group(1))
        keyword = match.group(2).lower()
        if keyword.startswith("error"):
            if 100 <= count <= 599:
                continue
            if _DEFECT_INVENTORY_RE.search(text):
                continue
        return match
    return None


def _as_list(value: Any) -> list:
    """Coerce a possibly-null JSON value to a list (explicit null -> [])."""
    return value if isinstance(value, list) else []


def _entry_field(entry: Any, key: str) -> str:
    """Return a work-log entry field, or '' when the entry is not a dict.

    An explicitly-null field value collapses to '' rather than the literal
    string 'None'.
    """
    if not isinstance(entry, dict):
        return ""
    value = entry.get(key)
    return str(value) if value is not None else ""


def _entry_title(entry: Any) -> str:
    """Milestone content for a work-log entry: task, else action, else outcome.

    Work-log entries appear in several shapes across the log history: a bare
    string, ``{action, outcome}`` (older), ``{task, outcome, evidence}``
    (newer), ``{step, summary}``, and ``{step, evidence}``. All are handled; a
    string entry is its own title. A numeric ``step`` is an ordinal index, not
    a label, so ``summary`` is preferred ahead of it.
    """
    if isinstance(entry, str):
        return entry.strip()
    if isinstance(entry, dict):
        return str(
            entry.get("task")
            or entry.get("action")
            or entry.get("summary")
            or entry.get("step")
            or entry.get("outcome")
            or ""
        ).strip()
    return ""


def _entry_text(entry: Any) -> str:
    """All free-text of a work-log entry, joined for signal detection."""
    if isinstance(entry, str):
        return entry
    if isinstance(entry, dict):
        return " ".join(
            str(entry.get(k) or "")
            for k in ("task", "action", "summary", "step", "outcome", "evidence", "result")
        )
    return ""


# Fields that carry the entry's own label/intent. Decision detection scans only
# these so narrative ``evidence``/``result`` prose mentioning "adopt" or
# "prioritize" does not manufacture spurious decisions (the ``outcome`` field is
# excluded too because it is a status, not the decision wording).
_DECISION_SIGNAL_FIELDS = ("task", "action", "summary", "step")

# Status words that describe how a step ended, not what was decided.
_STATUS_WORDS = {"success", "ok", "done", "complete", "completed", "passed"}


def _decision_signal_text(entry: Any) -> str:
    """Label/intent text of a work-log entry, used to detect a decision."""
    if isinstance(entry, str):
        return entry
    if isinstance(entry, dict):
        return " ".join(str(entry.get(k) or "") for k in _DECISION_SIGNAL_FIELDS)
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
    compliance = _as_dict(data.get("protocolCompliance"))
    g = _as_dict(_as_dict(compliance.get(phase)).get(gate))
    return bool(g.get("Complete"))


def _collect_shas(data: dict, *, include_starting: bool) -> list[str]:
    """Distinct commit SHAs from the structured commit fields and work-log
    evidence. Excludes the starting commit by default (it is the base, not a
    commit the session produced)."""
    seen: list[str] = []
    fields = [str(data.get("endingCommit") or "")]
    if include_starting:
        fields.append(str(_as_dict(data.get("session")).get("startingCommit") or ""))
    for entry in _as_list(data.get("workLog")):
        fields.append(_entry_text(entry))
    for field in fields:
        for sha in _SHA_RE.findall(field):
            if sha not in seen:
                seen.append(sha)
    return seen


def json_timestamp(data: dict) -> str:
    date = str(_as_dict(data.get("session")).get("date") or "").strip()
    if date:
        try:
            dt = datetime.fromisoformat(date)
            if dt.tzinfo is not None:
                return dt.astimezone(UTC).isoformat()
            return dt.replace(tzinfo=UTC).isoformat()
        except ValueError:
            pass
    return datetime.now(UTC).isoformat()


def json_outcome(data: dict, additional_worklogs: list | None = None) -> str:
    """Derive outcome from the session-end MUST gates and work-log results.

    The authoritative signal is the ``sessionEnd`` MUST gates: a session whose
    checklist, commit, and validation gates are all complete succeeded; an
    incomplete session is partial. ``failure`` requires an explicit counted
    failure in a work-log result AND an incomplete gate set, never a bare
    substring match.

    When ``additional_worklogs`` is provided (e.g., from archive fallback), those
    entries are also checked for counted failures to ensure outcome consistency
    with metrics sourced from the same archive.
    """
    must = ("checklistComplete", "changesCommitted", "validationPassed")
    all_complete = all(_gate_complete(data, "sessionEnd", g) for g in must)

    worklogs_to_check = _as_list(data.get("workLog"))
    if additional_worklogs:
        worklogs_to_check = worklogs_to_check + additional_worklogs

    explicit_failure = any(
        _valid_fail_match(_entry_text(e)) is not None for e in worklogs_to_check
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

    for entry in _as_list(data.get("workLog")):
        title = _entry_title(entry)
        if title:
            add("milestone", title)
        text = _entry_text(entry)
        if _PASS_COUNT_RE.search(text):
            add("test", (_entry_field(entry, "evidence") or _entry_field(entry, "outcome") or text).strip())
        if _valid_fail_match(text):
            add("error", text.strip())

    ending = str(data.get("endingCommit") or "")
    if _SHA_RE.fullmatch(ending.strip()):
        add("commit", f"Commit: {ending.strip()}")

    return events


def json_decisions(data: dict, now_iso: str) -> list[dict]:
    """Surface work-log entries that describe a choice as decisions."""
    decisions: list[dict] = []
    idx = 0
    for entry in _as_list(data.get("workLog")):
        text = _entry_text(entry)
        if not _DECISION_RE.search(_decision_signal_text(entry)):
            continue
        title = _entry_title(entry)
        outcome = _entry_field(entry, "outcome").strip()
        # Prefer the decision label; fall back to the outcome only when it is
        # not a bare status word ("success", "ok", ...).
        chosen = title or (outcome if outcome.lower() not in _STATUS_WORDS else "")
        idx += 1
        decisions.append({
            "id": f"d{idx:03d}",
            "timestamp": now_iso,
            "type": get_decision_type(text),
            "context": title,
            "chosen": chosen,
            "rationale": _entry_field(entry, "evidence").strip(),
            "outcome": "success",
            "effects": [],
        })
    return decisions


def json_metrics(data: dict) -> dict:
    # Count every distinct commit the session documents (ending commit plus any
    # SHAs in work-log evidence), not just the ending commit. Excludes the
    # starting commit (the base, not a commit the session produced).
    commit_count = len(_collect_shas(data, include_starting=False))
    metrics = {
        "duration_minutes": 0,
        "tool_calls": 0,
        "errors": 0,
        "recoveries": 0,
        "commits": commit_count,
        "files_changed": 0,
    }
    for entry in _as_list(data.get("workLog")):
        text = _entry_text(entry)
        fail = _valid_fail_match(text)
        if fail:
            metrics["errors"] += int(fail.group(1))
        files = _FILES_RE.search(text)
        if files:
            metrics["files_changed"] += int(files.group(1))
    return metrics


def _learning_entry_text(item: dict) -> str:
    """Render one structured learning entry as a single lesson string.

    Handles three shapes: the list-of-dict shorthand (``text``/``content``/
    ``lesson``), schema ``patterns`` entries (``pattern`` + ``application``), and
    schema ``avoidances`` entries (``antipattern`` + ``correction``).
    """
    for key in ("text", "content", "lesson"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    if "antipattern" in item or "correction" in item:
        anti = str(item.get("antipattern") or "").strip()
        corr = str(item.get("correction") or "").strip()
        parts = [f"Avoid: {anti}" if anti else "", corr]
    else:
        parts = [str(item.get("pattern") or "").strip(), str(item.get("application") or "").strip()]
    return ". ".join(p for p in parts if p)


def _json_lessons(data: dict) -> list[str]:
    """Extract lessons/learnings from JSON session log.

    ``learnings`` may be a list (strings or ``{text}`` dicts) or the schema's
    object shape with ``patterns`` and ``avoidances`` arrays; both are flattened
    to lesson strings so object-shaped learnings still reach episode JSON.
    """
    raw = data.get("learnings", [])
    if isinstance(raw, list):
        items = raw
    elif isinstance(raw, dict):
        items = _as_list(raw.get("patterns")) + _as_list(raw.get("avoidances"))
    else:
        return []
    lessons: list[str] = []
    for item in items:
        if isinstance(item, str):
            text = item.strip()
        elif isinstance(item, dict):
            text = _learning_entry_text(item)
        else:
            text = ""
        if text:
            lessons.append(text)
    return lessons


_PLACEHOLDER_VALUES = {"", "[migrated from markdown]", "unknown", "untitled"}


def _is_placeholder(value: Any) -> bool:
    """True when a scalar field carries no real information."""
    return str(value or "").strip().lower() in _PLACEHOLDER_VALUES


def _norm(value: Any) -> str:
    """Normalize text for dedupe keys: collapse whitespace and lowercase."""
    return " ".join(str(value or "").split()).lower()


def _deterministic_date(session_id: str, *timestamps: Any) -> str | None:
    """Pick a stable YYYY-MM-DD for event normalization.

    Preference order keeps committed fixtures idempotent: the session id date
    first (always present and stable), then any timestamp that already carries a
    date. Never falls back to wall-clock ``now()``.
    """
    match = re.search(r"(\d{4}-\d{2}-\d{2})", session_id or "")
    if match:
        return match.group(1)
    for ts in timestamps:
        text = str(ts or "").strip()
        if len(text) >= 10 and text[4] == "-" and text[7] == "-":
            return text[:10]
    return None


_JSON_FRAGMENT_RE = re.compile(r'^\s*"[^"]+"\s*:')


def _is_lesson_text(item: Any) -> bool:
    """Reject serialized JSON key/value fragments mis-captured as lessons.

    Older extraction runs stringified protocol-gate blobs ("retrospectiveInvoked":
    {...}), evidence fields ("Evidence": "..."), and work-log entries ("action":
    "...") into the lessons list. With --preserve those survive the union and keep
    polluting reflexion memory. A genuine lesson is prose; a JSON fragment starts
    with a quoted key followed by a colon. Refs PR #2170 (thread GAo-h).
    """
    text = str(item).strip()
    if not text:
        return False
    return not _JSON_FRAGMENT_RE.match(text)


def _dedupe_lessons(existing: list, new: list) -> list[str]:
    """Union lessons by normalized text, existing first, append new uniques.

    Drops JSON-fragment junk (see ``_is_lesson_text``) from both sides so a
    --preserve regeneration cleans previously committed pollution.
    """
    out: list[str] = []
    seen: set[str] = set()
    for item in list(existing) + list(new):
        if not _is_lesson_text(item):
            continue
        key = _norm(item)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _dedupe_decisions(existing: list, new: list) -> list[dict]:
    """Union decisions by (chosen, context, type); reassign ids by order.

    Legacy episodes stored decisions as plain strings. ``_as_dict`` would turn
    those into ``{}`` and silently drop the human-authored text, collapsing all
    string decisions into one empty object. Coerce a string decision to its
    ``chosen`` summary so the dedup key and output retain the content.
    Refs PR #2170 (thread GASBG).
    """
    def coerce(dec: Any) -> dict:
        if isinstance(dec, str):
            text = dec.strip()
            return {"chosen": text} if text else {}
        return _as_dict(dec)

    out: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    for dec in list(existing) + list(new):
        entry = coerce(dec)
        key = (_norm(entry.get("chosen")), _norm(entry.get("context")), _norm(entry.get("type")))
        if key in seen:
            continue
        seen.add(key)
        out.append(dict(entry))
    for i, entry in enumerate(out, 1):
        entry["id"] = f"d{i:03d}"
    return out


def _dedupe_events(existing: list, new: list, midnight: str | None) -> list[dict]:
    """Union events by (type, content); normalize timestamps; reassign ids."""
    out: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for evt in list(existing) + list(new):
        entry = _as_dict(evt)
        key = (_norm(entry.get("type")), _norm(entry.get("content")))
        if key in seen:
            continue
        seen.add(key)
        entry = dict(entry)
        if midnight:
            entry["timestamp"] = midnight
        out.append(entry)
    for i, entry in enumerate(out, 1):
        entry["id"] = f"e{i:03d}"
    return out


def _merge_metrics(new: dict, existing: dict) -> dict:
    """Per-key max so regeneration never zeroes a previously counted metric.

    Key order follows ``new`` first (a fixed extractor order) then any
    existing-only keys, so serialized output is deterministic and idempotent.
    """
    out: dict[str, Any] = {}
    ordered_keys = list(new) + [k for k in existing if k not in new]
    for key in ordered_keys:
        nv = new.get(key, 0)
        ev = existing.get(key, 0)
        if isinstance(nv, (int, float)) and isinstance(ev, (int, float)):
            out[key] = max(nv, ev)
        else:
            out[key] = nv if nv else ev
    return out


def merge_preserving(new: dict, existing: dict, *, session_id: str = "") -> dict:
    """Merge a freshly extracted episode over an existing one without data loss.

    Read-modify-write semantics for regeneration: fresh extraction is the base,
    but existing richer content survives. Lists union (existing first) by stable
    content keys so curated decisions/events/lessons are never dropped, metrics
    take the per-key max, placeholder task/outcome yield to existing real values,
    and event timestamps normalize to the deterministic session date so output is
    idempotent. Applying twice is a no-op.
    """
    existing = _as_dict(existing)
    date = _deterministic_date(
        session_id, new.get("timestamp"), existing.get("timestamp")
    )
    midnight = f"{date}T00:00:00+00:00" if date else None

    merged = dict(new)
    merged["timestamp"] = midnight or new.get("timestamp") or existing.get("timestamp")
    if _is_placeholder(new.get("task")) and not _is_placeholder(existing.get("task")):
        merged["task"] = existing.get("task")
    if _is_placeholder(new.get("outcome")) and not _is_placeholder(existing.get("outcome")):
        merged["outcome"] = existing.get("outcome")
    merged["lessons"] = _dedupe_lessons(
        _as_list(existing.get("lessons")), _as_list(new.get("lessons"))
    )
    merged["decisions"] = _dedupe_decisions(
        _as_list(existing.get("decisions")), _as_list(new.get("decisions"))
    )
    merged["events"] = _dedupe_events(
        _as_list(existing.get("events")), _as_list(new.get("events")), midnight
    )
    merged["metrics"] = _merge_metrics(
        _as_dict(new.get("metrics")), _as_dict(existing.get("metrics"))
    )
    return merged


def _repo_root() -> Path:
    """Locate the repository root by walking up to the nearest `.agents` dir.

    The script is distributed verbatim at two depths: the canonical
    `.claude/skills/memory/scripts/` copy and the generated
    `src/copilot-cli/skills/memory/scripts/` mirror. A fixed number of
    `.parent` hops cannot be correct at both depths, so search upward for the
    `.agents` marker and fall back to a four-hop default when it is absent.
    """
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / ".agents").is_dir():
            return parent
    return here.parent.parent.parent.parent


def _find_archive_file(session_id: str, extension: str) -> Path | None:
    """Find an archive file for a session ID with the given extension.

    Searches both `.agents/archive/sessions/` and `.agents/archive/session/`
    for files matching the session ID pattern. Returns the shortest-named match
    (preferring exact matches) to ensure deterministic selection across platforms.
    """
    base_archive = _repo_root() / ".agents" / "archive"
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


def _archive_session_id_candidates(session_date: str, session_num: Any) -> list[str]:
    """Build archive session-id candidates, tolerating zero-padded numbers.

    A primary log may record session number 2 while the archived file is named
    `...-session-02`. Emit the raw form plus zero-padded widths, de-duplicated
    in priority order so an exact match is preferred.
    """
    raw = str(session_num).strip()
    forms: list[str] = []
    for form in (raw, raw.zfill(2), raw.zfill(3)):
        if form and form not in forms:
            forms.append(form)
    return [f"{session_date}-session-{form}" for form in forms]


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
            if not _valid_fail_match(content):
                continue
        filtered.append(evt)
    return filtered


def extract_from_json(data: dict, *, archive_fallback: bool = True) -> dict:
    """Build the episode component bundle from a JSON session log.

    When `archive_fallback` is True and the primary JSON log yields no events
    of its own (no milestone/test/error, even if the workLog list is
    technically non-empty, e.g. ``[{}]`` or whitespace stubs), attempts to
    locate and parse the corresponding archive file (JSON first, then markdown)
    to preserve rich event/decision/lesson data from migrated sessions. A log
    that already has its own events keeps its own decisions and lessons; the
    archive is not consulted for them.
    """
    session_ts = json_timestamp(data)
    session = _as_dict(data.get("session"))

    events = json_events(data, session_ts)
    decisions = json_decisions(data, session_ts)
    lessons = _json_lessons(data)
    metrics_source = data

    has_events = any(e.get("type") in ("milestone", "test", "error") for e in events)
    # A commit event is the session's own signal. It does not gate archive
    # consultation (a thin stub may still need archived decisions/lessons), but
    # it must never be overwritten by archived events.
    has_own_events = has_events or any(e.get("type") == "commit" for e in events)
    if archive_fallback and not has_events:
        session_num = session.get("number")
        session_date = str(session.get("date") or "").strip()
        if session_num is not None and str(session_num).strip() and session_date:
            candidates = _archive_session_id_candidates(session_date, session_num)
            archive_json_path = next(
                (p for sid in candidates if (p := _find_archive_json(sid)) and p.is_file()),
                None,
            )
            if archive_json_path is not None:
                try:
                    archive_content = archive_json_path.read_text(encoding="utf-8")
                    archive_data = looks_like_json_session(archive_content)
                    if archive_data and _as_list(archive_data.get("workLog")):
                        archive_events = json_events(archive_data, session_ts)
                        archive_decisions = json_decisions(archive_data, session_ts)
                        archive_lessons = _json_lessons(archive_data)
                        if not has_own_events:
                            events = archive_events
                            metrics_source = archive_data
                        if not decisions:
                            decisions = archive_decisions
                        if not lessons:
                            lessons = archive_lessons
                except (OSError, json.JSONDecodeError):
                    pass
            has_events = any(
                e.get("type") in ("milestone", "test", "error") for e in events
            )
            has_own_events = has_events or any(e.get("type") == "commit" for e in events)
            if not has_events or not decisions or not lessons:
                archive_md_path = next(
                    (p for sid in candidates if (p := _find_archive_markdown(sid)) and p.is_file()),
                    None,
                )
                if archive_md_path is not None:
                    try:
                        md_content = archive_md_path.read_text(encoding="utf-8")
                        md_lines = md_content.splitlines()
                        if not has_own_events:
                            md_events = parse_events(md_lines, session_ts)
                            events = _filter_markdown_events(md_events)
                            # Metrics are NOT derived from markdown-archive prose.
                            # Unstructured lines would let _collect_shas count any
                            # hex run and _FILES_RE count any "N files" phrase,
                            # inflating commits/files (thread GA721). Metrics stay
                            # sourced from structured signal only: the primary
                            # JSON workLog + endingCommit, or a structured JSON
                            # archive (handled in the json-archive branch above).
                            # The markdown archive contributes events, decisions,
                            # and lessons (narrative recovery), not metrics.
                        if not decisions:
                            decisions = parse_decisions(md_lines, session_ts)
                        if not lessons:
                            lessons = parse_lessons(md_lines)
                    except OSError:
                        pass

    additional_worklogs = (
        _as_list(metrics_source.get("workLog")) if metrics_source is not data else None
    )
    metrics = json_metrics(metrics_source)
    return {
        "timestamp": session_ts,
        "task": str(session.get("objective") or "").strip(),
        "outcome": json_outcome(data, additional_worklogs),
        "decisions": decisions,
        "events": events,
        "metrics": metrics,
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
    write_mode = parser.add_mutually_exclusive_group()
    write_mode.add_argument(
        "--force", action="store_true",
        help="Overwrite existing episode file if it exists",
    )
    write_mode.add_argument(
        "--preserve", action="store_true",
        help=(
            "Read-modify-write an existing episode file, merging fresh "
            "extraction over it without dropping richer existing data"
        ),
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
        output_path = _repo_root() / ".agents" / "memory" / "episodes"

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

    if episode_file.exists():
        if args.preserve:
            try:
                existing_raw = json.loads(episode_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as e:
                print(
                    json.dumps({
                        "Error": f"--preserve requires a readable existing episode: {e}",
                    }),
                    file=sys.stderr,
                )
                return 1
            if not isinstance(existing_raw, dict):
                print(
                    json.dumps({
                        "Error": "--preserve requires the existing episode to be a JSON object.",
                    }),
                    file=sys.stderr,
                )
                return 1
            episode = merge_preserving(episode, existing_raw, session_id=session_id)
            decisions = episode["decisions"]
            events = episode["events"]
            lessons = episode["lessons"]
            outcome = episode["outcome"]
        elif not args.force:
            print(
                json.dumps({
                    "Error": f"Episode file already exists: {episode_file}. Use --force to overwrite or --preserve to merge.",
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
