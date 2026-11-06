"""Shared fixtures for the friction calibration tests: synthetic transcript records."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

TS = "2026-10-15T12:00:00Z"
SINCE, UNTIL = date(2026, 10, 3), date(2026, 11, 2)
FAKE_TOKEN = "ghp_" + "A1b2C3d4E5" * 3 + "F6g7H8"  # ghp_ plus 36 chars


def human(text: str, ts: str | None = TS) -> dict[str, Any]:
    record: dict[str, Any] = {
        "type": "user",
        "origin": {"kind": "human"},
        "message": {"role": "user", "content": text},
    }
    if ts:
        record["timestamp"] = ts
    return record


def use(use_id: str, name: str, tool_input: object, sidechain: bool = False) -> dict[str, Any]:
    block = {"type": "tool_use", "id": use_id, "name": name, "input": tool_input}
    return {
        "type": "assistant",
        "isSidechain": sidechain,
        "message": {"role": "assistant", "content": [block]},
    }


def result(use_id: str, text: str, error: bool = False, sidechain: bool = False) -> dict[str, Any]:
    block: dict[str, Any] = {"type": "tool_result", "tool_use_id": use_id, "content": text}
    if error:
        block["is_error"] = True
    return {
        "type": "user",
        "isSidechain": sidechain,
        "toolUseResult": {},
        "message": {"role": "user", "content": [block]},
    }


def call(
    n: int, name: str = "Bash", cmd: str = "make build", err: str | None = None
) -> list[dict[str, Any]]:
    """A tool_use/tool_result pair; ``err`` makes the result an error."""
    return [
        use(f"u{n}", name, {"command": cmd}),
        result(f"u{n}", err or "done", error=err is not None),
    ]


def write(path: Path, records: list[Any], raw: list[str] | None = None) -> Path:
    lines = [json.dumps(r) for r in records] + (raw or [])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def three_turn_session() -> list[dict[str, Any]]:
    return [
        human("first prompt"),
        *call(1, err="boom one"),
        human("second"),
        *call(2, err="boom two"),
        human("third"),
        *call(3, err="boom three"),
    ]
