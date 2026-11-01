#!/usr/bin/env python3
"""Check caller-supplied tool events for a failure loop (consumer A of REQ-048).

REQ-048: https://github.com/rjmurillo/ai-agents/blob/main/.project-toolkit/specs/requirements/REQ-048-friction-triggered-retrospective-nudge.md

Stateless. The caller passes the recent tool events; nothing is stored, no
model is called, and no hook runs this. Every signal definition lives in the
shared FailureClassifier (`lib/failure_classifier`, canonical source
`scripts/failure_classifier/` in the rjmurillo/ai-agents repository). A
planned Stop retrospective nudge (consumer B, not shipped yet) will use the
same classifier; a parity test keeps the two adapters in step. This module only validates input, applies `--window`, `--repeat`,
and `--churn`, and builds the nudge. It reports two signals:

- ``failure-repeat`` (AC-33): one failure fingerprint seen again and again.
- ``edit-churn`` (AC-32): one file edited across several cycles while the
  same failure keeps coming back.

Run it as ``stuck_detection.py check-failures`` (the skill's entry point) or
directly as ``failure_loops.py``.

EXIT CODES (ADR-035):
    0 - Success (regardless of stuck/not-stuck)
    2 - Invalid arguments or event input (AC-35)

Stdlib only, plus this plugin's own ``lib/``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

# ADR-047 keeps this bootstrap inline because imports need sys.path first.
# The skill directory sits at <plugin root>/skills/stuck-detection/.
_PLUGIN_ROOT = os.environ.get("COPILOT_PLUGIN_ROOT") or os.environ.get("CLAUDE_PLUGIN_ROOT")
_LIB_DIR = (
    Path(_PLUGIN_ROOT) / "lib" if _PLUGIN_ROOT else Path(__file__).resolve().parents[2] / "lib"
)
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

from failure_classifier import (  # noqa: E402
    EDIT_TOOLS,
    FailureEvent,
    FailureSignals,
    canonicalize_input_text,
    classify,
    fingerprint_tool,
)

# Provisional: these defaults ship before calibration (REQ-048 decision D12).
# If under half of the nudges they produce are real loops, on at least 20
# labeled nudges, they are raised, and dropped if raising does not help.
DEFAULT_REPEAT = 3
DEFAULT_CHURN = 3
DEFAULT_WINDOW = 20
MAX_EVENTS = 10_000
MAX_INPUT_BYTES = 8 * 1024 * 1024
MAX_NUDGE_SIGNALS = 5
# AC-34: tool names the nudge may print verbatim; any other name prints as "tool".
NUDGE_TOOL_NAMES: frozenset[str] = EDIT_TOOLS | frozenset(
    {"bash", "shell", "powershell", "read", "view", "grep", "glob", "webfetch", "task"}
)
# AC-35: the output fields that echo tool output and file names.
UNTRUSTED_FIELDS: tuple[str, ...] = ("signals[].fingerprint", "signals[].target")


class EventError(ValueError):
    """Raised when the tool-event input does not match the documented shape."""


def _optional_string(item: dict[str, Any], key: str, index: int) -> str | None:
    value = item.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise EventError(f"event {index}: '{key}' must be a string")
    return value


def _canonical_input(item: dict[str, Any], index: int) -> str | None:
    """AC-39: a JSON ``input`` gets AC-38's canonical form; other text stays as given."""
    value = _optional_string(item, "input", index)
    return None if value is None else canonicalize_input_text(value)


def parse_events(raw: Any) -> list[FailureEvent]:
    """Validate decoded JSON and return FailureEvents.

    Accepts a list of objects. Each needs ``tool`` (non-empty string) and
    ``ok`` (boolean). ``error``, ``input`` and ``target`` are optional
    strings on every event and are type-checked whenever present. Unknown
    keys are ignored. Anything else raises ``EventError`` naming the bad
    index. An ``input`` that is a JSON document is canonicalized (AC-39).
    Other normalization (trimming, target paths) is the classifier's.
    """
    if not isinstance(raw, list):
        raise EventError("input must be a JSON array of tool events")
    if len(raw) > MAX_EVENTS:
        raise EventError(f"input holds {len(raw)} events; the limit is {MAX_EVENTS}")
    events: list[FailureEvent] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise EventError(f"event {index} is not an object")
        tool = item.get("tool")
        ok = item.get("ok")
        if not isinstance(tool, str) or not tool.strip():
            raise EventError(f"event {index}: 'tool' must be a non-empty string")
        if not isinstance(ok, bool):
            raise EventError(f"event {index}: 'ok' must be true or false")
        events.append(
            FailureEvent.build(
                tool=tool,
                ok=ok,
                error=_optional_string(item, "error", index),
                input=_canonical_input(item, index),
                target=_optional_string(item, "target", index),
            )
        )
    return events


def detect_signals(
    classified: FailureSignals, repeat_threshold: int, churn_threshold: int
) -> list[dict[str, Any]]:
    """Both signals: failure-repeat first (most frequent first), then churn."""
    repeats = sorted(
        ((fp, n) for fp, n in classified.repeat_totals().items() if n >= repeat_threshold),
        key=lambda kv: (-kv[1], kv[0]),
    )
    signals: list[dict[str, Any]] = [
        {"signal": "failure-repeat", "fingerprint": fp, "count": n} for fp, n in repeats
    ]
    for target, (fp, n) in classified.churned_targets(churn_threshold).items():
        signals.append({"signal": "edit-churn", "target": target, "fingerprint": fp, "count": n})
    return signals


def _safe_tool(fingerprint: str) -> str:
    """The fingerprint's tool name if it is a known tool, else the word "tool".

    Tool names can come from third-party MCP servers, so only names on the
    allowlist reach the nudge; anything else could spell an instruction.
    """
    tool = fingerprint_tool(fingerprint)
    return tool if tool in NUDGE_TOOL_NAMES else "tool"


def build_failure_nudge(signals: list[dict[str, Any]]) -> str:
    """Build the nudge from signal names, counts and sanitized tool names only.

    The nudge is control text a caller may inject into a prompt, so it carries
    no error lines, inputs, or file paths: those can come from an attacker (a
    crafted test message, a file name) and stay in the JSON ``signals``. Tool
    names appear only when allowlisted.
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
        "4. If a permission or user denial caused the failure, do not work around it: "
        "ask the user\n"
        "</stuck-detection>"
    )


def check_failures(
    events: list[FailureEvent],
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
    classified = classify(recent)
    signals = detect_signals(classified, repeat_threshold, churn_threshold)
    result: dict[str, Any] = {
        "stuck": bool(signals),
        "events_total": len(events),
        "events_checked": len(recent),
        "counts": {
            "tool_error": classified.tool_error,
            "permission_denial": classified.permission_denial,
            "failed_retry": classified.failed_retry,
            "unfingerprinted": classified.unfingerprinted,
        },
        "signals": signals,
        "untrusted": list(UNTRUSTED_FIELDS),
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


def read_events(path: Path | None) -> list[FailureEvent]:
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
