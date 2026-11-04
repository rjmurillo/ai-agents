"""Builders for the friction branch tests of the reflect nudge (REQ-048 TASK-003).

Records follow the Claude Code transcript shapes the classifier reads: an
assistant ``tool_use`` block, then a user ``tool_result`` block that pairs by
``tool_use_id``, and ``Stop hook feedback:`` user records.
"""

from __future__ import annotations

import io
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from tests.hooks.reflect_nudge_support import nudge, write_transcript

PLANT = "PLANTED-TEXT-7f3a9c"
DENIAL_TEXT = f"Tool use was denied by the user. {PLANT}"
THRESHOLD_ENV = "AI_AGENTS_RETRO_NUDGE_THRESHOLD"

__all__ = [
    "DENIAL_TEXT",
    "PLANT",
    "THRESHOLD_ENV",
    "call",
    "expected_score",
    "friction_records",
    "run_env",
    "stop_feedback",
    "write_transcript",
]


def call(tool_id: str, *, error: str | None, sidechain: bool = False) -> list[dict[str, Any]]:
    """One Bash tool_use and its tool_result. ``error`` None means success."""
    block = {"type": "tool_use", "id": tool_id, "name": "Bash", "input": {"command": f"c {PLANT}"}}
    result: dict[str, Any] = {
        "type": "tool_result",
        "tool_use_id": tool_id,
        "content": error if error is not None else "ok",
    }
    if error is not None:
        result["is_error"] = True
    return [
        {"type": "assistant", "isSidechain": sidechain, "message": {"content": [block]}},
        {"type": "user", "isSidechain": sidechain, "message": {"content": [result]}},
    ]


def stop_feedback(sidechain: bool = False) -> dict[str, Any]:
    return {
        "type": "user",
        "isSidechain": sidechain,
        "message": {"role": "user", "content": f"Stop hook feedback: keep going {PLANT}"},
    }


def friction_records(denials: int = 0, feedback: int = 0, prefix: str = "t") -> list[Any]:
    """Records whose friction v2 score is ``expected_score(denials, feedback)``.

    A success follows each denial, so the longest error streak is 1.
    """
    records: list[Any] = []
    for index in range(denials):
        records += call(f"{prefix}-d{index}", error=DENIAL_TEXT)
        records += call(f"{prefix}-ok{index}", error=None)
    records += [stop_feedback() for _ in range(feedback)]
    return records


def expected_score(denials: int, feedback: int) -> int:
    return 2 * denials + 2 * feedback + (1 if denials else 0)


def run_env(
    transcript: Path | None,
    state_root: Path | None,
    env: Mapping[str, str] | None = None,
    session_id: str = "sess-1",
    **kwargs: Any,
) -> tuple[int, str, str]:
    """Run the hook with an explicit env mapping (the shared run_hook passes none)."""
    body: dict[str, Any] = {"session_id": session_id}
    if transcript is not None:
        body["transcript_path"] = str(transcript)
    out, err = io.StringIO(), io.StringIO()
    code = nudge.run(
        io.StringIO(json.dumps(body)), out, err, env or {}, state_root=state_root, **kwargs
    )
    return code, out.getvalue(), err.getvalue()
