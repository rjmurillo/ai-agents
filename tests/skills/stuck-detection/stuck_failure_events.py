"""Shared loader and event builders for the check-failures tests."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
if TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, TESTS_SKILLS_DIR)

from claude_skills_import import import_skill_script

mod: Any = import_skill_script(".claude/skills/stuck-detection/failure_loops.py")
entry: Any = import_skill_script(".claude/skills/stuck-detection/stuck_detection.py")
# The shared FailureClassifier, as failure_loops.py imported it from the plugin lib.
fc: Any = sys.modules["failure_classifier"]

TEST_CMD = "pytest tests/test_app.py"


def fail(tool: str, error: str, command: str | None = None) -> dict[str, Any]:
    event: dict[str, Any] = {"tool": tool, "ok": False, "error": error}
    if command is not None:
        event["input"] = command
    return event


def ok(tool: str, target: str | None = None, command: str | None = None) -> dict[str, Any]:
    event: dict[str, Any] = {"tool": tool, "ok": True}
    if target is not None:
        event["target"] = target
    if command is not None:
        event["input"] = command
    return event


def run(events: list[dict[str, Any]], **kwargs: int) -> dict[str, Any]:
    result: dict[str, Any] = mod.check_failures(mod.parse_events(events), **kwargs)
    return result


def kinds(result: dict[str, Any]) -> list[str]:
    return [s["signal"] for s in result["signals"]]
