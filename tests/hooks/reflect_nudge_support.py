"""Shared fixtures-as-functions for the reflect nudge tests (issue #5817).

Record fixtures mirror the key shapes measured on real transcripts: a human
turn carries ``origin.kind == "human"`` and ``promptSource``; a tool result
carries ``toolUseResult`` and ``sourceToolAssistantUUID`` and is recorded with
``type == "user"``.
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
HOOK_PATH = REPO_ROOT / "templates" / "hooks" / "Stop" / "invoke_reflect_nudge.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("invoke_reflect_nudge", HOOK_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["invoke_reflect_nudge"] = module
    # Never write bytecode into templates/hooks: the template-tree corpus test
    # lists every file under that directory.
    previous, sys.dont_write_bytecode = sys.dont_write_bytecode, True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return module


nudge = _load()


def human(text: str, **extra: Any) -> dict[str, Any]:
    record: dict[str, Any] = {
        "type": "user",
        "isSidechain": False,
        "origin": {"kind": "human"},
        "promptSource": "typed",
        "message": {"role": "user", "content": text},
    }
    record.update(extra)
    return record


def tool_result(text: str) -> dict[str, Any]:
    return {
        "type": "user",
        "isSidechain": False,
        "sourceToolAssistantUUID": "u-1",
        "toolUseResult": {"stdout": text},
        "message": {"role": "user", "content": [{"type": "tool_result", "content": text}]},
    }


def scan(path: Path, **kwargs: Any) -> Any:
    """Open ``path`` the way the hook does and scan it."""
    handle = nudge.open_transcript(str(path))
    assert handle is not None
    with handle:
        return nudge.scan_transcript(handle, **kwargs)


def write_transcript(path: Path, records: list[Any], raw_lines: list[str] | None = None) -> Path:
    lines = [json.dumps(r) for r in records] + (raw_lines or [])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def payload(transcript: Path | None, session_id: str = "sess-1") -> str:
    body: dict[str, Any] = {"session_id": session_id, "cwd": "/work"}
    if transcript is not None:
        body["transcript_path"] = str(transcript)
    return json.dumps(body)


def run_hook(stdin_text: str, state_root: Path, **kwargs: Any) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    code = nudge.run(io.StringIO(stdin_text), out, err, {}, state_root=state_root, **kwargs)
    return code, out.getvalue(), err.getvalue()
