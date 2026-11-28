"""Synthetic transcript builders and CLI drivers for the reply-friction tests.

Every transcript here is invented. No real session data is read or copied.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

SCRIPTS = (
    Path(__file__).resolve().parents[3]
    / "src"
    / "claude"
    / "skills"
    / "skill-bootstrap"
    / "scripts"
)
sys.path.insert(0, str(SCRIPTS))
try:
    import replies_audit
    import replies_corpus
    import replies_flags
    import replies_prepare
    import replies_sample
    import replies_tally
finally:
    sys.path.remove(str(SCRIPTS))

__all__ = [
    "replies_audit",
    "replies_corpus",
    "replies_flags",
    "replies_prepare",
    "replies_sample",
    "replies_tally",
]

T0 = datetime(2026, 11, 1, tzinfo=timezone.utc)
CONTROL_TOKEN = "CONTROL-TOKEN-7731"
CONTROL_REPLY = f"{CONTROL_TOKEN} Applied the patch. Want me to also update the docs? Let me know."
BEFORE = "2026-12-01T00:00:00Z"
LONG_PROMPT = "Please build the synthetic widget exporter with tests and docs for the fixture suite"


def ts(minutes: float) -> str:
    return (T0 + timedelta(minutes=minutes)).isoformat()


def user(text: str, at: float, **extra: Any) -> dict[str, Any]:
    return {"type": "user", "timestamp": ts(at), "message": {"content": text}, **extra}


def assistant_text(text: str, at: float, **extra: Any) -> dict[str, Any]:
    block = {"type": "text", "text": text}
    return {"type": "assistant", "timestamp": ts(at), "message": {"content": [block]}, **extra}


def assistant_tool(at: float, narration: str | None = None) -> dict[str, Any]:
    blocks: list[dict[str, Any]] = []
    if narration:
        blocks.append({"type": "text", "text": narration})
    blocks.append({"type": "tool_use", "id": "t1", "name": "Bash", "input": {}})
    return {"type": "assistant", "timestamp": ts(at), "message": {"content": blocks}}


def tool_result(at: float, is_error: bool = False) -> dict[str, Any]:
    block = {"type": "tool_result", "tool_use_id": "t1", "content": "ok", "is_error": is_error}
    return {"type": "user", "timestamp": ts(at), "message": {"content": [block]}}


def api_error(at: float) -> dict[str, Any]:
    rec = assistant_text("synthetic api failure text", at)
    rec["isApiErrorMessage"] = True
    return rec


def write_session(store: Path, sid: str, records: list[dict[str, Any]]) -> Path:
    store.mkdir(parents=True, exist_ok=True)
    path = store / f"{sid}.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
    return path


def write_child(
    store: Path, parent: str, name: str, records: list[dict[str, Any]], meta: str | None = None
) -> Path:
    folder = store / parent / "subagents"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{name}.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
    if meta is not None:
        (folder / f"{name}.meta.json").write_text(json.dumps({"agentType": meta}), encoding="utf-8")
    return path


def simple_session(prompt: str, replies: list[str], start: float) -> list[dict[str, Any]]:
    """A prompt, then a tool boundary and final reply per entry, with typed follow-ups between."""
    recs = [user(prompt, start)]
    at = start
    for index, reply in enumerate(replies):
        recs += [assistant_tool(at + 1), tool_result(at + 2), assistant_text(reply, at + 3)]
        if index < len(replies) - 1:
            recs.append(user(f"synthetic follow-up number {index} please go on", at + 4))
        at += 5
    return recs


def plant_control(store: Path, start: float = 100.0, sid: str = "ctl-session") -> None:
    """Synthetic positive control: one reply that every run must flag as an offer tail."""
    write_session(
        store,
        sid,
        simple_session("synthetic control prompt, unique wording alpha", [CONTROL_REPLY], start),
    )


def prepare_args(store: Path | list[Path], run_dir: Path, *extra: str) -> list[str]:
    stores = store if isinstance(store, list) else [store]
    argv = ["prepare", "--before", BEFORE, "--run-dir", str(run_dir), "--sample-per-kind", "200"]
    argv += ["--marker", CONTROL_TOKEN]
    for item in stores:
        argv += ["--store", str(item)]
    return argv + list(extra)


def run_cli(capsys: pytest.CaptureFixture[str], argv: list[str]) -> tuple[int, dict[str, Any], str]:
    code = replies_audit.main(argv)
    out = capsys.readouterr().out
    return code, json.loads(out), out


def evidence_rows(run_dir: Path) -> list[dict[str, Any]]:
    text = (run_dir / replies_sample.EVIDENCE_NAME).read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def assert_control(payload: dict[str, Any], run_dir: Path, evidence: bool = True) -> None:
    """Fail the test when the planted control was missed, so a green run cannot be vacuous.

    With `evidence=False` (small samples may skip the control row) only the marker hit is required.
    """
    assert payload["replies"]["marker_hits"] == 1
    if not evidence:
        return
    rows = [r for r in evidence_rows(run_dir) if CONTROL_TOKEN in r["reply"]]
    assert len(rows) == 1
    assert "offer_tail" in rows[0]["flags"]


def prepare_ok(
    capsys: pytest.CaptureFixture[str],
    store: Path | list[Path],
    run_dir: Path,
    *extra: str,
    evidence: bool = True,
) -> tuple[dict[str, Any], str]:
    """Run prepare, require exit 0 and the positive control, return (payload, raw stdout)."""
    code, payload, out = run_cli(capsys, prepare_args(store, run_dir, *extra))
    assert code == 0, payload
    assert_control(payload, run_dir, evidence)
    return payload, out
