"""Shared helpers for the skillopt tests."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

Capture = pytest.CaptureFixture[str]


def write_json(path: Path, value: object) -> Path:
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def valid_eval(tmp_path: Path) -> Path:
    """A minimal eval file with a nonempty `sel` split, under tmp_path/evals."""
    folder = tmp_path / "evals"
    folder.mkdir(exist_ok=True)
    return write_json(folder / "eval.json", {"splits": {"sel": ["t1", "t2"]}})


def write_jsonl(path: Path, records: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")


def pattern(**overrides: object) -> dict:
    base: dict = {
        "id": "p1",
        "skill": "build",
        "sessions": ["s1"],
        "invocations": 1,
        "corrections": 0,
        "prompts": ["build it"],
    }
    base.update(overrides)
    return base


def write_handoff(path: Path, patterns: list | None = None, **top: object) -> None:
    if patterns is None:
        patterns = [
            pattern(sessions=["s1", "s2"], invocations=3, corrections=1,
                     prompts=["build the feature", "build the feature", "fix the build"]),
            pattern(id="p2", skill="review", sessions=["s3"], invocations=2,
                     prompts=["review this PR"]),
        ]  # fmt: skip
    doc: dict = {"schema": "session-patterns/1", "producer": "companion", "patterns": patterns}
    doc.update(top)
    path.write_text(json.dumps(doc), encoding="utf-8")


def skill_use(name: str) -> dict:
    return {"type": "assistant", "message": {"content": [
        {"type": "tool_use", "name": "Skill", "input": {"skill": name}}]}}  # fmt: skip


def user(text: str) -> dict:
    return {"type": "user", "message": {"content": text}}


def make_copilot_db(path: Path, turns: list[tuple]) -> None:
    con = sqlite3.connect(path)
    con.execute(
        "CREATE TABLE turns (session_id INT, turn_index INT, "
        "user_message TEXT, assistant_response TEXT)"
    )
    con.executemany("INSERT INTO turns VALUES (?,?,?,?)", turns)
    con.commit()
    con.close()
