"""Shared builders for the reflect Stop-hook tests (issue #5817)."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
HOOK = REPO_ROOT / ".claude" / "hooks" / "Stop" / "invoke_reflect_nudge.py"
SETTINGS = REPO_ROOT / ".claude" / "settings.json"


def human(text: str) -> dict:
    """A human-typed user record, the shape measured in real transcripts."""
    return {
        "type": "user",
        "origin": {"kind": "human"},
        "promptSource": "typed",
        "isSidechain": False,
        "message": {"role": "user", "content": text},
    }


def tool_result(text: str) -> dict:
    """A tool result the harness records as a user-role turn."""
    return {
        "type": "user",
        "toolUseResult": {"stdout": text},
        "sourceToolAssistantUUID": "abc",
        "message": {"role": "user", "content": [{"type": "tool_result", "content": text}]},
    }


def write_transcript(path: Path, records: list[dict], extra_lines: list[str] | None = None) -> Path:
    lines = [json.dumps(r) for r in records] + (extra_lines or [])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def registered_command() -> str:
    """The Stop command exactly as .claude/settings.json registers it."""
    entries = json.loads(SETTINGS.read_text(encoding="utf-8"))["hooks"]["Stop"]
    return entries[0]["hooks"][0]["command"]


def run_hook(
    payload: dict | str,
    state_home: Path,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Drive the real registered command through a shell, as the harness does."""
    env = {k: v for k, v in os.environ.items() if k != "REFLECT_NUDGE_DISABLE"}
    env.update({"CLAUDE_PROJECT_DIR": str(REPO_ROOT), "XDG_STATE_HOME": str(state_home)})
    env.update(extra_env or {})
    stdin = payload if isinstance(payload, str) else json.dumps(payload)
    return subprocess.run(
        ["bash", "-c", registered_command()],
        input=stdin,
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
        check=False,
    )
