#!/usr/bin/env python3
"""Detect conversation loops via Jaccard similarity on topic signatures.

Tracks recent response signatures in a JSON history file. When the most
recent N entries exceed a similarity threshold, emits a nudge payload so
the orchestrator can break the loop.

EXIT CODES (ADR-035):
    0 - Success (regardless of stuck/not-stuck)
    2 - Invalid command or arguments
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

DEFAULT_MAX_HISTORY = 10
DEFAULT_STUCK_THRESHOLD = 3
DEFAULT_SIMILARITY_THRESHOLD = 0.6
MIN_SIGNIFICANT_WORDS = 2
MIN_TEXT_LENGTH = 50
SIGNATURE_SIZE = 5
MIN_WORD_LENGTH = 4

STOP_WORDS: frozenset[str] = frozenset({
    "the", "and", "but", "for", "are", "was", "were", "been", "being",
    "have", "has", "had", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "need", "ought", "used",
    "into", "through", "during", "before", "after", "above", "below",
    "between", "out", "off", "over", "under", "again", "further", "then",
    "once", "here", "there", "when", "where", "why", "how", "all", "both",
    "each", "few", "more", "most", "other", "some", "such", "nor",
    "not", "only", "own", "same", "than", "too", "very", "just",
    "don", "now", "this", "that", "these", "those", "with", "from",
    "your", "yours", "their", "theirs", "ours", "what", "which", "who",
    "whom", "okay", "yes", "thanks", "thank", "please", "sorry", "hello",
    "hey", "sure", "right", "well", "also", "still", "already",
    "done", "going", "want", "like", "know", "think", "make", "take",
    "get", "see", "come", "look", "use", "find", "give", "tell", "work",
})


def default_history_path() -> Path:
    """Resolve the default history file path.

    Honors STUCK_DETECTION_HISTORY env var. Falls back to XDG state dir
    (`$XDG_STATE_HOME/claude-stuck-detection/history.json`), then
    `~/.local/state/claude-stuck-detection/history.json`.
    """
    override = os.environ.get("STUCK_DETECTION_HISTORY")
    if override:
        return Path(override).expanduser()

    xdg = os.environ.get("XDG_STATE_HOME")
    base = Path(xdg).expanduser() if xdg else Path.home() / ".local" / "state"
    return base / "claude-stuck-detection" / "history.json"


def extract_topic_signature(text: str) -> str | None:
    """Extract a sorted, comma-joined signature of the top significant words.

    Returns None for short or low-content text.
    """
    if not text or len(text) < MIN_TEXT_LENGTH:
        return None

    cleaned = re.sub(r"[^\w\s]", " ", text.lower())
    tokens = [
        w for w in cleaned.split()
        if len(w) > MIN_WORD_LENGTH - 1 and w not in STOP_WORDS
    ]
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
    """Compute Jaccard similarity between two comma-joined signatures."""
    set_a = set(sig_a.split(","))
    set_b = set(sig_b.split(","))
    union = set_a | set_b
    if not union:
        return 0.0
    return len(set_a & set_b) / len(union)


def load_history(path: Path) -> list[dict[str, str]]:
    """Read history; return empty list on missing or unreadable file."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return cast("list[dict[str, str]]", data)


def save_history(path: Path, history: list[dict[str, str]], max_history: int) -> None:
    """Persist the most recent `max_history` entries atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    trimmed = history[-max_history:]
    path.write_text(json.dumps(trimmed, indent=2), encoding="utf-8")


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
    signature = extract_topic_signature(text)
    if signature is None:
        return {"stuck": False, "signature": None, "reason": "no-signature"}

    history = load_history(history_path)
    timestamp = (now or datetime.now(UTC)).isoformat()
    history.append({"signature": signature, "timestamp": timestamp})
    save_history(history_path, history, max_history)

    if len(history) < stuck_threshold:
        return {"stuck": False, "signature": signature, "reason": "warming-up"}

    recent = history[-stuck_threshold:]
    similar = sum(
        1 for entry in recent
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


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="stuck-detection",
        description="Detect agent conversation loops via topic-signature similarity.",
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

    sub.add_parser("reset", help="Clear history.")
    sub.add_parser("status", help="Show current state.")

    extract_parser = sub.add_parser("extract", help="Extract topic signature only.")
    extract_parser.add_argument("text", nargs="*", help="Text to analyze (or stdin).")

    args = parser.parse_args(argv)
    history_path = args.history or default_history_path()

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
    else:
        parser.error(f"unknown command: {args.command}")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
