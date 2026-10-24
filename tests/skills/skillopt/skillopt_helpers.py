"""Shared helpers for the skillopt tests."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

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


# --- skillopt.py run helpers ---
PY = Path(sys.executable).name


def py(code: str, *args: str) -> list[str]:
    return [PY, "-c", code, *args]


def task(command: object, **fields: Any) -> dict[str, Any]:
    spec: dict[str, Any] = {"command": command, "timeout": 30}
    if not ({"expect_exit", "expect_stdout"} & set(fields)):
        spec["expect_exit"] = 0
    spec.update(fields)
    return spec


def make_eval(tmp_path: Path, tasks: dict[str, Any], **splits: list[str]) -> Path:
    if not splits:
        splits = {"sel": list(tasks)}
    return write_json(tmp_path / "eval.json", {"splits": splits, "tasks": tasks})


def bundle_of(tmp_path: Path, name: str = "bundle") -> Path:
    bundle = tmp_path / name
    bundle.mkdir()
    (bundle / "SKILL.md").write_text("skill\n", encoding="utf-8")
    return bundle


def run_argv(
    eval_path: Path, bundle: Path, out_dir: Path, role: str = "incumbent", *extra: str
) -> list[str]:
    return [
        "run",
        "--eval",
        str(eval_path),
        "--bundle",
        str(bundle),
        "--role",
        role,
        "--out-dir",
        str(out_dir),
        *extra,
    ]


def results_of(out_dir: Path, role: str = "incumbent") -> dict[str, Any]:
    return json.loads((out_dir / f"{role}_results.json").read_text(encoding="utf-8"))
