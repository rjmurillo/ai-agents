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
import copy
import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from functools import lru_cache
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
    metrics: dict[str, int] = {
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


def _entry_timestamp(entry: Any, fallback: str) -> str:
    """Return a work-log entry timestamp when the entry carries one."""
    for key in ("timestamp", "time"):
        value = _entry_field(entry, key).strip()
        if not value:
            continue
        try:
            parsed = _parse_causal_timestamp({"id": "workLog", "timestamp": value})
        except EpisodeValidationError:
            continue
        return parsed.isoformat()
    return fallback


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


@lru_cache(maxsize=256)
def _commit_datetime(sha: str) -> datetime | None:
    """The committer date of ``sha`` in UTC, or ``None`` when git cannot say.

    ``None`` covers every way the question can go unanswered: no checkout, an
    unresolvable or ambiguous abbreviation, an object that is not a commit, a
    git binary that is missing or hangs, and a date git prints that cannot be
    parsed. Callers must treat ``None`` as "unknown", never as "old" or "new".

    Scrubs the ``GIT_*`` variables so the lookup resolves against the ambient
    working directory rather than whatever repository invoked the hook, which
    under the pre-commit hook is the repo owning the session log.

    Cached because both callers ask about the same small SHA set repeatedly and
    each miss is a subprocess. The cache lives for one process, so a commit
    created after the first lookup within the same run is not observed; no
    caller creates commits mid-extraction.
    """
    if not sha:
        return None
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
        return None
    if result.returncode != 0:
        return None
    try:
        return datetime.fromisoformat((result.stdout or "").strip()).astimezone(UTC)
    except ValueError:
        return None


@lru_cache(maxsize=256)
def _sha_is_reachable(sha: str) -> bool:
    """Return True when ``sha`` is reachable from at least one named ref.

    A commit that resolves (``git cat-file -t`` succeeds) but is reachable from
    zero refs is a dangling object: clone residue from a squash-merged branch.
    Whether the object is present depends on local ``git gc`` timing, not on
    the repository content. Using it as evidence of commit order produces
    clone-dependent results: green on CI, red on a developer clone that never
    collected. Issue #4240.

    This check uses ``git for-each-ref --contains`` because it queries the
    object's position in the ref graph rather than the object database.
    ``--contains`` iterates all refs by default and exits as soon as one match
    is found; on large repositories the optional ``--format=%(refname)`` and a
    short-circuit via ``head -1`` make it faster, but the default is safe here.

    Returns ``False`` on any subprocess error, missing git binary, or timeout.
    A ``False`` is treated as unknown, matching the ``None`` contract of
    ``_commit_datetime``.
    """
    if not sha:
        return False
    env = os.environ.copy()
    for var in ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE"):
        env.pop(var, None)
    env["LC_ALL"] = "C"
    try:
        result = subprocess.run(
            ["git", "for-each-ref", "--contains", sha, "--format=%(refname)"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return bool(result.stdout.strip())


def _chronological(shas: list[str]) -> list[str]:
    """``shas`` in committer-date order, or unchanged when git cannot order them.

    ``_collect_shas`` returns commits in source-of-truth order: ``endingCommit``
    first, then the ``changesCommitted`` evidence. That is a provenance ranking,
    not a chronology, and ``endingCommit`` is by definition the *last* commit a
    session made. Emitting commit events in that order made
    ``_link_sequential_events`` chain the newest commit into the oldest, so a
    five-commit episode claimed its final commit caused its first (issue #3619).

    Reorders only when every SHA resolves. A partial answer cannot produce a
    trustworthy total order: placing unresolved commits first or last asserts a
    position git did not supply, and this artifact is read as a record of what
    happened. When any lookup returns ``None`` the input order is preserved
    unchanged, which is the pre-#3619 behavior and keeps episodes extractable
    outside a checkout.

    Ties keep their original relative order, so two commits sharing a committer
    second stay as ``_collect_shas`` ranked them.
    """
    resolved: list[datetime] = []
    for sha in shas:
        moment = _commit_datetime(sha)
        if moment is None:
            return list(shas)
        resolved.append(moment)
    return [sha for _, _, sha in sorted(zip(resolved, range(len(shas)), shas, strict=True))]


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
    committed = _commit_datetime(sha)
    if committed is None:
        return False
    return committed < floor


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


def json_events(data: dict, now_iso: str, *, session_id: str = "") -> list[dict]:
    """Type events from the work-log structure, not substring matching.

    ``session_id`` stamps each emitted event with ``_source_session`` so that
    ``_dedupe_events`` can evict events carried over from a different session
    during a ``--preserve`` merge (issue #4024).  Callers that do not supply a
    session_id get events without a stamp, which ``_dedupe_events`` treats as
    same-session for backward compatibility.
    """
    events: list[dict] = []
    idx = 0

    def add(evt_type: str, content: str, timestamp: str = now_iso) -> None:
        nonlocal idx
        idx += 1
        entry: dict = {
            "id": f"e{idx:03d}",
            "timestamp": timestamp,
            "type": evt_type,
            "content": content,
            "caused_by": [],
            "leads_to": [],
        }
        if session_id:
            entry["_source_session"] = session_id
        events.append(entry)

    for entry in _as_list(data.get("workLog")):
        event_timestamp = _entry_timestamp(entry, now_iso)
        title = _entry_title(entry)
        if title:
            add("milestone", title, event_timestamp)
        text = _entry_text(entry)
        if _PASS_COUNT_RE.search(text):
            evidence = _entry_field(entry, "evidence")
            outcome = _entry_field(entry, "outcome")
            add("test", (evidence or outcome or text).strip(), event_timestamp)
        if _valid_fail_match(text):
            add("error", text.strip(), event_timestamp)

    # Emit one commit event per distinct session-produced commit SHA so the
    # event stream and metrics.commits share a single provenance rule
    # (issue #3123). Excludes the starting/base SHA, including work-log
    # mentions of it, matching json_metrics. Ordered by committer date rather
    # than by provenance rank, because _link_sequential_events chains commits
    # in list order and _collect_shas puts endingCommit, the session's *last*
    # commit, first (issue #3619).
    for sha in _chronological(_collect_shas(data)):
        add("commit", f"Commit: {sha}", _git_commit_timestamp(sha) or now_iso)

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


_FULL_SHA_RE = re.compile(r"\A[0-9a-fA-F]{7,40}\Z")


def _authoritative_files_changed(data: dict[str, Any]) -> int | None:
    """Return the session-recorded episode file count when present."""
    episode_metrics = _as_dict(data.get("episodeMetrics"))
    files_changed = episode_metrics.get("filesChanged")
    if isinstance(files_changed, bool) or not isinstance(files_changed, int):
        return None
    return files_changed if files_changed >= 0 else None


def _range_files_changed(
    start: str,
    end: str,
    cwd: str | Path | None = None,
) -> int | None:
    """Count files changed by branch commits in a session range (best-effort).

    Returns ``None`` when the range cannot be measured and ``0`` when a valid
    range changes no files. The distinction lets callers use an empty range as
    authoritative without masking git failures with a false zero.

    Follow only the ending commit's first-parent path and skip merge commits.
    A normal sync from main uses the branch tip as the merge's first parent, so
    this counts session commits while excluding files that arrived from main.

    Both SHAs are shape-checked against ``_FULL_SHA_RE`` before reaching the
    command line: the values come from a JSON file, and a value like
    ``--output=/etc/passwd`` would otherwise be handed to git as a flag.
    """
    start = str(start or "").strip()
    end = str(end or "").strip()
    if not _FULL_SHA_RE.match(start) or not _FULL_SHA_RE.match(end):
        return None
    if start.lower() == end.lower():
        return 0
    cmd = ["git"]
    if cwd is not None:
        cmd += ["-C", str(cwd)]
    cmd += [
        "log",
        "--first-parent",
        "--no-merges",
        "--format=",
        "--name-only",
        f"{start}..{end}",
        "--",
    ]
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
        return None
    if result.returncode != 0:
        return None
    return len({line.strip() for line in result.stdout.splitlines() if line.strip()})


_DURATION_TEXT_RE = re.compile(r"(\d+)\s*minutes?", re.IGNORECASE)


# workLog entries spell their timestamp two ways in the tree. Measured over the
# 40 most recent session logs: 14 use "timestamp", 9 use "time", the rest carry
# neither. Reading only "time" is why duration_minutes read 0 on the majority of
# episodes (issue #3972). Accept both spellings, preferring "time".
_WORKLOG_TIME_KEYS = ("time", "timestamp")


def _duration_from_worklogs(entries: list) -> int | None:
    """Compute duration in minutes from first to last workLog timestamp.

    Returns None when fewer than two timestamped entries exist or when parsing
    fails, so a genuinely unmeasured duration stays distinguishable from a
    measured zero.
    """
    times: list[datetime] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        raw = next((entry[k] for k in _WORKLOG_TIME_KEYS if entry.get(k)), None)
        if not raw:
            continue
        try:
            dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                # Session logs use UTC by convention; legacy naive timestamps are UTC, not local time.
                dt = dt.replace(tzinfo=UTC)
            else:
                dt = dt.astimezone(UTC)
            times.append(dt)
        except (ValueError, TypeError):
            continue
    if len(times) < 2:
        return None
    delta = max(times) - min(times)
    return max(0, int(delta.total_seconds() / 60))


def _duration_from_metrics_block(metrics_block: dict) -> int | None:
    """Parse duration from the old-schema top-level metrics block.

    Handles strings like "~20 minutes" or "25 minutes" and integer values.
    Returns None when nothing parseable is found.
    """
    raw = metrics_block.get("duration") or metrics_block.get("duration_minutes")
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return max(0, int(raw))
    m = _DURATION_TEXT_RE.search(str(raw))
    return int(m.group(1)) if m else None


def json_metrics(data: dict) -> dict:
    # Count every distinct commit the session documents, from the same source
    # as the commit events so the two can never disagree: endingCommit plus the
    # session-end changesCommitted evidence, falling back to work-log prose only
    # when neither of those yields a SHA (issue #3363). Excludes the starting
    # commit: it is the base, not a commit the session produced.
    commit_count = len(_collect_shas(data))

    worklogs = _as_list(data.get("workLog"))
    metrics_block = _as_dict(data.get("metrics"))

    # duration_minutes: prefer structured timestamps (first-to-last workLog entry),
    # fall back to the old-schema metrics.duration text/integer. Stays None when
    # neither source exists, so "not measured" is distinguishable from "took no
    # measurable time" (issue #3972).
    duration = _duration_from_worklogs(worklogs)
    if duration is None:
        duration = _duration_from_metrics_block(metrics_block)

    # tool_calls: only the old schema carries a structured count (metrics.toolCalls).
    # Modern session logs have no machine-readable tool count, so this field stays
    # null for those sessions. Emitting 0 was worse than emitting nothing: a reader
    # cannot tell an unpopulated field from a session that really made no tool
    # calls, and 0 reads as "nothing happened here, skip it" (issue #3972).
    raw_tool_calls = metrics_block.get("toolCalls")
    tool_calls = int(raw_tool_calls) if raw_tool_calls is not None else None

    error_count = 0
    files_changed = 0
    for entry in worklogs:
        text = _entry_text(entry)
        fail = _valid_fail_match(text)
        if fail:
            error_count += int(fail.group(1))
        files = _FILES_RE.search(text)
        if files:
            files_changed += int(files.group(1))

    return {
        "duration_minutes": duration,
        "tool_calls": tool_calls,
        "errors": error_count,
        "recoveries": 0,
        "commits": commit_count,
        "files_changed": files_changed,
    }


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


def _preserved_timestamp(entry: dict, midnight: str | None) -> str | None:
    """Keep source time when present, otherwise use deterministic midnight.

    Normalization exists because untimestamped milestone entries fall back to
    the session timestamp and are not reproducible. Explicit work-log
    timestamps are source data, not wall clock noise, and preserve needs them to
    keep post-commit milestones after the commits they describe (issue #4588).

    A commit event's timestamp is a deterministic function of the SHA already
    in its content, so normalizing it buys no idempotence and costs the only
    evidence that separates a commit from a same-day milestone. Without it
    ``_event_order_relation`` sees equal timestamps, returns None per the #3464
    incomparability rule, and every milestone-to-commit edge is dropped on
    regeneration (issue #4071).

    Falls back to the stored timestamp before midnight so a git-less run
    (shallow clone, rebased SHA) cannot re-flatten an already-correct artifact.
    """
    if _norm(entry.get("type")) != "commit":
        timestamp = entry.get("timestamp")
        if isinstance(timestamp, str) and timestamp and timestamp != midnight:
            return timestamp
        return midnight if midnight else None
    sha = _commit_sha(entry)
    real = _git_commit_timestamp(sha) if sha else None
    timestamp = entry.get("timestamp")
    stored = timestamp if isinstance(timestamp, str) else None
    return real or stored or midnight


def _maybe_update_event_timestamp(
    target: dict[str, Any],
    incoming: dict[str, Any],
    midnight: str | None,
) -> None:
    """Upgrade a duplicate event from synthesized midnight to source time."""
    incoming_timestamp = _preserved_timestamp(incoming, midnight)
    current_timestamp = target.get("timestamp")
    if not incoming_timestamp:
        return
    if current_timestamp and (current_timestamp != midnight or incoming_timestamp == midnight):
        return
    target["timestamp"] = incoming_timestamp


def _dedupe_events(
    existing: list, new: list, midnight: str | None, *, session_id: str = ""
) -> list[dict]:
    """Union events by (type, content); normalize timestamps; reassign ids.

    When ``session_id`` is supplied, existing events that carry a
    ``_source_session`` stamp from a *different* session are dropped before the
    union.  Events with no stamp (legacy episodes written before #4024) are kept
    unchanged, preserving backward compatibility.  Events stamped with the
    current session are kept unconditionally so accumulated commit events
    survive ``--preserve`` regeneration (issue #3123).
    """
    out: list[dict] = []
    seen: set[tuple[str, str]] = set()
    filtered_existing: list[dict] = []
    for evt in existing:
        entry = _as_dict(evt)
        source = entry.get("_source_session", "")
        if source and session_id and source != session_id:
            continue  # cross-session stamp: evict
        filtered_existing.append(entry)
    positions: dict[tuple[str, str], int] = {}
    for evt in filtered_existing + list(new):
        entry = _as_dict(evt)
        key = (_norm(entry.get("type")), _norm(entry.get("content")))
        if key in seen:
            _maybe_update_event_timestamp(out[positions[key]], entry, midnight)
            continue
        seen.add(key)
        positions[key] = len(out)
        entry = dict(entry)
        stamped = _preserved_timestamp(entry, midnight)
        if stamped:
            entry["timestamp"] = stamped
        out.append(entry)
    for i, entry in enumerate(out, 1):
        entry["id"] = f"e{i:03d}"
    return out


def _total_causal_edges(events: Any) -> int:
    """Count ``leads_to`` entries across an event list.

    Regeneration rewrites the causal chain from scratch, so a drop here means
    ordering evidence was lost rather than added. Counting one direction is
    enough: ``_link_sequential_events`` writes each edge into both endpoints.
    """
    if not isinstance(events, list):
        return 0
    return sum(len(_as_list(_as_dict(evt).get("leads_to"))) for evt in events)


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
    and non-commit event timestamps normalize to the deterministic session date
    so output is idempotent. Commit events keep the real committer date, which
    is already deterministic from the SHA and is the only ordering evidence the
    causal graph has against a same-day milestone (issue #4071). Applying twice
    is a no-op.
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
        _as_list(existing.get("events")),
        _as_list(new.get("events")),
        midnight,
        session_id=session_id,
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


def default_episodes_dir() -> Path:
    """Where episodes live, for this script and for the repair pass.

    One definition so a sibling script does not have to restate the upstream
    path literal, which the vendor-portability ratchet counts per file.
    """
    return _repo_root() / ".agents" / "memory" / "episodes"


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


def extract_from_json(data: dict, *, archive_fallback: bool = True, session_id: str = "") -> dict:
    """Build the episode component bundle from a JSON session log.

    ``session_id`` is forwarded to ``json_events`` so each emitted event is
    stamped with ``_source_session``.  Pass the value from
    ``get_session_id_from_path`` at the call site.

    When ``archive_fallback`` is True and the primary JSON log yields no events
    of its own (no milestone/test/error, even if the workLog list is
    technically non-empty, e.g. ``[{}]`` or whitespace stubs), attempts to
    locate and parse the corresponding archive file (JSON first, then markdown)
    to preserve rich event/decision/lesson data from migrated sessions. A log
    that already has its own events keeps its own decisions and lessons; the
    archive is not consulted for them.
    """
    session_ts = json_timestamp(data)
    session = _as_dict(data.get("session"))

    events = json_events(data, session_ts, session_id=session_id)
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
                        archive_events = json_events(
                            archive_data, session_ts, session_id=session_id
                        )
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
        "--validate",
        action="store_true",
        help=(
            "Validate an existing episode JSON file, or every *.json under a "
            "directory, instead of extracting. Exit 2 on a duplicate, missing, "
            "or non-contiguous event id, or a commit-to-commit edge that runs "
            "backwards in committer time"
        ),
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help=(
            "With --validate, repair backwards commit order in place by "
            "restamping commit events from git and rebuilding the chain. "
            "Refuses any file whose rebuild would drop edges"
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


CAUSAL_ORDER_VERSION = 2
_CAUSAL_EVENT_TYPES = frozenset({"tool_call", "error", "milestone", "handoff", "commit", "test"})
_POST_COMMIT_SAME_TIMESTAMP_TYPES = frozenset({"error", "test"})


class EpisodeValidationError(ValueError):
    """Episode event graph validation failed with an ADR-035 exit code."""

    def __init__(self, message: str, exit_code: int) -> None:
        super().__init__(message)
        self.exit_code = exit_code


def _parse_causal_timestamp(evt: dict[str, Any]) -> datetime:
    raw = evt.get("timestamp")
    event_id = evt.get("id", "<missing>")
    if not isinstance(raw, str) or not raw.strip():
        raise EpisodeValidationError(f"event {event_id} has a missing or non-string timestamp", 2)
    normalized = raw.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise EpisodeValidationError(f"event {event_id} has an invalid timestamp", 2) from exc
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _event_refs(evt: dict[str, Any], key: str) -> list[str]:
    raw = evt.get(key, [])
    event_id = evt.get("id", "<missing>")
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise EpisodeValidationError(f"event {event_id} field {key} must be a list", 2)
    refs: list[str] = []
    for ref in raw:
        if not isinstance(ref, str) or not ref:
            msg = f"event {event_id} field {key} contains invalid ref {ref!r}"
            raise EpisodeValidationError(msg, 2)
        refs.append(ref)
    return refs


def _validate_causal_event(
    evt: dict[str, Any],
    ids: set[str],
) -> tuple[str, datetime]:
    if not isinstance(evt, dict):
        raise EpisodeValidationError("event entry must be an object", 2)
    event_id = evt.get("id")
    if not isinstance(event_id, str) or not event_id:
        raise EpisodeValidationError("event id must be a non-empty string", 2)
    if event_id in ids:
        raise EpisodeValidationError(f"duplicate event id: {event_id}", 1)
    event_type = evt.get("type")
    if not isinstance(event_type, str) or event_type not in _CAUSAL_EVENT_TYPES:
        raise EpisodeValidationError(f"event {event_id} has unsupported type: {event_type}", 2)
    return event_id, _parse_causal_timestamp(evt)


def _validate_causal_reference(
    event_id: str,
    ref: str,
    ids: set[str],
    relation: str,
) -> None:
    if ref not in ids:
        raise EpisodeValidationError(f"event {event_id} {relation} unknown event {ref}", 1)
    if ref == event_id:
        raise EpisodeValidationError(f"event {event_id} {relation} itself", 1)


def _add_causal_references(
    evt: dict[str, Any],
    ids: set[str],
    adjacency: dict[str, set[str]],
) -> None:
    event_id = str(evt["id"])
    for ref in _event_refs(evt, "leads_to"):
        _validate_causal_reference(event_id, ref, ids, "leads_to")
        adjacency[event_id].add(ref)
    for ref in _event_refs(evt, "caused_by"):
        _validate_causal_reference(event_id, ref, ids, "caused_by")
        adjacency[ref].add(event_id)


def _validate_causal_order(
    events: list[dict[str, Any]],
    timestamps: dict[str, datetime],
    adjacency: dict[str, set[str]],
) -> None:
    by_id = {str(evt["id"]): evt for evt in events}
    for source_id, target_ids in adjacency.items():
        for target_id in target_ids:
            relation = _event_order_relation(by_id[source_id], by_id[target_id], timestamps)
            if relation == 1:
                raise EpisodeValidationError(
                    f"event {source_id} leads to earlier event {target_id}", 1
                )


def validate_episode_causal_graph(
    events: list[dict[str, Any]],
    *,
    validate_order: bool = True,
) -> dict[str, datetime]:
    """Validate event ids, event types, timestamps, references, and acyclicity."""
    ids: set[str] = set()
    parsed: dict[str, datetime] = {}
    adjacency: dict[str, set[str]] = {}

    for evt in events:
        event_id, timestamp = _validate_causal_event(evt, ids)
        ids.add(event_id)
        parsed[event_id] = timestamp
        adjacency[event_id] = set()

    for evt in events:
        _add_causal_references(evt, ids, adjacency)

    if validate_order:
        _validate_causal_order(events, parsed, adjacency)
    _validate_dag(adjacency)
    return parsed


def _validate_dag(adjacency: dict[str, set[str]]) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visited:
            return
        if node in visiting:
            raise EpisodeValidationError("episode event graph contains a cycle", 1)
        visiting.add(node)
        for child in adjacency[node]:
            visit(child)
        visiting.remove(node)
        visited.add(node)

    for node in adjacency:
        visit(node)


def _commit_sha(evt: dict[str, Any]) -> str | None:
    match = _SHA_RE.search(str(evt.get("content") or ""))
    return match.group(0) if match else None


def _git_ancestor_relation(left_sha: str, right_sha: str) -> int | None:
    """Return -1 when left precedes right, 1 when right precedes left."""
    repo = _repo_root()
    env = os.environ.copy()
    env["LC_ALL"] = "C"
    checks = ((left_sha, right_sha, -1), (right_sha, left_sha, 1))
    for ancestor, descendant, relation in checks:
        result = subprocess.run(
            ["git", "-C", str(repo), "merge-base", "--is-ancestor", ancestor, descendant],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=10,
            check=False,
        )
        if result.returncode == 0:
            return relation
        if result.returncode not in (1, 128):
            return None
    return None


def _git_commit_timestamp(sha: str) -> str | None:
    repo = _repo_root()
    env = os.environ.copy()
    env["LC_ALL"] = "C"
    result = subprocess.run(
        ["git", "-C", str(repo), "show", "-s", "--format=%cI", sha],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        timeout=10,
        check=False,
    )
    if result.returncode != 0:
        return None
    raw = result.stdout.strip()
    if not raw:
        return None
    try:
        return _parse_causal_timestamp({"id": sha, "timestamp": raw}).isoformat()
    except EpisodeValidationError:
        return None


def _is_synthetic_midnight(ts: datetime) -> bool:
    """True when a timestamp has the midnight fallback shape (issue #4847).

    Untimestamped milestones receive ``{date}T00:00:00+00:00`` from
    ``_preserved_timestamp``.  Their position relative to commits is unknown,
    so ``_event_order_relation`` must treat them as incomparable rather than
    asserting they preceded every same-day commit.
    """
    return ts.hour == 0 and ts.minute == 0 and ts.second == 0 and ts.microsecond == 0


# Event types whose midnight timestamp signals unknown order relative to
# commits.  Error and test events at midnight still sort after a same-timestamp
# commit because they report on code execution (_POST_COMMIT_SAME_TIMESTAMP_TYPES).
_MIDNIGHT_INCOMPARABLE_TYPES = frozenset({"milestone", "handoff", "tool_call"})


def _event_order_relation(
    left: dict[str, Any],
    right: dict[str, Any],
    timestamps: dict[str, datetime],
) -> int | None:
    """Return -1 when left is before right, 1 for reverse, None if incomparable."""
    left_id = str(left["id"])
    right_id = str(right["id"])
    left_time = timestamps[left_id]
    right_time = timestamps[right_id]

    left_type = left["type"]
    right_type = right["type"]

    # Issue #4847: an untimestamped non-commit event that fell back to midnight
    # has unknown order relative to commits.  Return incomparable so no false
    # causal edge is emitted.
    if (
        left_type in _MIDNIGHT_INCOMPARABLE_TYPES
        and right_type == "commit"
        and _is_synthetic_midnight(left_time)
    ):
        return None
    if (
        right_type in _MIDNIGHT_INCOMPARABLE_TYPES
        and left_type == "commit"
        and _is_synthetic_midnight(right_time)
    ):
        return None

    if left_time < right_time:
        return -1
    if right_time < left_time:
        return 1

    if left_type == "commit" and right_type == "commit":
        left_sha = _commit_sha(left)
        right_sha = _commit_sha(right)
        if left_sha is None or right_sha is None:
            return None
        return _git_ancestor_relation(left_sha, right_sha)
    if left_type == "commit" and right_type in _POST_COMMIT_SAME_TIMESTAMP_TYPES:
        return -1
    if right_type == "commit" and left_type in _POST_COMMIT_SAME_TIMESTAMP_TYPES:
        return 1
    return None


def _has_alternate_path(source: str, target: str, edges: set[tuple[str, str]]) -> bool:
    stack = [child for parent, child in edges if parent == source and child != target]
    seen: set[str] = set()
    while stack:
        node = stack.pop()
        if node == target:
            return True
        if node in seen:
            continue
        seen.add(node)
        stack.extend(child for parent, child in edges if parent == node)
    return False


def _immediate_causal_edges(
    events: list[dict[str, Any]],
    timestamps: dict[str, datetime],
) -> set[tuple[str, str]]:
    ordered_edges: set[tuple[str, str]] = set()
    for left_index, left in enumerate(events):
        for right in events[left_index + 1 :]:
            relation = _event_order_relation(left, right, timestamps)
            if relation == -1:
                ordered_edges.add((str(left["id"]), str(right["id"])))
            elif relation == 1:
                ordered_edges.add((str(right["id"]), str(left["id"])))

    return {
        edge for edge in ordered_edges if not _has_alternate_path(edge[0], edge[1], ordered_edges)
    }


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
    # The counter advances per assigned id, not per list slot. Numbering by
    # position gave the event after a malformed entry a number one higher than
    # the count of events before it, so the ids this function promises to make
    # contiguous were not. Ids label events, not slots.
    index = 0
    for evt in events:
        if isinstance(evt, dict):
            index += 1
            evt["id"] = f"e{index:03d}"


def _link_sequential_events(events: list[dict[str, Any]]) -> None:
    """Populate ``caused_by``/``leads_to`` with evidence-gated causal edges.

    ADR-038 defines ``caused_by``/``leads_to`` as first-class event fields so a
    reader can walk one episode's events in causal order, but every
    event-construction site emitted them empty, leaving the chain flat
    (issue #3245). These links stay inside the episode file; the separate
    aggregated causal graph they once fed was removed by ADR-089.

    The chain follows measured timestamps first, which is why ``_dedupe_events``
    leaves a commit event's real committer date alone (issue #4071). When
    timestamps tie, commits
    are ordered only by local git ancestry. A same-timestamp commit can precede
    test and error events because those event types report on code execution.
    Same-timestamp commit and milestone events stay incomparable unless a real
    timestamp separates them, because milestones also record pre-code work such
    as issue filing or reproduction (#3464).

    Mutates in place. Must run on final ids, i.e. after any id reassignment by
    ``_dedupe_events``, so the references never dangle.

    Overwrites ``caused_by``/``leads_to`` unconditionally. Under ``--preserve``,
    ids reassigned by ``merge_preserving`` make prior edges invalid, so any
    existing values (including curated edges on a loaded episode) are replaced
    by the regenerated chain rather than retained.
    """
    timestamps = validate_episode_causal_graph(events, validate_order=False)
    ids = {str(evt["id"]) for evt in events}
    edges = _immediate_causal_edges(events, timestamps)

    for evt in events:
        evt["caused_by"] = []
        evt["leads_to"] = []
    for source, target in sorted(edges):
        if source not in ids or target not in ids:
            raise EpisodeValidationError(f"edge references unknown event: {source} -> {target}", 1)
        source_event = next(evt for evt in events if evt["id"] == source)
        target_event = next(evt for evt in events if evt["id"] == target)
        source_event["leads_to"].append(target)
        target_event["caused_by"].append(source)
    validate_episode_causal_graph(events)


def validate_event_ids(events: Any) -> list[str]:
    """Return one message per event-id violation, empty when the list is sound.

    ``_renumber_events`` makes duplicates unrepresentable on the write path, so
    this never fires for a file the extractor produced. It exists for the case
    issue #3633 names as the actual origin of the one duplicate found live: a
    hand edit or a merge-conflict resolution, which lands a file without ever
    passing through the extractor again. Prevention at write time and detection
    at rest cover different populations; neither subsumes the other.

    ``caused_by`` and ``leads_to`` reference events by id, so a duplicate makes
    every edge touching it ambiguous and a gap means an edge can dangle.
    """
    problems: list[str] = []
    if not isinstance(events, list):
        return [f"events must be a list, got {type(events).__name__}"]

    seen: dict[str, int] = {}
    for position, event in enumerate(events, 1):
        if not isinstance(event, dict):
            problems.append(f"event {position} is not an object")
            continue
        identifier = event.get("id")
        if not isinstance(identifier, str) or not identifier:
            problems.append(f"event {position} has no id")
            continue
        if identifier in seen:
            problems.append(
                f"duplicate event id {identifier} at positions {seen[identifier]} and {position}"
            )
            continue
        seen[identifier] = position
        expected = f"e{position:03d}"
        if identifier != expected:
            problems.append(f"event {position} has id {identifier}, expected {expected}")
    return problems


def validate_metrics_consistency(metrics: Any) -> list[str]:
    """Return one message per metrics-consistency violation.

    Catches the specific case where commits==0 but files_changed>0, which
    indicates the episode's commit-collection logic failed to record the
    commits that produced the file changes (issue #3873).
    """
    if not isinstance(metrics, dict):
        return []
    try:
        commits = int(metrics.get("commits") or 0)
    except (TypeError, ValueError):
        commits = 0
    try:
        files_changed = int(metrics.get("files_changed") or 0)
    except (TypeError, ValueError):
        files_changed = 0
    if commits == 0 and files_changed > 0:
        return [
            f"metrics.commits==0 but metrics.files_changed=={files_changed};"
            " commit collection may have failed"
        ]
    return []


def _commit_event_dates(events: list) -> dict[str, datetime]:
    """Map event id to committer date, for commit events reachable from a named ref.

    Reachability (``git for-each-ref --contains``) is the filter, not mere
    resolvability (``git cat-file -t``). A SHA that resolves but is reachable
    from zero refs is a dangling object: clone residue from a squash-merged
    branch. Whether it is present depends on local ``git gc`` timing, not on
    the repository content, so the same artifact produces different verdicts on
    different machines. Issue #4240, CI-scripts rule MUST-9: a claim about what
    the repository contains MUST be computed from a named ref.

    Treating an unreachable SHA as absent matches the intent of the original
    skip-when-unresolvable policy from #4219: absence of evidence is not
    evidence of order.
    """
    dates: dict[str, datetime] = {}
    for evt in events:
        entry = _as_dict(evt)
        identifier = entry.get("id")
        if entry.get("type") != "commit" or not isinstance(identifier, str):
            continue
        sha = _commit_sha(entry)
        if not sha or not _sha_is_reachable(sha):
            continue
        moment = _commit_datetime(sha)
        if moment is not None:
            dates[identifier] = moment
    return dates


def validate_commit_order(events: Any) -> list[str]:
    """Return one message per commit-to-commit edge that runs backwards in time.

    ``leads_to`` claims the source commit preceded the target. When git says the
    target was committed first, the episode records an effect as its own cause.
    17 such edges shipped across 14 episodes, written by the pre-#3638 linker,
    which chained commits by list position while ``_collect_shas`` put the
    session's *last* commit first. Issue #3765 named nine files; the same defect
    shape reached six more it did not list, and one it did list carries no
    verifiable edge because none of its abbreviated SHAs still resolves.

    Only commit-to-commit edges are checked, and only where git resolves both
    SHAs. Every other edge type is ordered by event timestamps this function has
    no independent evidence about.
    """
    if not isinstance(events, list):
        return []
    dates = _commit_event_dates(events)
    problems: list[str] = []
    for evt in events:
        entry = _as_dict(evt)
        source = entry.get("id")
        if not isinstance(source, str) or source not in dates:
            continue
        for raw_target in _as_list(entry.get("leads_to")):
            target = raw_target if isinstance(raw_target, str) else ""
            if target not in dates or dates[target] >= dates[source]:
                continue
            problems.append(
                f"commit edge {source} -> {target} runs backwards: "
                f"{dates[source].isoformat()} then {dates[target].isoformat()}"
            )
    return problems


def _event_causal_edges(evt: Any) -> list[tuple[str, str]]:
    if not isinstance(evt, dict) or not isinstance(evt.get("id"), str):
        return []
    event_id = str(evt["id"])
    return [(event_id, ref) for ref in _event_refs(evt, "leads_to")] + [
        (ref, event_id) for ref in _event_refs(evt, "caused_by")
    ]


def _causal_order_problem(
    source: str,
    target: str,
    by_id: dict[str, dict[str, Any]],
) -> str | None:
    source_event = by_id.get(source)
    target_event = by_id.get(target)
    if source_event is None or target_event is None:
        return f"causal edge {source} -> {target} references unknown event"
    try:
        timestamps = {
            source: _parse_causal_timestamp(source_event),
            target: _parse_causal_timestamp(target_event),
        }
        relation = _event_order_relation(source_event, target_event, timestamps)
    except (EpisodeValidationError, KeyError) as exc:
        return f"causal edge {source} -> {target} cannot be ordered: {exc}"
    if relation == 1:
        return f"event {source} leads to earlier event {target}"
    return None


def validate_causal_edge_order(events: Any) -> list[str]:
    """Return one message when a causal edge runs backward by event ordering."""
    if not isinstance(events, list):
        return []
    by_id = {
        str(evt.get("id")): evt
        for evt in events
        if isinstance(evt, dict) and isinstance(evt.get("id"), str)
    }
    problems: list[str] = []
    checked: set[tuple[str, str]] = set()
    for evt in events:
        try:
            edges = _event_causal_edges(evt)
        except EpisodeValidationError as exc:
            problems.append(str(exc))
            continue
        for source, target in edges:
            if (source, target) in checked:
                continue
            checked.add((source, target))
            problem = _causal_order_problem(source, target, by_id)
            if problem:
                problems.append(problem)
    return problems


def validate_causal_edge_consistency(events: Any) -> list[str]:
    """Return stored-vs-derived causal edge mismatches."""
    if not isinstance(events, list):
        return []
    try:
        timestamps = validate_episode_causal_graph(events, validate_order=False)
    except EpisodeValidationError as exc:
        return [str(exc)]

    stored_leads_to: set[tuple[str, str]] = set()
    stored_caused_by: set[tuple[str, str]] = set()
    for evt in events:
        event_id = str(evt["id"])
        stored_leads_to.update((event_id, ref) for ref in _event_refs(evt, "leads_to"))
        stored_caused_by.update((ref, event_id) for ref in _event_refs(evt, "caused_by"))

    derivable = _immediate_causal_edges(events, timestamps)
    stored = stored_leads_to | stored_caused_by
    problems = [
        f"causal edge {source} -> {target} is stored but not derivable"
        for source, target in sorted(stored - derivable)
    ]
    problems.extend(
        f"causal edge {source} -> {target} is derivable but missing"
        for source, target in sorted(derivable - stored)
    )
    problems.extend(
        f"causal edge {source} -> {target} is missing reciprocal caused_by"
        for source, target in sorted(stored_leads_to - stored_caused_by)
    )
    problems.extend(
        f"causal edge {source} -> {target} is missing reciprocal leads_to"
        for source, target in sorted(stored_caused_by - stored_leads_to)
    )
    return problems


def _edge_count(events: list) -> int:
    """Total ``leads_to`` edges across ``events``."""
    return sum(len(_as_list(_as_dict(evt).get("leads_to"))) for evt in events)


def _real_edge_count(events: list) -> int:
    """Edge count excluding false edges from synthetic-midnight incomparable events.

    Edges originating from milestone/handoff/tool_call events at midnight are
    false causal claims (issue #4847).  The repair guard must not protect them.
    """
    count = 0
    for evt in events:
        entry = _as_dict(evt)
        if entry.get("type") in _MIDNIGHT_INCOMPARABLE_TYPES:
            ts_str = entry.get("timestamp", "")
            try:
                ts = datetime.fromisoformat(ts_str)
            except (ValueError, TypeError):
                ts = None
            if ts is not None and _is_synthetic_midnight(ts):
                continue
        count += len(_as_list(entry.get("leads_to")))
    return count


def repair_commit_order(events: list) -> str | None:
    """Restamp commit events from git and rebuild the chain. Return a refusal.

    Returns ``None`` on success and a one-line reason when the repair is
    refused, leaving ``events`` untouched in that case.

    Relinking alone is not a repair. These episodes carry session-date midnight
    on every event, so ``_event_order_relation`` cannot separate a commit from a
    same-day milestone and drops the edge as incomparable: over the fourteen
    affected files a bare relink takes 234 edges to 96 and strands 163 of 263
    events with no edge at all, up from 4. An edgeless graph carries no
    backwards edge, so the check this repair exists to satisfy cannot see that
    damage. Restamping first restores the evidence the ordering rule needs, and
    the edge-count guard below refuses any repair that still loses edges.
    """
    dates = _commit_event_dates(events)
    if not dates:
        return "no commit event resolves to a git commit in this checkout"
    before = copy.deepcopy(events)
    for evt in events:
        entry = evt if isinstance(evt, dict) else None
        if entry is not None and entry.get("id") in dates:
            entry["timestamp"] = dates[entry["id"]].isoformat()
    try:
        _renumber_events(events)
        _link_sequential_events(events)
    except EpisodeValidationError as exc:
        events[:] = before
        return f"relink failed: {exc}"
    lost = _real_edge_count(before) - _real_edge_count(events)
    if lost > 0:
        events[:] = before
        return f"refused: relink would drop {lost} of {_real_edge_count(before)} edges"
    return None


def _read_episode(path: Path) -> tuple[dict | None, str]:
    """Return the parsed episode at ``path``, or ``None`` and why it is unusable."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, f"unreadable: {exc}"
    if not isinstance(data, dict):
        return None, "top level must be an object"
    return data, ""


def validate_episode_file(path: Path) -> list[str]:
    """Return one message per violation found in the episode JSON at ``path``."""
    data, failure = _read_episode(path)
    if data is None:
        return [f"{path}: {failure}"]
    events = data.get("events")
    problems = validate_event_ids(events)
    if not problems:
        problems = [
            *validate_commit_order(events),
            *validate_causal_edge_order(events),
            *validate_causal_edge_consistency(events),
        ]
    problems = [*problems, *validate_metrics_consistency(data.get("metrics"))]
    return [f"{path}: {problem}" for problem in problems]


def repair_episode_file(path: Path) -> tuple[bool, list[str]]:
    """Repair backwards commit order at ``path``.

    Returns whether the file was rewritten, and one message per reason the
    repair could not proceed.

    A file with no backwards commit edge is left alone: this repair addresses
    that defect only, and rewriting a sound episode would churn timestamps no
    check objects to. That decision lives here rather than in the caller so one
    read of the file answers both questions.

    An unreadable file yields no message. ``run_validate`` calls
    ``validate_episode_file`` on the same path straight after, and that reports
    the identical ``_read_episode`` text; returning it here too printed the line
    twice under ``--validate --fix`` and told the reader nothing new.
    """
    data, _ = _read_episode(path)
    if data is None:
        return False, []
    events = data.get("events")
    if not isinstance(events, list) or not validate_commit_order(events):
        return False, []
    refusal = repair_commit_order(events)
    if refusal:
        return False, [f"{path}: {refusal}"]
    try:
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        return False, [f"{path}: write failed: {exc}"]
    return True, []


def _episode_paths(target: Path) -> list[Path]:
    """Expand ``target`` to the episode files it names."""
    if target.is_dir():
        return sorted(target.glob("*.json"))
    return [target]


def run_validate(target: Path, *, fix: bool = False) -> int:
    """Validate an episode file or a directory of them. Exit 2 on violation.

    With ``fix``, repair backwards commit order in place first, then report on
    what the repair left. A refused repair still counts as a violation, so the
    exit code never claims a file was fixed when it was not.
    """
    paths = _episode_paths(target)
    if not paths:
        print(json.dumps({"Error": f"No episode files under {target}"}), file=sys.stderr)
        return 2
    repaired = 0
    if fix:
        for path in paths:
            changed, failures = repair_episode_file(path)
            for failure in failures:
                print(failure, file=sys.stderr)
            repaired += int(changed)
    problems = [problem for path in paths for problem in validate_episode_file(path)]
    for problem in problems:
        print(problem, file=sys.stderr)
    summary: dict[str, int] = {"Validated": len(paths), "Violations": len(problems)}
    if fix:
        summary["Repaired"] = repaired
    print(json.dumps(summary), file=sys.stderr)
    return 2 if problems else 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if ".." in args.session_log_path.parts:
        msg = "Security: path must not contain traversal sequences."
        print(json.dumps({"Error": msg}), file=sys.stderr)
        return 2
    session_log_path = args.session_log_path.resolve()

    if args.validate:
        if not session_log_path.exists():
            print(
                json.dumps({"Error": f"Path not found: {session_log_path}"}),
                file=sys.stderr,
            )
            return 1
        return run_validate(session_log_path, fix=args.fix)

    if args.fix:
        print(
            json.dumps({"Error": "--fix requires --validate"}),
            file=sys.stderr,
        )
        return 2

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
        output_path = default_episodes_dir()

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

    authoritative_files_changed: int | None = None
    json_data = looks_like_json_session(content)
    if json_data is not None:
        print("  Parsing JSON session log...", file=sys.stderr)
        authoritative_files_changed = _authoritative_files_changed(json_data)
        bundle = extract_from_json(json_data, session_id=session_id)
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

    ranged: int | None = None
    if json_data is not None:
        session_block = _as_dict(json_data.get("session"))
        ranged = _range_files_changed(
            session_block.get("startingCommit", ""),
            json_data.get("endingCommit", ""),
            session_log_path.parent,
        )

    measured_files_changed = (
        authoritative_files_changed if authoritative_files_changed is not None else ranged
    )
    staged = _staged_files_changed(session_log_path.parent)
    if measured_files_changed is not None:
        metrics["files_changed"] = measured_files_changed
    elif staged:
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
        measured_files_changed = staged
        metrics["files_changed"] = staged

    episode = {
        "id": f"episode-{session_id}",
        "session": session_id,
        "timestamp": timestamp,
        "causal_order_version": CAUSAL_ORDER_VERSION,
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
    prior_edges: int | None = None

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
                                "--preserve requires the existing episode to be a JSON object."
                            ),
                        }
                    ),
                    file=sys.stderr,
                )
                return 1
            prior_edges = _total_causal_edges(existing_raw.get("events"))
            episode = merge_preserving(episode, existing_raw, session_id=session_id)
            if measured_files_changed is not None:
                episode["metrics"]["files_changed"] = measured_files_changed
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
    try:
        _link_sequential_events(episode["events"])
    except EpisodeValidationError as exc:
        print(json.dumps({"Error": str(exc)}), file=sys.stderr)
        return exc.exit_code

    new_edges = _total_causal_edges(episode["events"])
    if prior_edges is not None and new_edges < prior_edges:
        print(
            f"WARNING: causal edge count decreased: {prior_edges} -> {new_edges}",
            file=sys.stderr,
        )

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
