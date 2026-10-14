"""Transcript parsing, correction cues, aggregation, and ranking."""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

# Word-boundary correction cues. These are WEAK labels for ranking candidates,
# not gold pass/fail labels for the gate. Tuned for PRECISION: an early version
# included bare "no", "don't", "actually", "stop" and every skill scored a ~1.0
# correction rate (they match "no problem", "don't worry", "actually nice").
# These survivors are explicit dissatisfaction with the prior turn. Gold labels
# for a real gate come from an agent judging each exchange; this just prioritizes.
CORRECTION_CUES = (
    r"\bthat'?s not\b", r"\bnot right\b", r"\bnot correct\b", r"\bincorrect\b",
    r"\bthat'?s wrong\b", r"\bis wrong\b", r"\bwrong\b", r"\brevert\b", r"\bundo\b",
    r"\bredo\b", r"\bdoesn'?t work\b", r"\bdoes not work\b", r"\bdidn'?t work\b",
    r"\bdid not work\b", r"\bnot what i\b", r"\btry again\b", r"\bbroke\b",
    r"\bbroken\b", r"\byou missed\b", r"\bstill (?:wrong|broken|failing|fails)\b",
)  # fmt: skip
_CORRECTION_RE = re.compile("|".join(CORRECTION_CUES), re.IGNORECASE)

_COMMAND_RE = re.compile(
    r"<command-name>\s*/?([a-z0-9][a-z0-9_-]*)\s*</command-name>", re.IGNORECASE
)

# Copilot CLI renders a skill invocation as `skill(<name>)` in the assistant
# response text (e.g. "skill(skillopt)"). Used only when ingesting Copilot's
# SQLite store, so it never pollutes Claude tool_use counts.
_SKILL_CALL_RE = re.compile(r"\bskill\(([a-z0-9][a-z0-9_-]*)\)", re.IGNORECASE)


def is_correction(text: str) -> bool:
    """True if a user message reads as a correction of the prior turn."""
    if not isinstance(text, str):
        return False
    return _CORRECTION_RE.search(text) is not None


def _content_text(message: dict[str, Any]) -> str:
    """Flatten a message's content to plain text (string or block list)."""
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and isinstance(block.get("text"), str):
                parts.append(block["text"])
        return "\n".join(parts)
    return ""


def extract_skill_invocations(record: dict[str, Any]) -> list[str]:
    """Skill names invoked in this record (Skill tool_use + slash-command tags)."""
    skills: list[str] = []
    message = record.get("message")
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, list):
            for block in content:
                if not isinstance(block, dict) or block.get("type") != "tool_use":
                    continue
                if block.get("name") != "Skill":
                    continue
                inp = block.get("input")
                if isinstance(inp, dict):
                    name = inp.get("skill") or inp.get("command")
                    if isinstance(name, str) and name:
                        skills.append(name.strip())
        skills.extend(_COMMAND_RE.findall(_content_text(message)))
    # last-prompt records carry the raw typed prompt (slash commands included)
    if record.get("type") == "last-prompt":
        prompt = record.get("prompt") or record.get("text")
        if isinstance(prompt, str):
            skills.extend(_COMMAND_RE.findall(prompt))
    return skills


def user_text(record: dict[str, Any]) -> str | None:
    """The user's plain-text message for a user record, else None."""
    if record.get("type") != "user":
        return None
    message = record.get("message")
    if not isinstance(message, dict):
        return None
    return _content_text(message)


def iter_records(paths: Iterable[Path]) -> Iterator[dict[str, Any]]:
    """Stream-parse jsonl transcripts, skipping unreadable lines/files."""
    for path in paths:
        try:
            with path.open(encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(record, dict):
                        yield record
        except OSError:
            continue


def _copilot_turns(db_path: Path) -> list[tuple[Any, ...]]:
    """Read (user_message, assistant_response) rows; any failure yields none."""
    if not db_path.is_file():
        return []
    uri = db_path.resolve().as_uri() + "?mode=ro"  # as_uri also handles Windows drives
    try:
        con = sqlite3.connect(uri, uri=True)
    except sqlite3.Error:
        return []
    try:
        return con.execute(
            "SELECT user_message, assistant_response FROM turns ORDER BY session_id, turn_index"
        ).fetchall()
    except sqlite3.Error:
        return []
    finally:
        con.close()


def iter_copilot_records(db_path: Path) -> Iterator[dict[str, Any]]:
    """Yield Claude-shaped pseudo-records from a Copilot `session-store.db`.

    Each `turns` row (user_message, assistant_response) becomes a user record
    plus, if the assistant text contains `skill(name)` calls, a synthetic
    assistant record carrying Skill tool_use blocks. Reusing the Claude record
    shape means `aggregate`, `extract_skill_invocations`, and `extract_tasks`
    work on Copilot data with no special-casing. Read-only; a missing, locked,
    or non-SQLite file yields nothing rather than raising.
    """
    for user_message, assistant_response in _copilot_turns(db_path):
        if isinstance(user_message, str) and user_message.strip():
            yield {"type": "user", "message": {"content": user_message}}
        if isinstance(assistant_response, str):
            blocks = [
                {"type": "tool_use", "name": "Skill", "input": {"skill": name}}
                for name in _SKILL_CALL_RE.findall(assistant_response)
            ]
            if blocks:
                yield {"type": "assistant", "message": {"content": blocks}}


def aggregate(records: Iterable[dict[str, Any]], window: int = 2) -> dict[str, dict[str, int]]:
    """Per-skill {invocations, corrections}. A correction within `window` user
    turns of a skill invocation is attributed to that skill.

    Window tuning (measured on one corpus of 306 skill invocations): window=1
    attributes 0 corrections (users rarely correct in the literal next turn);
    window=2 attributes 77 across 28 skills (discriminating); larger windows add
    noise. Default 2. Corrections are a WEAK ranking signal, not a gate label.
    """
    stats: dict[str, dict[str, int]] = {}
    # [name, age_in_user_turns, credited] for skills still in window. Each
    # invocation earns at most one correction, so corrections <= invocations.
    recent: list[list[Any]] = []
    for record in records:
        for name in extract_skill_invocations(record):
            stats.setdefault(name, {"invocations": 0, "corrections": 0})
            stats[name]["invocations"] += 1
            recent.append([name, 0, False])
        text = user_text(record)
        if text is not None:  # a user turn
            if is_correction(text):
                for entry in recent:
                    if not entry[2]:
                        stats[entry[0]]["corrections"] += 1
                        entry[2] = True
            for entry in recent:
                entry[1] += 1
            recent = [entry for entry in recent if entry[1] < window]
    return stats


def rank(stats: dict[str, dict[str, int]], known: set[str] | None = None) -> list[dict[str, Any]]:
    """Rank skills by a target score: invocations weighted by correction rate.

    correction_rate = corrections / invocations. target = invocations *
    (0.25 + correction_rate): rewards both volume (enough eval tasks) and signal
    (room to improve). `known` (repo skills) flags which are locally optimizable.
    """
    rows: list[dict[str, Any]] = []
    for name, s in stats.items():
        inv = s["invocations"]
        corr = s["corrections"]
        rate = corr / inv if inv else 0.0
        rows.append(
            {
                "skill": name,
                "invocations": inv,
                "corrections": corr,
                "correction_rate": round(rate, 3),
                "target_score": round(inv * (0.25 + rate), 2),
                "in_repo": (known is None) or (name in known),
            }
        )
    rows.sort(key=lambda r: r["target_score"], reverse=True)
    return rows


def extract_tasks(records: Iterable[dict[str, Any]], skill: str, window: int = 4) -> list[str]:
    """The user prompts that most recently preceded each invocation of `skill`."""
    tasks: list[str] = []
    pending: list[str] = []  # recent user prompts
    for record in records:
        text = user_text(record)
        if text and text.strip():
            pending.append(text.strip())
            pending = pending[-window:]
        if skill in extract_skill_invocations(record) and pending:
            tasks.append(pending[-1])
    return tasks
