#!/usr/bin/env python3
"""Detect agent loops: repeated topics across responses, or repeated tool failures.

Two independent detectors share this module:

- ``check`` tracks response topic signatures in a JSON history file. When the
  most recent N entries exceed a Jaccard similarity threshold, it emits a
  nudge payload so the orchestrator can break the loop.
- ``check-failures`` is stateless. It reads a list of recent tool events and
  reports two signals adapted from TokenEconomizer's failure-loop guard
  (https://github.com/microsoft/TokenEconomizer, tokeneconomizer/loopguard):
  the same failure fingerprint repeating, and one file edited again and again
  while the same failure keeps coming back. Unlike TokenEconomizer it calls no
  judge model, runs in no hook, and never stops a turn; it only reports.

EXIT CODES (ADR-035):
    0 - Success (regardless of stuck/not-stuck)
    2 - Invalid command, arguments, or check-failures event input

This module is intentionally stdlib-only and self-contained. It does not
import from `semantic_hooks` so behavior stays deterministic regardless of
which optional packages happen to be installed in the environment.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DEFAULT_FAILURE_REPEAT = 3
DEFAULT_EDIT_CHURN = 3
DEFAULT_FAILURE_WINDOW = 20
MAX_EVENTS = 10_000
FINGERPRINT_MAX_CHARS = 200
EDIT_TOOLS: frozenset[str] = frozenset(
    {"edit", "write", "multiedit", "str_replace", "create", "apply_patch", "notebookedit"}
)
_HEX_RUN = re.compile(r"\b(?:0x)?[0-9a-f]{7,}\b")
_DIGIT_RUN = re.compile(r"\d+")
_WHITESPACE_RUN = re.compile(r"\s+")

DEFAULT_MAX_HISTORY = 10
DEFAULT_STUCK_THRESHOLD = 3
DEFAULT_SIMILARITY_THRESHOLD = 0.6
MIN_SIGNIFICANT_WORDS = 2
MIN_TEXT_LENGTH = 50
SIGNATURE_SIZE = 5
MIN_WORD_LENGTH = 4

STOP_WORDS: frozenset[str] = frozenset(
    [
        "the",
        "a",
        "an",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "could",
        "should",
        "may",
        "might",
        "shall",
        "can",
        "need",
        "dare",
        "ought",
        "used",
        "to",
        "of",
        "in",
        "for",
        "on",
        "with",
        "at",
        "by",
        "from",
        "as",
        "into",
        "through",
        "during",
        "before",
        "after",
        "above",
        "below",
        "between",
        "out",
        "off",
        "over",
        "under",
        "again",
        "further",
        "then",
        "once",
        "here",
        "there",
        "when",
        "where",
        "why",
        "how",
        "all",
        "both",
        "each",
        "few",
        "more",
        "most",
        "other",
        "some",
        "such",
        "no",
        "nor",
        "not",
        "only",
        "own",
        "same",
        "so",
        "than",
        "too",
        "very",
        "just",
        "don",
        "now",
        "and",
        "but",
        "or",
        "if",
        "while",
        "that",
        "this",
        "it",
        "i",
        "you",
        "we",
        "they",
        "he",
        "she",
        "my",
        "your",
        "his",
        "her",
        "its",
        "our",
        "their",
        "what",
        "which",
        "who",
        "whom",
        "okay",
        "yes",
        "no",
        "thanks",
        "thank",
        "please",
        "sorry",
        "hello",
        "hi",
        "hey",
        "sure",
        "right",
        "well",
        "also",
        "still",
        "already",
        "done",
        "going",
        "want",
        "like",
        "know",
        "think",
        "make",
        "take",
        "get",
        "see",
        "come",
        "look",
        "use",
        "find",
        "give",
        "tell",
        "work",
    ]
)


def default_history_path() -> Path:
    """Resolve the default history file path.

    Resolution order:
      1. `STUCK_DETECTION_HISTORY` env var (full path).
      2. `STUCK_DETECTION_SESSION` env var (per-session file under XDG dir).
      3. `$XDG_STATE_HOME/claude-stuck-detection/history.json`.
      4. `~/.local/state/claude-stuck-detection/history.json` (global fallback).

    Callers running multiple concurrent sessions should set
    `STUCK_DETECTION_SESSION` to a unique identifier to avoid cross-session
    contamination of signatures.
    """
    override = os.environ.get("STUCK_DETECTION_HISTORY")
    if override:
        return Path(override).expanduser().resolve()

    xdg = os.environ.get("XDG_STATE_HOME")
    base = Path(xdg).expanduser() if xdg else Path.home() / ".local" / "state"
    base = (base / "claude-stuck-detection").resolve()

    session = os.environ.get("STUCK_DETECTION_SESSION")
    if session:
        safe = re.sub(r"[^A-Za-z0-9._-]", "_", session)
        return (base / f"history-{safe}.json").resolve()

    return (base / "history.json").resolve()


def extract_topic_signature(text: str) -> str | None:
    """Extract a sorted, comma-joined signature of the top significant words.

    Returns None for short or low-content text.
    """
    if not text or len(text) < MIN_TEXT_LENGTH:
        return None

    cleaned = re.sub(r"[^\w\s]", " ", text.lower())
    tokens = [w for w in cleaned.split() if len(w) > MIN_WORD_LENGTH - 1 and w not in STOP_WORDS]
    if not tokens:
        return None

    freq: dict[str, int] = {}
    for token in tokens:
        freq[token] = freq.get(token, 0) + 1

    top = sorted(freq.items(), key=lambda kv: (-kv[1], kv[0]))[:SIGNATURE_SIZE]
    words = sorted(word for word, _ in top)
    if len(words) < MIN_SIGNIFICANT_WORDS:
        return None

    return ",".join(words)


def jaccard_similarity(sig_a: str, sig_b: str) -> float:
    """Compute Jaccard similarity between two comma-joined signatures.

    Empty tokens (from leading/trailing/repeated commas, or empty inputs) are
    filtered out so that two empty signatures return 0.0 rather than 1.0.
    """
    set_a = {tok for tok in sig_a.split(",") if tok}
    set_b = {tok for tok in sig_b.split(",") if tok}
    union = set_a | set_b
    if not union:
        return 0.0
    return len(set_a & set_b) / len(union)


def load_history(path: Path) -> list[dict[str, str]]:
    """Read history; return empty list on missing, unreadable, or malformed file.

    Validates that the persisted JSON is a list of `{signature, timestamp}`
    string-keyed string-valued entries. A wrong-shaped payload is treated as
    corrupt and discarded so callers always see a clean list.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return []
    if not isinstance(data, list):
        return []
    history: list[dict[str, str]] = []
    for entry in data:
        if not isinstance(entry, dict):
            return []
        signature = entry.get("signature")
        timestamp = entry.get("timestamp")
        if not isinstance(signature, str) or not isinstance(timestamp, str):
            return []
        history.append({"signature": signature, "timestamp": timestamp})
    return history


def save_history(path: Path, history: list[dict[str, str]], max_history: int) -> None:
    """Persist the most recent `max_history` entries atomically.

    Writes to a sibling temp file then `os.replace`s it onto the target.
    The replace is atomic on POSIX and Windows, so a crash mid-write leaves
    either the prior file or the new file, never a truncated one.
    Concurrent writers can still race for last-writer-wins on `replace`,
    but neither outcome is corrupt.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    trimmed = history[-max_history:]
    payload = json.dumps(trimmed, indent=2)
    fd, tmp_name = tempfile.mkstemp(
        prefix=path.name + ".",
        suffix=".tmp",
        dir=str(path.parent),
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_path, path)
    except OSError:
        tmp_path.unlink(missing_ok=True)
        raise


def build_nudge(signature: str) -> str:
    """Build the loop-breaking nudge payload."""
    words = signature.split(",")
    return (
        "<stuck-detection>\n"
        "SELF-REFLECTION: Loop detected.\n"
        f"- Repeating topic words: {', '.join(words)}\n"
        "- Pattern: response content overlaps recent turns\n"
        "\n"
        "BREAK THE LOOP:\n"
        "1. Ask the user a direct question about their goal\n"
        "2. Wait for input instead of volunteering more\n"
        "3. If you must respond, change topic or framing\n"
        "4. Do not repeat status updates unless explicitly asked\n"
        "</stuck-detection>"
    )


def check_stuck(
    text: str,
    history_path: Path,
    *,
    stuck_threshold: int = DEFAULT_STUCK_THRESHOLD,
    similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
    max_history: int = DEFAULT_MAX_HISTORY,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Append the signature for `text` and report whether the agent is stuck."""
    if max_history < stuck_threshold:
        raise ValueError(
            f"max_history ({max_history}) must be >= stuck_threshold "
            f"({stuck_threshold}) so the persisted window can hold enough "
            "entries to evaluate."
        )

    signature = extract_topic_signature(text)
    if signature is None:
        return {"stuck": False, "signature": None, "reason": "no-signature"}

    history = load_history(history_path)
    timestamp = (now or datetime.now(UTC)).isoformat()
    history.append({"signature": signature, "timestamp": timestamp})
    history = history[-max_history:]
    save_history(history_path, history, max_history)

    if len(history) < stuck_threshold:
        return {"stuck": False, "signature": signature, "reason": "warming-up"}

    recent = history[-stuck_threshold:]
    similar = sum(
        1
        for entry in recent
        if jaccard_similarity(signature, entry["signature"]) > similarity_threshold
    )

    if similar >= stuck_threshold:
        return {
            "stuck": True,
            "signature": signature,
            "similar_count": similar,
            "nudge": build_nudge(signature),
        }
    return {"stuck": False, "signature": signature, "similar_count": similar}


class EventError(ValueError):
    """Raised when the tool-event input does not match the documented shape."""


def failure_fingerprint(tool: str, error: str) -> str:
    """Reduce a tool failure to a stable key: tool plus its first error line.

    Hex runs of 7 or more characters (hashes, addresses) become ``H`` and
    digit runs (line numbers, PIDs, durations) become ``N`` so the same failure
    at a different line or on a different run still matches. The line is
    lowercased, whitespace-collapsed, and capped at ``FINGERPRINT_MAX_CHARS``.
    """
    first = next((line for line in error.splitlines() if line.strip()), "")
    line = first.strip().lower()
    line = _HEX_RUN.sub("H", line)
    line = _DIGIT_RUN.sub("N", line)
    line = _WHITESPACE_RUN.sub(" ", line)[:FINGERPRINT_MAX_CHARS]
    return f"{tool.strip().lower()}|{line}"


def parse_events(raw: Any) -> list[dict[str, Any]]:
    """Validate the decoded JSON input and return normalized events.

    Accepts a list of objects. Each object needs ``tool`` (non-empty string)
    and ``ok`` (boolean). ``error`` (string) is read only when ``ok`` is false;
    ``target`` (string) names the file an edit tool changed. Unknown keys are
    ignored. Anything else raises ``EventError`` naming the bad index.
    """
    if not isinstance(raw, list):
        raise EventError("input must be a JSON array of tool events")
    if len(raw) > MAX_EVENTS:
        raise EventError(f"input holds {len(raw)} events; the limit is {MAX_EVENTS}")
    events: list[dict[str, Any]] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise EventError(f"event {index} is not an object")
        tool = item.get("tool")
        ok = item.get("ok")
        if not isinstance(tool, str) or not tool.strip():
            raise EventError(f"event {index}: 'tool' must be a non-empty string")
        if not isinstance(ok, bool):
            raise EventError(f"event {index}: 'ok' must be true or false")
        error = item.get("error", "")
        target = item.get("target")
        if not isinstance(error, str):
            raise EventError(f"event {index}: 'error' must be a string")
        if target is not None and not isinstance(target, str):
            raise EventError(f"event {index}: 'target' must be a string")
        events.append({"tool": tool, "ok": ok, "error": error, "target": target or None})
    return events


def _is_edit(event: dict[str, Any]) -> bool:
    return event["tool"].strip().lower() in EDIT_TOOLS and event["target"] is not None


def detect_failure_repeat(events: list[dict[str, Any]], threshold: int) -> list[dict[str, Any]]:
    """Fingerprints that failed at least ``threshold`` times, most frequent first."""
    counts: dict[str, int] = {}
    for event in events:
        if not event["ok"]:
            key = failure_fingerprint(event["tool"], event["error"])
            counts[key] = counts.get(key, 0) + 1
    hits = [(key, n) for key, n in counts.items() if n >= threshold]
    hits.sort(key=lambda kv: (-kv[1], kv[0]))
    return [{"signal": "failure-repeat", "fingerprint": key, "count": n} for key, n in hits]


def detect_edit_churn(events: list[dict[str, Any]], threshold: int) -> list[dict[str, Any]]:
    """Files edited at least ``threshold`` times where the same failure followed each edit.

    The first failure after an edit is that edit's outcome. A success counts
    as progress, and resets the churn state (pending edits and the outcomes
    counted so far), only when its tool already failed earlier in the window:
    a check that failed and now passes ends the loop. Other
    successes (reads, searches) leave the chain alone, so the common
    edit, read, re-run cycle still counts. A file is churning when
    ``threshold`` of its edits share one outcome fingerprint. Failed edits are
    ignored.
    """
    outcomes: dict[str, dict[str, int]] = {}
    pending: set[str] = set()
    failed_tools: set[str] = set()
    for event in events:
        tool = event["tool"].strip().lower()
        if _is_edit(event):
            if event["ok"]:
                pending.add(event["target"])
            continue
        if event["ok"]:
            if tool in failed_tools:
                pending.clear()
                outcomes.clear()
            continue
        failed_tools.add(tool)
        if not pending:
            continue
        key = failure_fingerprint(event["tool"], event["error"])
        for target in pending:
            per_file = outcomes.setdefault(target, {})
            per_file[key] = per_file.get(key, 0) + 1
        pending.clear()
    hits: list[dict[str, Any]] = []
    for target in sorted(outcomes):
        key, n = max(outcomes[target].items(), key=lambda kv: (kv[1], kv[0]))
        if n >= threshold:
            hits.append({"signal": "edit-churn", "target": target, "fingerprint": key, "count": n})
    return hits


def build_failure_nudge(signals: list[dict[str, Any]]) -> str:
    """Build the nudge for tool-failure loops."""
    lines = []
    for sig in signals:
        if sig["signal"] == "failure-repeat":
            lines.append(f"- Same failure {sig['count']} times: {sig['fingerprint']}")
        else:
            lines.append(
                f"- {sig['target']} edited {sig['count']} times, same failure after each: "
                f"{sig['fingerprint']}"
            )
    return (
        "<stuck-detection>\n"
        "SELF-REFLECTION: Failure loop detected.\n" + "\n".join(lines) + "\n\n"
        "BREAK THE LOOP:\n"
        "1. Stop retrying the same command or edit\n"
        "2. Re-read the full error and state its cause in one sentence\n"
        "3. Try a different approach, or ask the user if the cause is unclear\n"
        "</stuck-detection>"
    )


def check_failures(
    events: list[dict[str, Any]],
    *,
    repeat_threshold: int = DEFAULT_FAILURE_REPEAT,
    churn_threshold: int = DEFAULT_EDIT_CHURN,
    window: int = DEFAULT_FAILURE_WINDOW,
) -> dict[str, Any]:
    """Report failure-loop signals over the last ``window`` events."""
    for name, value in (
        ("repeat_threshold", repeat_threshold),
        ("churn_threshold", churn_threshold),
        ("window", window),
    ):
        if value < 2:
            raise ValueError(f"{name} ({value}) must be >= 2")
    recent = events[-window:]
    signals = detect_failure_repeat(recent, repeat_threshold) + detect_edit_churn(
        recent, churn_threshold
    )
    result: dict[str, Any] = {
        "stuck": bool(signals),
        "events_checked": len(recent),
        "signals": signals,
    }
    if signals:
        result["nudge"] = build_failure_nudge(signals)
    return result


def _read_events(path: Path | None) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8") if path else sys.stdin.read()
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise EventError(f"input is not valid JSON: {exc.msg} at line {exc.lineno}") from exc
    return parse_events(raw)


def reset_history(history_path: Path) -> dict[str, bool]:
    """Truncate history (call after a confirmed topic change)."""
    save_history(history_path, [], DEFAULT_MAX_HISTORY)
    return {"reset": True}


def get_status(history_path: Path) -> dict[str, Any]:
    """Return current history depth and recent signatures."""
    history = load_history(history_path)
    return {
        "history_length": len(history),
        "max_history": DEFAULT_MAX_HISTORY,
        "stuck_threshold": DEFAULT_STUCK_THRESHOLD,
        "recent_signatures": [entry["signature"] for entry in history[-3:]],
    }


def _read_text(positional: list[str]) -> str:
    if positional:
        return " ".join(positional)
    return sys.stdin.read()


def _run_check_failures(args: argparse.Namespace) -> int:
    try:
        events = _read_events(args.events)
        result = check_failures(
            events,
            repeat_threshold=args.repeat,
            churn_threshold=args.churn,
            window=args.window,
        )
    except (EventError, ValueError, OSError, UnicodeDecodeError) as exc:
        print(f"stuck-detection: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="stuck-detection",
        description="Detect agent loops via topic signatures or repeated tool failures.",
    )
    parser.add_argument(
        "--history",
        type=Path,
        default=None,
        help="Override history file path (env: STUCK_DETECTION_HISTORY).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    check_parser = sub.add_parser("check", help="Check text for a stuck loop.")
    check_parser.add_argument("text", nargs="*", help="Text to check (or read from stdin).")

    failures_parser = sub.add_parser(
        "check-failures", help="Check a JSON array of tool events for a failure loop."
    )
    failures_parser.add_argument(
        "--events", type=Path, default=None, help="JSON file of tool events (default: stdin)."
    )
    failures_parser.add_argument("--repeat", type=int, default=DEFAULT_FAILURE_REPEAT)
    failures_parser.add_argument("--churn", type=int, default=DEFAULT_EDIT_CHURN)
    failures_parser.add_argument("--window", type=int, default=DEFAULT_FAILURE_WINDOW)

    sub.add_parser("reset", help="Clear history.")
    sub.add_parser("status", help="Show current state.")

    extract_parser = sub.add_parser("extract", help="Extract topic signature only.")
    extract_parser.add_argument("text", nargs="*", help="Text to analyze (or stdin).")

    args = parser.parse_args(argv)
    if args.command == "check-failures":
        return _run_check_failures(args)
    raw_path = args.history or default_history_path()
    history_path = Path(raw_path).expanduser().resolve()

    if args.command == "check":
        result = check_stuck(_read_text(args.text), history_path)
        print(json.dumps(result, indent=2))
    elif args.command == "reset":
        print(json.dumps(reset_history(history_path)))
    elif args.command == "status":
        print(json.dumps(get_status(history_path), indent=2))
    elif args.command == "extract":
        signature = extract_topic_signature(_read_text(args.text))
        print(signature if signature else "(no signature)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
