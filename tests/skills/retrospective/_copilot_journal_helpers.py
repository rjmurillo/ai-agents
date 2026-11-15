"""Shared helpers for the native Copilot journal tests (issue #7357).

Every journal is synthetic. Sentinel strings stand in for prompts and results so
a leak into the output is detectable.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from hashlib import sha1
from pathlib import Path

_SCRIPT_DIR = (
    Path(__file__).resolve().parents[3] / "src" / "claude" / "skills" / "retrospective" / "scripts"
)


def _load(filename: str):
    path = _SCRIPT_DIR / filename
    name = f"retro_{path.stem}_{sha1(str(path).encode()).hexdigest()[:12]}"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


extract = _load("extract_evidence.py")
journal_mod = _load("copilot_journal.py")

PROMPT = "SENTINEL-PROMPT-do-not-leak"
REASONING = "SENTINEL-REASONING-do-not-leak"
RESULT = "SENTINEL-RESULT-do-not-leak"
ARG_VALUE = "SENTINEL-ARGUMENT-do-not-leak"


def ev(kind: str, data: dict, **extra) -> dict:
    return {"type": kind, "timestamp": "2026-11-09T12:00:00Z", "data": data, **extra}


def start(call: object, tool: object = "bash", arguments: object = None, **extra) -> dict:
    data = {"toolCallId": call, "toolName": tool}
    if arguments is not None:
        data["arguments"] = arguments
    return ev("tool.execution_start", data, **extra)


def complete(call: object, success: object = True, **fields) -> dict:
    return ev("tool.execution_complete", {"toolCallId": call, "success": success, **fields})


def session_start(cwd: Path | None) -> dict:
    context = {"cwd": str(cwd)} if cwd is not None else {}
    return ev("session.start", {"context": context})


def context_event(kind: str, cwd: object = None, git_root: object = None) -> dict:
    context = {}
    if cwd is not None:
        context["cwd"] = str(cwd)
    if git_root is not None:
        context["gitRoot"] = str(git_root)
    return ev(kind, {"context": context})


def write_journal(path: Path, rows: list) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [row if isinstance(row, str) else json.dumps(row) for row in rows]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def assert_unavailable(report: dict, fragment: str) -> None:
    assert report["available"] is False
    assert fragment in report["reason"]
    assert report["receipts"] == []
