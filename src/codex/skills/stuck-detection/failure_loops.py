#!/usr/bin/env python3
"""Detect tool-failure loops in a list of recent tool events.

Stateless. The caller passes the recent tool events; nothing is stored, no
model is called, and no hook runs this. It reports two signals:

- ``failure-repeat``: one failure fingerprint seen again and again.
- ``edit-churn``: one file edited across several cycles while the same
  failure keeps coming back.

The signal definitions are adapted from the failure-loop guard in
microsoft/TokenEconomizer (https://github.com/microsoft/TokenEconomizer,
Apache-2.0). No code was copied. Unlike that guard, this one calls no judge
model and never stops a turn; it only reports.

Run it as ``stuck_detection.py check-failures`` (the skill's entry point) or
directly as ``failure_loops.py``.

EXIT CODES (ADR-035):
    0 - Success (regardless of stuck/not-stuck)
    2 - Invalid arguments or event input

Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import posixpath
import re
import sys
from pathlib import Path
from typing import Any

DEFAULT_REPEAT = 3
DEFAULT_CHURN = 3
DEFAULT_WINDOW = 20
MAX_EVENTS = 10_000
MAX_INPUT_BYTES = 8 * 1024 * 1024
FINGERPRINT_MAX_CHARS = 200
TOOL_MAX_CHARS = 40
TARGET_MAX_CHARS = 512
MAX_NUDGE_SIGNALS = 5
EDIT_TOOLS: frozenset[str] = frozenset(
    {"edit", "write", "multiedit", "str_replace", "create", "apply_patch", "notebookedit"}
)
# A hash or address: 0x plus 7 or more hex characters, or a bare run of 7 or
# more holding at least one digit and one letter, so plain numbers fall to the
# digit rule and words like "defaced" stay words.
_HEX_RUN = re.compile(r"\b0x[0-9a-f]{7,}\b|\b(?=[0-9a-f]*\d)(?=[0-9a-f]*[a-f])[0-9a-f]{7,}\b")
_DIGIT_RUN = re.compile(r"\d+")
_WHITESPACE_RUN = re.compile(r"\s+")
_UNSAFE_TOOL_CHARS = re.compile(r"[^a-z0-9_.-]")


class EventError(ValueError):
    """Raised when the tool-event input does not match the documented shape."""


def normalize_tool(tool: str) -> str:
    """Lowercase and strip a tool name. The one place tool names are compared."""
    return tool.strip().lower()


def failure_fingerprint(tool: str, error: str) -> str | None:
    """Reduce a failure to ``<tool>|<first error line>``, or None with no error text.

    Hex runs (hashes, addresses) become ``H`` and digit runs (line numbers,
    PIDs) become ``N``, so the same failure on another line or run still
    matches. The line is lowercased, whitespace-collapsed, and capped at
    ``FINGERPRINT_MAX_CHARS``. A failure with no error text has no
    fingerprint: it carries nothing that could tell two failures apart.
    """
    first = next((line for line in error.splitlines() if line.strip()), "")
    line = first.strip().lower()
    if not line:
        return None
    line = _HEX_RUN.sub("H", line)
    line = _DIGIT_RUN.sub("N", line)
    line = _WHITESPACE_RUN.sub(" ", line)[:FINGERPRINT_MAX_CHARS]
    return f"{normalize_tool(tool)}|{line}"


def _normalize_target(target: str) -> str:
    """Collapse ``./a.py``, ``a//b.py`` and Windows separators to one spelling."""
    return posixpath.normpath(target.replace("\\", "/"))[:TARGET_MAX_CHARS]


def _optional_string(item: dict[str, Any], key: str, index: int) -> str | None:
    value = item.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise EventError(f"event {index}: '{key}' must be a string")
    stripped = value.strip()
    return stripped if stripped else None


def parse_events(raw: Any) -> list[dict[str, Any]]:
    """Validate decoded JSON and return normalized events.

    Accepts a list of objects. Each needs ``tool`` (non-empty string) and
    ``ok`` (boolean). ``error``, ``input`` and ``target`` are optional
    strings on every event and are type-checked whenever present; ``error``
    is used only for failures. Unknown keys are ignored. Anything else
    raises ``EventError`` naming the bad index.
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
        error = _optional_string(item, "error", index) or ""
        command = _optional_string(item, "input", index)
        target = _optional_string(item, "target", index)
        key = normalize_tool(tool)
        events.append(
            {
                "tool": key,
                "ok": ok,
                "fingerprint": None if ok else failure_fingerprint(key, error),
                "input": command,
                "target": _normalize_target(target) if target else None,
                "edit_tool": key in EDIT_TOOLS,
                "is_edit": key in EDIT_TOOLS and target is not None,
            }
        )
    return events


def _progress_key(event: dict[str, Any]) -> tuple[str, str] | None:
    """The (tool, input) pair a later success must match to count as progress."""
    if event["input"] is None:
        return None
    return (event["tool"], event["input"])


Tally = dict[tuple[tuple[str, str] | None, str], int]


def _scan(events: list[dict[str, Any]]) -> tuple[Tally, dict[str, Tally]]:
    """Walk events once; return failure tallies and per-file churn tallies.

    Every count is keyed by ``(progress key, fingerprint)``, where the
    progress key is the event's ``(tool, input)`` pair, or None without
    ``input``. Progress is a success whose pair matches an earlier failure in
    the window: the check that failed now passes. It removes only the counts
    recorded under that pair, so fixing one command never hides a loop in
    another that shares its first error line, and it closes the pending edit
    cycle. Without ``input`` nothing can match, so nothing resets.

    Every fingerprinted failure is tallied, failed edits included. The first
    fingerprinted failure of a non-edit tool after successful edits is the
    outcome of each file edited since the previous outcome; several edits of
    one file before one failure count once (one cycle). A failed edit-tool
    event, with or without ``target``, closes no cycle.
    """
    tally: Tally = {}
    churn: dict[str, Tally] = {}
    pending: set[str] = set()
    for event in events:
        key = _progress_key(event)
        if event["ok"]:
            # Progress first, for every tool: a retried Write that now succeeds
            # clears its own failures, then starts a new edit cycle.
            if key is not None and any(k == key for k, _ in tally):
                tally = {kf: n for kf, n in tally.items() if kf[0] != key}
                for target, per_file in churn.items():
                    churn[target] = {kf: n for kf, n in per_file.items() if kf[0] != key}
                pending.clear()
            if event["is_edit"]:
                pending.add(event["target"])
            continue
        fingerprint = event["fingerprint"]
        if fingerprint is None:
            continue
        tally[(key, fingerprint)] = tally.get((key, fingerprint), 0) + 1
        if event["edit_tool"]:
            continue
        for target in pending:
            per_file = churn.setdefault(target, {})
            per_file[(key, fingerprint)] = per_file.get((key, fingerprint), 0) + 1
        pending.clear()
    return tally, churn


def _by_fingerprint(tally: Tally) -> dict[str, int]:
    """Sum a tally over progress keys: one count per fingerprint."""
    totals: dict[str, int] = {}
    for (_, fingerprint), n in tally.items():
        totals[fingerprint] = totals.get(fingerprint, 0) + n
    return totals


def detect_signals(
    events: list[dict[str, Any]], repeat_threshold: int, churn_threshold: int
) -> list[dict[str, Any]]:
    """Both signals over ``events``: failure-repeat first (most frequent first), then churn."""
    tally, churn = _scan(events)
    repeats = sorted(
        ((fp, n) for fp, n in _by_fingerprint(tally).items() if n >= repeat_threshold),
        key=lambda kv: (-kv[1], kv[0]),
    )
    signals: list[dict[str, Any]] = [
        {"signal": "failure-repeat", "fingerprint": fp, "count": n} for fp, n in repeats
    ]
    for target in sorted(churn):
        totals = _by_fingerprint(churn[target])
        if not totals:
            continue
        fp, n = max(totals.items(), key=lambda kv: (kv[1], kv[0]))
        if n >= churn_threshold:
            signals.append(
                {"signal": "edit-churn", "target": target, "fingerprint": fp, "count": n}
            )
    return signals


def _safe_tool(fingerprint: str) -> str:
    return _UNSAFE_TOOL_CHARS.sub("", fingerprint.split("|", 1)[0])[:TOOL_MAX_CHARS] or "tool"


def build_failure_nudge(signals: list[dict[str, Any]]) -> str:
    """Build the nudge from signal names, counts and sanitized tool names only.

    The nudge is control text a caller may inject into a prompt, so it never
    carries event text: error lines and file paths can come from an attacker
    (a crafted test message, a file name). They stay in the JSON ``signals``.
    """
    lines = []
    # Churn names a file-level loop, the most actionable signal: list it first
    # so a pile of failure-repeat signals cannot push it past the cap.
    ordered = sorted(signals, key=lambda sig: sig["signal"] != "edit-churn")
    for sig in ordered[:MAX_NUDGE_SIGNALS]:
        tool = _safe_tool(sig["fingerprint"])
        if sig["signal"] == "failure-repeat":
            lines.append(f"- failure-repeat: the same {tool} failure {sig['count']} times")
        elif sig["signal"] == "edit-churn":
            lines.append(
                f"- edit-churn: one file edited across {sig['count']} cycles, "
                f"same {tool} failure after each"
            )
        else:
            lines.append(f"- {sig['signal']}: {sig['count']} times")
    extra = len(signals) - MAX_NUDGE_SIGNALS
    if extra > 0:
        lines.append(f"- and {extra} more")
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
    repeat_threshold: int = DEFAULT_REPEAT,
    churn_threshold: int = DEFAULT_CHURN,
    window: int = DEFAULT_WINDOW,
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
    signals = detect_signals(recent, repeat_threshold, churn_threshold)
    result: dict[str, Any] = {
        "stuck": bool(signals),
        "events_total": len(events),
        "events_checked": len(recent),
        "signals": signals,
    }
    if signals:
        result["nudge"] = build_failure_nudge(signals)
    return result


def _read_input(path: Path | None) -> str:
    """Read at most ``MAX_INPUT_BYTES`` from the file or stdin, tolerating a BOM."""
    if path is not None:
        # A bounded read, not stat(): a FIFO or /dev/zero reports size 0.
        with path.open("rb") as handle:
            data = handle.read(MAX_INPUT_BYTES + 1)
        if len(data) > MAX_INPUT_BYTES:
            raise EventError(f"{path} is over the {MAX_INPUT_BYTES}-byte input limit")
    else:
        if sys.stdin is None:
            raise EventError("no --events file and stdin is closed")
        if sys.stdin.isatty():
            raise EventError("no --events file and stdin is a terminal; pipe the events in")
        buffer = getattr(sys.stdin, "buffer", None)
        if buffer is not None:
            data = buffer.read(MAX_INPUT_BYTES + 1)
        else:
            data = sys.stdin.read(MAX_INPUT_BYTES + 1).encode("utf-8")
        if len(data) > MAX_INPUT_BYTES:
            raise EventError(f"stdin is over the {MAX_INPUT_BYTES}-byte input limit")
    return data.decode("utf-8-sig")


def read_events(path: Path | None) -> list[dict[str, Any]]:
    """Read, decode and validate the event input."""
    text = _read_input(path)
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise EventError(f"input is not valid JSON: {exc.msg} at line {exc.lineno}") from exc
    except RecursionError as exc:
        raise EventError("input JSON is nested too deeply to decode") from exc
    return parse_events(raw)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for ``check-failures``."""
    parser = argparse.ArgumentParser(
        prog="stuck-detection check-failures",
        description="Check a JSON array of tool events for a failure loop.",
    )
    parser.add_argument(
        "--events", type=Path, default=None, help="JSON file of tool events (default: stdin)."
    )
    parser.add_argument("--repeat", type=int, default=DEFAULT_REPEAT)
    parser.add_argument("--churn", type=int, default=DEFAULT_CHURN)
    parser.add_argument("--window", type=int, default=DEFAULT_WINDOW)
    args = parser.parse_args(argv)
    try:
        result = check_failures(
            read_events(args.events),
            repeat_threshold=args.repeat,
            churn_threshold=args.churn,
            window=args.window,
        )
    except (ValueError, OSError) as exc:
        # EventError and UnicodeDecodeError are both ValueError subclasses.
        print(f"stuck-detection: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
