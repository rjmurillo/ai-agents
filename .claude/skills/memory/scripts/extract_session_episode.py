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
import os
import re
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


def get_session_id_from_path(path: Path) -> str:
    """Extract session ID from a log file path, preserving the full suffix.

    The session ID drives the episode filename (``episode-<id>.json``). Two
    parallel autofix sessions can share a session number but differ in their
    descriptive suffix (``...-session-2335-pr-2353-autofix`` vs
    ``...-session-2335-pr-2359-autofix``). Capturing only the number maps both
    to ``episode-<date>-session-2335.json`` and produces an add/add merge
    conflict (issue #2379). Capturing the full suffix keeps distinct sessions on
    distinct episode files.
    """
    stem = path.stem
    match = re.search(r"(\d{4}-\d{2}-\d{2}-session-\d+(?:-.+)?)", stem)
    if match:
        return match.group(1)
    match = re.search(r"(session-\d+(?:-.+)?)", stem)
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
        title_match = re.match(r"^#\s+(.+)$", line)
        if title_match and not metadata["title"]:
            metadata["title"] = title_match.group(1)
            continue

        # Date field
        m = re.match(r"^\*\*Date\*\*:\s*(.+)$", line)
        if m:
            metadata["date"] = m.group(1).strip()
            continue

        # Status field
        m = re.match(r"^\*\*Status\*\*:\s*(.+)$", line)
        if m:
            metadata["status"] = m.group(1).strip()
            continue

        # Objectives section
        if re.match(r"^##\s*Objectives?", line):
            in_section = "objectives"
            continue

        # Deliverables section
        if re.match(r"^##\s*Deliverables?", line):
            in_section = "deliverables"
            continue

        # New section ends current
        if re.match(r"^##\s", line):
            in_section = ""
            continue

        # Collect list items
        m = re.match(r"^\s*[-*]\s+(.+)$", line)
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
    if re.search(r"design|architect|schema|structure", lower):
        return "design"
    if re.search(r"test|pester|coverage|assert", lower):
        return "test"
    if re.search(r"recover|fix|retry|fallback", lower):
        return "recovery"
    if re.search(r"route|delegate|agent|handoff", lower):
        return "routing"
    return "implementation"


def parse_decisions(lines: list[str], timestamp: str | None = None) -> list[dict[str, Any]]:
    """Extract decisions from session log."""
    decisions: list[dict[str, Any]] = []
    decision_index = 0
    in_decision_section = False
    ts = timestamp if timestamp is not None else datetime.now(UTC).isoformat()

    for i, line in enumerate(lines):
        if re.match(r"^##\s*Decisions?", line):
            in_decision_section = True
            continue

        if in_decision_section and re.match(r"^##\s", line):
            in_decision_section = False

        # Decision patterns in various formats
        decision_text = None
        m1 = re.match(r"^\*\*Decision\*\*:\s*(.+)$", line)
        m2 = re.match(r"^Decision:\s*(.+)$", line)
        m3 = re.match(r"^\s*[-*]\s+\*\*(.+?)\*\*:\s*(.+)$", line) if in_decision_section else None

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
                ctx_match = re.match(r"^\s*[-*]\s+(.+)$", lines[i - 1])
                if ctx_match:
                    context = ctx_match.group(1)

            decisions.append(
                {
                    "id": f"d{decision_index:03d}",
                    "timestamp": ts,
                    "type": get_decision_type(decision_text),
                    "context": context,
                    "chosen": decision_text,
                    "rationale": "",
                    "outcome": "success",
                    "effects": [],
                }
            )
            continue

        # Capture decisions from work log entries
        if re.search(r"chose|decided|selected|opted for", line) and not line.startswith("#"):
            decision_index += 1
            decisions.append(
                {
                    "id": f"d{decision_index:03d}",
                    "timestamp": ts,
                    "type": "implementation",
                    "context": "",
                    "chosen": line.strip(),
                    "rationale": "",
                    "outcome": "success",
                    "effects": [],
                }
            )

    return decisions


def parse_events(lines: list[str], timestamp: str | None = None) -> list[dict]:
    """Extract events from session log."""
    events: list[dict] = []
    event_index = 0
    ts = timestamp if timestamp is not None else datetime.now(UTC).isoformat()

    def add(evt_type: str, content: str) -> None:
        nonlocal event_index
        event_index += 1
        events.append(
            {
                "id": f"e{event_index:03d}",
                "timestamp": ts,
                "type": evt_type,
                "content": content,
                "caused_by": [],
                "leads_to": [],
            }
        )

    for line in lines:
        # Commit events
        m = re.search(r"commit[ted]?\s+(?:as\s+)?([a-f0-9]{7,40})", line)
        if not m:
            m = re.search(r"([a-f0-9]{7,40})\s+\w+\(.+\):", line)
        if m:
            add("commit", f"Commit: {m.group(1)}")

        # Error events
        if re.search(r"error|fail|exception", line, re.IGNORECASE) and not line.startswith("#"):
            add("error", line.strip())

        # Milestone events
        if re.search(r"completed?|done|finished|success", line, re.IGNORECASE) and re.match(
            r"^[-*]\s+(?!\*)", line
        ):
            add("milestone", re.sub(r"^[-*]\s*", "", line.strip()))

        # Bold status markers (archive convention): the milestone rule above
        # excludes list markers followed by `**`, so an archived status bullet
        # like `- **Status**: COMPLETE` is otherwise dropped. Recognize a
        # completed status field as a milestone. The field name is restricted to
        # a status vocabulary so objective/decision sentences that merely begin
        # with "Complete ..." do not misfire. Refs PR #2170 (thread GA722).
        elif re.match(
            r"^[-*]\s+\*\*(?:status|result|outcome|state|resolution)\*\*\s*:\s*"
            r"(complete|completed|done|success|finished)\b",
            line,
            re.IGNORECASE,
        ):
            add("milestone", re.sub(r"^[-*]\s*", "", line.strip()))

        # Test events
        if re.search(r"test[s]?\s+(pass|fail|run)", line, re.IGNORECASE) or "Pester" in line:
            add("test", line.strip())

    return events


def parse_lessons(lines: list[str]) -> list[str]:
    """Extract lessons learned from session log."""
    lessons = []
    in_lessons_section = False

    for line in lines:
        if re.match(r"^##\s*(Lessons?\s*Learned?|Key\s*Learnings?|Takeaways?)", line):
            in_lessons_section = True
            continue

        if in_lessons_section and re.match(r"^##\s", line):
            in_lessons_section = False

        m = re.match(r"^\s*[-*]\s+(.+)$", line)
        if in_lessons_section and m:
            lessons.append(m.group(1).strip())
        elif m and re.match(
            r"(?:lessons?\s+learned|lessons?|learned|takeaways?|note\s+for\s+future)\b",
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
        m = re.search(r"(\d+)\s*minutes?", line)
        if not m:
            m = re.search(r"duration:\s*(\d+)", line, re.IGNORECASE)
        if m:
            metrics["duration_minutes"] = int(m.group(1))

        # Count commits
        if re.search(r"[a-f0-9]{7,40}", line):
            metrics["commits"] += 1

        # Count errors
        if re.search(r"error|fail|exception", line, re.IGNORECASE) and not line.startswith("#"):
            metrics["errors"] += 1

        # Count files
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
_FAIL_COUNT_RE = re.compile(r"(?<![#\w])([1-9]\d*)\s+(failed|failures|errors?)\b", re.IGNORECASE)
_PASS_COUNT_RE = re.compile(r"\b(\d+)\s+(?:passed|passing)\b", re.IGNORECASE)
_SHA_RE = re.compile(r"\b[0-9a-f]{7,40}\b")
# A commit SHA candidate pulled from free-text prose must contain at least one
# hex letter. Decimal-only runs of 7 to 40 digits (GitHub comment IDs, run IDs,
# epoch timestamps, long issue numbers) are a subset of _SHA_RE and would
# otherwise be misread as commits (issue #3301).
_HEX_LETTER_RE = re.compile(r"[a-f]")
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


def _valid_fail_match(text: str) -> re.Match[str] | None:
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
    (newer), ``{step, summary}``, ``{step, evidence}``, and ``{entry, ...}``
    (issue #2552). All are handled; a string entry is its own title. A numeric
    ``step`` is an ordinal index, not a label, so ``summary`` and ``entry`` are
    preferred ahead of it.
    """
    if isinstance(entry, str):
        return entry.strip()
    if isinstance(entry, dict):
        return str(
            entry.get("task")
            or entry.get("action")
            or entry.get("summary")
            or entry.get("entry")
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
            for k in ("task", "action", "summary", "entry", "step", "outcome", "evidence", "result")
        )
    return ""


# Fields that carry the entry's own label/intent. Decision detection scans only
# these so narrative ``evidence``/``result`` prose mentioning "adopt" or
# "prioritize" does not manufacture spurious decisions (the ``outcome`` field is
# excluded too because it is a status, not the decision wording). ``entry`` is a
# primary label-bearing field in newer logs (issue #2552).
_DECISION_SIGNAL_FIELDS = ("task", "action", "summary", "entry", "step")

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
    return bool(g.get("Complete") if "Complete" in g else g.get("complete"))


def _same_commit(a: str, b: str) -> bool:
    """True when two hex SHA strings denote the same commit, allowing for git
    abbreviation: the shorter is a prefix of the longer with at least 7 shared
    hex chars. Exact equality is the equal-length case. This lets a full 40-char
    ``startingCommit`` match a 7-char abbreviation of it repeated in work-log
    prose (issue #3123).

    Seven is this module's own floor, not a git contract. Git's abbreviation
    length is repo-dependent (``core.abbrev``, and git widens it as the object
    count grows), so there is no minimum to inherit. Seven is chosen because it
    is what this repository's tooling emits and short enough prefixes collide."""
    a = a.strip().lower()
    b = b.strip().lower()
    if not a or not b:
        return False
    lo, hi = (a, b) if len(a) <= len(b) else (b, a)
    return len(lo) >= 7 and hi.startswith(lo)


def _already_seen(sha: str, seen: list[str]) -> bool:
    """True when ``seen`` already holds this commit at any abbreviation length.

    Exact string membership lets one commit in twice when two fields spell it
    at different lengths: a full 40-char ``endingCommit`` and a 7-char
    abbreviation of the same commit in the ``changesCommitted`` evidence. That
    double-counts ``metrics.commits`` and emits two commit events for a single
    commit (issue #3363).
    """
    return any(_same_commit(sha, existing) for existing in seen)


def _prose_shas(text: str) -> list[str]:
    """Commit SHAs mentioned in free-text prose.

    Require at least one hex letter (a-f) so decimal-only identifiers (GitHub
    comment IDs, run IDs, epoch timestamps, long issue numbers) are not misread
    as commit SHAs (issue #3301). This trades one rare miss for a common false
    positive: a genuine short SHA prefix that happens to be all decimal digits
    (uncommon for 7-char prefixes, vanishingly rare for full-length SHAs) is
    dropped when it appears only in prose.
    That miss degrades the event chain gracefully; counting every decimal ID in
    prose as a commit corrupts it. Structured commit fields (``endingCommit``,
    ``startingCommit``) are scanned unfiltered, so an all-decimal final SHA is
    still captured. ``endingCommit`` records only the final commit, so an
    intermediate all-decimal SHA referenced solely in work-log prose is the one
    case this filter can miss.
    """
    return [sha for sha in _SHA_RE.findall(text) if _HEX_LETTER_RE.search(sha)]


def _session_floor(session_date: str) -> datetime | None:
    """Earliest instant a session dated ``session_date`` could have committed.

    ``session.date`` is normally a calendar day with no timezone, and a
    session's own commits straddle midnight in both directions: the committer's
    local clock can be up to 14 hours off UTC, and a session that starts in the
    evening keeps committing past midnight. One full day of slack before the
    labelled day covers both without needing a timezone the log does not
    record.

    The schema pins ``session.date`` to a bare ``YYYY-MM-DD``, but this parser
    is deliberately tolerant of a full ISO timestamp, which may carry an offset.
    An offset-bearing value is converted, not relabelled: ``replace(tzinfo=UTC)``
    on an aware datetime silently discards the real offset and can move the
    floor by up to a day, which is enough to drop a commit the session made.
    """
    try:
        parsed = datetime.fromisoformat(session_date)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC) - timedelta(days=1)


def _prose_sha_predates_session(sha: str, session_date: str) -> bool:
    """Whether git can prove ``sha`` was committed before the session could run.

    Work-log prose cites SHAs the session did not author: an upstream merge it
    reasoned about, a third-party commit it bisected, a PR whose base it read.
    Counting those inflates ``metrics.commits`` and puts commit events the
    session never produced into the episode (issue #3328).

    The discriminator is the commit's own committer timestamp against
    ``_session_floor``. A commit that already existed a full day before the
    session's calendar date cannot be a commit that session produced. Rebase,
    cherry-pick, amend, and squash all refresh the committer date forward, so
    the test survives history rewriting: a rewritten commit reads as newer, and
    newer only ever means "keep counting it".

    Both ancestry forms issue #3328 proposes are unsound here, in opposite ways:

    * "is ``sha`` a *descendant* of ``startingCommit``" breaks under
      squash-merge. A squash commit discards the topic branch's parentage, so a
      session's own merge commit is not a descendant of its own base. Measured
      over the full session-log corpus it dropped 13 logs, every inspected case
      a squash merge of that session's own work.
    * "is ``sha`` an *ancestor* of ``startingCommit``" breaks whenever the log's
      ``startingCommit`` was captured late. Nothing in the schema or in
      ``validate_session_json.py`` requires the anchor to precede the work, and
      ``.agents/sessions/2026-05-11-session-1832.json`` records exactly that: it
      opened its log after the green-phase commit, so its own spec and red-phase
      commits are ancestors of its own anchor and get dropped.

    The timestamp test needs no anchor and no assumption about merge strategy.
    Measured against the corpus as it stood when #3328 was investigated (917
    logs, 2026-07-25), it excluded five SHAs, each an explicit citation
    ("Verified PR #2168 merge commit", "git-blamed exit-4 (added #2394 ...)"),
    and dropped no session-authored commit. That is a point-in-time reading
    taken to justify the rule, not a live invariant; expect the count to move
    as logs land, and do not treat a different number as a regression.

    Fails open on unknown: an unresolvable SHA, a non-commit object, an
    ambiguous abbreviation, or an unparsable date all keep the pre-#3328
    behavior. That preserves the abbreviated-SHA fixtures the #2170, #3123, and
    #3301 guards depend on, and it is the right default because this feeds a
    metrics artifact, not a security gate. Over-counting one commit is cheaper
    than silently dropping real ones whenever the extractor runs outside a
    checkout.

    Resolves against the ambient working directory, which under the pre-commit
    hook is the repo that owns the session log being extracted.
    """
    floor = _session_floor(session_date) if sha else None
    if floor is None:
        return False
    env = os.environ.copy()
    for var in ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE"):
        env.pop(var, None)
    env["LC_ALL"] = "C"
    try:
        result = subprocess.run(
            ["git", "show", "-s", "--format=%cI", f"{sha}^{{commit}}"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    if result.returncode != 0:
        return False
    try:
        committed = datetime.fromisoformat((result.stdout or "").strip())
    except ValueError:
        return False
    return committed.astimezone(UTC) < floor


def _changes_committed_evidence(data: dict) -> str:
    """The session-end ``changesCommitted`` evidence string, or empty.

    The session protocol treats this field as the record of what the session
    committed, so it is the authoritative commit source alongside
    ``endingCommit``.
    """
    compliance = _as_dict(data.get("protocolCompliance"))
    session_end = _as_dict(compliance.get("sessionEnd"))
    item = _as_dict(session_end.get("changesCommitted"))
    for key in ("Evidence", "evidence"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return ""


def _collect_shas(data: dict) -> list[str]:
    """Distinct commit SHAs a session produced, newest source of truth first.

    Distinctness is abbreviation-aware: two fields that spell the same commit
    at different lengths yield one entry, keeping the first spelling seen.

    The commit set comes from the two fields the session protocol treats as the
    record of what a session committed: ``endingCommit`` and the session-end
    ``changesCommitted`` evidence. Work-log prose is a fallback, consulted only
    when neither of those two yields a SHA. That is a weaker condition than
    "both fields are empty": evidence reading ``Committed.`` with no SHA in it
    also reaches the fallback, and has to, because that is the shape 12 of the
    15 prose-only logs are in.

    Prose is not a primary source (issue #3363). A work-log entry legitimately
    cites SHAs the session did not author: a bot's housekeeping commits, a
    commit it bisected, the base of a PR it read. Counting those inflated
    ``metrics.commits`` and seeded commit events for work the session never
    did, while the session's own commits, recorded only in
    ``changesCommitted``, were missed entirely. On
    ``fix/3342-harness-reference-size`` the episode counted two foreign commits
    and dropped three of the session's own.

    The fallback is kept because 15 logs record their commits only in the work
    log. Three have no evidence string at all; the other 12 have one that names
    no SHA. Deleting the fallback would drop every commit those 15 sessions
    made. They are not a closed historical set: they run 2026-01-15 to
    2026-07-08, so the fallback is load-bearing for logs still being written.
    Measured over the 941 logs present at the time of measurement, by the
    definition this docstring states: neither
    ``endingCommit`` nor the ``changesCommitted`` evidence names a SHA other
    than the starting commit, and the work log does. It carries the existing
    hex-letter (issue #3301) and committer-date (issue #3328) filters.

    Excludes the starting commit: it is the base, not a commit the session
    produced, including when prose repeats it at a different abbreviation
    length (issue #3123).
    """
    seen: list[str] = []
    session = _as_dict(data.get("session"))
    starting = str(session.get("startingCommit") or "").strip()
    session_date = str(session.get("date") or "").strip()

    def _take(shas: list[str]) -> None:
        """Record every SHA that is neither the base commit nor already held."""
        for sha in shas:
            if starting and _same_commit(sha, starting):
                continue
            if not _already_seen(sha, seen):
                seen.append(sha)

    # endingCommit is the protocol's own field, so no prose heuristic applies.
    _take(_SHA_RE.findall(str(data.get("endingCommit") or "")))
    # changesCommitted evidence is a free-text sentence rather than a bare SHA,
    # so the hex-letter filter applies: a 20-digit CI run id quoted there is not
    # a commit (issue #3301). Scanning it unfiltered also let a decimal-only
    # match populate ``seen`` and suppress the work-log fallback below.
    _take(_prose_shas(_changes_committed_evidence(data)))

    if seen:
        return seen

    # Fallback for logs with no structured commit record at all.
    for entry in _as_list(data.get("workLog")):
        for sha in _prose_shas(_entry_text(entry)):
            if starting and _same_commit(sha, starting):
                continue
            if _already_seen(sha, seen):
                continue
            if _prose_sha_predates_session(sha, session_date):
                continue
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

    explicit_failure = any(_valid_fail_match(_entry_text(e)) is not None for e in worklogs_to_check)

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
        events.append(
            {
                "id": f"e{idx:03d}",
                "timestamp": now_iso,
                "type": evt_type,
                "content": content,
                "caused_by": [],
                "leads_to": [],
            }
        )

    for entry in _as_list(data.get("workLog")):
        title = _entry_title(entry)
        if title:
            add("milestone", title)
        text = _entry_text(entry)
        if _PASS_COUNT_RE.search(text):
            evidence = _entry_field(entry, "evidence")
            outcome = _entry_field(entry, "outcome")
            add("test", (evidence or outcome or text).strip())
        if _valid_fail_match(text):
            add("error", text.strip())

    # Emit one commit event per distinct session-produced commit SHA so the
    # event stream and metrics.commits share a single provenance rule
    # (issue #3123). Excludes the starting/base SHA, including work-log
    # mentions of it, matching json_metrics.
    for sha in _collect_shas(data):
        add("commit", f"Commit: {sha}")

    return events


def json_decisions(data: dict, now_iso: str) -> list[dict]:
    """Surface work-log entries that describe a choice as decisions.

    ``context`` and ``chosen`` are only both populated when the entry records
    two distinct things: a label and a separate selection. A work-log title
    like "Selected issue #1798" is the choice itself, not the situation
    prompting it, so it goes to ``chosen`` and ``context`` stays empty. Writing
    it to both was the majority shape: 19 of 28 decisions in the shipped corpus
    had ``context`` byte-identical to ``chosen``, which reads as corroboration
    while carrying no independent signal (issue #3628).
    """
    decisions: list[dict] = []
    idx = 0
    for entry in _as_list(data.get("workLog")):
        text = _entry_text(entry)
        if not _DECISION_RE.search(_decision_signal_text(entry)):
            continue
        title = str(_entry_title(entry) or "").strip()
        outcome = _entry_field(entry, "outcome").strip()
        # A bare status word ("success", "ok", ...) is not a selection.
        selection = outcome if outcome.lower() not in _STATUS_WORDS else ""
        chosen = selection or title
        context = title if selection and title != selection else ""
        idx += 1
        decisions.append(
            {
                "id": f"d{idx:03d}",
                "timestamp": now_iso,
                "type": get_decision_type(text),
                "context": context,
                "chosen": chosen,
                "rationale": _entry_field(entry, "evidence").strip(),
                "outcome": "success",
                "effects": [],
            }
        )
    return decisions


def _staged_file_paths(cwd: str | Path | None = None) -> set[str]:
    """Return the set of file paths in the staged commit (best-effort).

    Runs ``git diff --cached --name-only`` to get the list of staged files.
    When ``cwd`` is provided, the command is scoped via ``git -C``.
    Returns an empty set when git is unavailable or the command fails.
    """
    cmd = ["git"]
    if cwd is not None:
        cmd += ["-C", str(cwd)]
    cmd += ["diff", "--cached", "--name-only"]
    env = os.environ.copy()
    for var in ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE"):
        env.pop(var, None)
    env["LC_ALL"] = "C"
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return set()
    if result.returncode != 0:
        return set()
    return {line.strip() for line in result.stdout.splitlines() if line.strip()}


def _staged_files_changed(cwd: str | Path | None = None) -> int:
    """Count files in the staged commit of the repo at ``cwd`` (best-effort).

    The episode extractor runs in the pre-commit hook, where the session's
    in-flight commit is staged but no commit SHA exists yet. ``git diff
    --cached --numstat`` lists one line per staged file, so its line count is
    the commit's files-changed. When ``cwd`` is provided, the command is scoped
    via ``git -C`` so a non-repo path (e.g. a tmp fixture) yields 0 rather than
    leaking the ambient index. When ``cwd`` is omitted, git uses the ambient
    current working directory. Returns 0 when git is unavailable, nothing is
    staged, or the command fails (issue #2537 item 3: episodes otherwise report
    ``files_changed=0`` even when the commit changed several files).
    """
    cmd = ["git"]
    if cwd is not None:
        cmd += ["-C", str(cwd)]
    cmd += ["diff", "--cached", "--numstat"]
    env = os.environ.copy()
    for var in ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE"):
        env.pop(var, None)
    env["LC_ALL"] = "C"
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return 0
    if result.returncode != 0:
        return 0
    return sum(1 for line in result.stdout.splitlines() if line.strip())


def json_metrics(data: dict) -> dict:
    # Count every distinct commit the session documents, from the same source
    # as the commit events so the two can never disagree: endingCommit plus the
    # session-end changesCommitted evidence, falling back to work-log prose only
    # when neither of those yields a SHA (issue #3363). Excludes the starting
    # commit: it is the base, not a commit the session produced.
    commit_count = len(_collect_shas(data))
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


def _count_commit_events(events: list) -> int:
    """Distinct commit events in an episode. ``_dedupe_events`` unions by
    ``(type, content)``, so counting ``type == "commit"`` yields the distinct
    session-produced commit count that ``metrics.commits`` must equal (#3123)."""
    return sum(1 for evt in events if _as_dict(evt).get("type") == "commit")


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
    date = _deterministic_date(session_id, new.get("timestamp"), existing.get("timestamp"))
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
    # metrics.commits must equal the distinct commit-event count so preserve
    # accumulation never drifts from the event stream (issue #3123). The event
    # union above already dedupes by (type, content), so counting commit events
    # yields the distinct session-produced commit count.
    merged["metrics"]["commits"] = _count_commit_events(merged["events"])
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
            has_events = any(e.get("type") in ("milestone", "test", "error") for e in events)
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
        "session_log_path",
        type=Path,
        help="Path to the session log file to extract from",
    )
    parser.add_argument(
        "--output-path",
        type=Path,
        default=None,
        help="Output directory for episode JSON",
    )
    write_mode = parser.add_mutually_exclusive_group()
    write_mode.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing episode file if it exists",
    )
    write_mode.add_argument(
        "--preserve",
        action="store_true",
        help=(
            "Read-modify-write an existing episode file, merging fresh "
            "extraction over it without dropping richer existing data"
        ),
    )
    parser.add_argument(
        "--pending-stage",
        action="store_true",
        help=(
            "Add 1 to staged files count to account for the episode file "
            "that will be staged after extraction (pre-commit hook context)"
        ),
    )
    return parser


# Lifecycle precedence for the in-episode causal chain. Every JSON extractor
# event shares one session timestamp, so rank-only edges are intentionally
# sparse. The rank still protects issue #3260 from linking a commit as
# ``caused_by`` a later review milestone, but it is no longer enough evidence to
# assert causality for a pre-code milestone such as issue filing or
# reproduction.
_CAUSAL_TYPE_RANK: dict[str, int] = {
    "implementation": 0,
    "commit": 1,
    "test": 2,
    "error": 3,
    "milestone": 4,
}
_CAUSAL_DEFAULT_RANK = 2


def _causal_rank(evt: dict[str, Any]) -> int:
    return _CAUSAL_TYPE_RANK.get(evt.get("type", ""), _CAUSAL_DEFAULT_RANK)


def _has_causal_order_evidence(previous: dict[str, Any], current: dict[str, Any]) -> bool:
    previous_timestamp = previous.get("timestamp") or ""
    current_timestamp = current.get("timestamp") or ""
    if previous_timestamp != current_timestamp:
        return True
    return _causal_rank(previous) == _causal_rank(current)


def _stamp_decision_outcomes(decisions: list, outcome: str) -> None:
    """Replace the placeholder decision outcome with the session's measured one.

    Both producers wrote the literal `"success"`, so the field never
    discriminated: all 24 decisions in the shipped corpus that carried an
    outcome carried `"success"`, while 8 of 302 episodes were `partial` or
    `failure` at the session level. A constant that reads as a measurement is
    worse than no measurement, because a reader cannot tell the two apart
    (issue #3628).

    The session outcome is the strongest signal the extractor actually has:
    `json_outcome` derives it from the sessionEnd MUST gates plus counted
    work-log failures, and it uses the same three values the decision schema
    allows. Every decision in an episode belongs to that one session, so the
    session verdict applies to each of them.
    """
    for dec in decisions:
        if isinstance(dec, dict):
            dec["outcome"] = outcome


def _renumber_events(events: list) -> None:
    """Reassign contiguous, unique ids to the final event list, in place.

    Ids are positional labels, not stable identifiers: `_link_sequential_events`
    rebuilds every edge from the list that follows this call, so no reference
    can dangle. Only the `--preserve` path renumbered before (via
    `_dedupe_events`), which left two ways for a shipped episode to carry ids
    that tooling cannot index (issue #3633).

    A duplicate id makes every edge touching it ambiguous. A gap comes from
    filtering after ids are assigned: `_filter_markdown_events` drops error
    events that fail the counted-failure guard, which is how
    `episode-2026-05-31-session-1857.json` shipped a list starting at `e002`.
    Numbering last makes both unrepresentable rather than merely detected.
    """
    for index, evt in enumerate(events, 1):
        if isinstance(evt, dict):
            evt["id"] = f"e{index:03d}"


def _link_sequential_events(events: list[dict[str, Any]]) -> None:
    """Populate ``caused_by``/``leads_to`` with evidence-gated causal edges.

    ADR-038 defines ``caused_by``/``leads_to`` as first-class event fields so a
    reader can walk one episode's events in causal order, but every
    event-construction site emitted them empty, leaving the chain flat
    (issue #3245). These links stay inside the episode file; the separate
    aggregated causal graph they once fed was removed by ADR-089.

    The chain follows observed evidence first. ``json_events`` appends every
    commit after the work-log milestones, so a purely positional chain linked
    the commit as ``caused_by`` the final PR-review milestone, inverting cause
    and effect: a commit is created and pushed before any review happens
    (issue #3260). Events are ordered by ``(timestamp, lifecycle rank, original
    position)`` so commits precede the tests, errors, and review milestones
    that follow them, while events of the same rank keep their original order.
    The physical ``events`` list is left untouched; only the link fields change.

    A rank-only order is not enough evidence for an edge. JSON events often all
    share one session timestamp, and the schema leaves ``workLog.phase`` as free
    text instead of a stable pre-code or post-code marker. When adjacent events
    differ only by type rank at the same timestamp, the graph stays sparse
    rather than asserting a false cause. This preserves the #3260 invariant that
    a commit is not caused by a review milestone, and fixes #3464's pre-code
    milestone inversion.

    Mutates in place. Must run on final ids, i.e. after any id reassignment by
    ``_dedupe_events``, so the references never dangle.

    Overwrites ``caused_by``/``leads_to`` unconditionally. Under ``--preserve``,
    ids reassigned by ``merge_preserving`` make prior edges invalid, so any
    existing values (including curated edges on a loaded episode) are replaced
    by the regenerated chain rather than retained.
    """
    linkable = [e for e in events if isinstance(e, dict) and e.get("id")]
    chain_order = sorted(
        range(len(linkable)),
        key=lambda i: (
            linkable[i].get("timestamp") or "",
            _causal_rank(linkable[i]),
            i,
        ),
    )
    chain = [linkable[i] for i in chain_order]
    for evt in chain:
        evt["caused_by"] = []
        evt["leads_to"] = []
    for previous, current in zip(chain, chain[1:], strict=False):
        if not _has_causal_order_evidence(previous, current):
            continue
        previous["leads_to"] = [current["id"]]
        current["caused_by"] = [previous["id"]]


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
            json.dumps(
                {
                    "Error": f"Failed to read session log: {e}",
                }
            ),
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
                    f"  WARNING: Could not parse date '{metadata['date']}', using current time",
                    file=sys.stderr,
                )
        task = metadata["objectives"][0] if metadata["objectives"] else metadata["title"]

    # The staged commit is the primary source for files-changed; work-log prose
    # is only a fallback. `_FILES_RE` matches any "N files" phrase, so a line
    # like "markdownlint reported Linting: 2 files, 0 issues" would otherwise
    # set the count to 2 and, because the backfill was guarded on a falsy value,
    # suppress the correct staged-diff figure entirely (issue #3617). This is
    # the same primary/fallback split `_collect_shas` already applies to SHAs.
    # The extractor runs in pre-commit, so the in-flight commit is staged even
    # though no SHA exists yet (issue #2537 item 3).
    # When --pending-stage is set, add 1 to account for the episode file that
    # will be staged after extraction (the hook stages it after this script
    # returns, so numstat cannot see it yet). However, skip the +1 if the
    # episode file is already in the staged diff (e.g., via `git add -A`)
    # to avoid double-counting.
    staged = _staged_files_changed(session_log_path.parent)
    if staged:
        if args.pending_stage:
            episode_path = output_path / f"episode-{session_id}.json"
            repo_root = _repo_root()
            try:
                episode_rel = episode_path.resolve().relative_to(repo_root)
                episode_rel_path = str(episode_rel).replace("\\", "/")
            except ValueError:
                episode_rel_path = None
            staged_paths = _staged_file_paths(session_log_path.parent)
            if episode_rel_path is not None and episode_rel_path not in staged_paths:
                staged += 1
        metrics["files_changed"] = staged

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
                    json.dumps(
                        {
                            "Error": f"--preserve requires a readable existing episode: {e}",
                        }
                    ),
                    file=sys.stderr,
                )
                return 1
            if not isinstance(existing_raw, dict):
                print(
                    json.dumps(
                        {
                            "Error": (
                                "--preserve requires the existing episode to be "
                                "a JSON object."
                            ),
                        }
                    ),
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
                json.dumps(
                    {
                        "Error": (
                            f"Episode file already exists: {episode_file}. "
                            "Use --force to overwrite or --preserve to merge."
                        ),
                    }
                ),
                file=sys.stderr,
            )
            return 1

    _renumber_events(episode["events"])
    _stamp_decision_outcomes(episode["decisions"], episode["outcome"])
    _link_sequential_events(episode["events"])

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
