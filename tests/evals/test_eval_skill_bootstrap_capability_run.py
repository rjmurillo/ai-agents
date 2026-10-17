"""Tests for the run side of scripts/eval/eval_skill_bootstrap_capability.py."""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

SCRIPT = (
    Path(__file__).resolve().parents[2] / "scripts" / "eval" / "eval_skill_bootstrap_capability.py"
)


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("eval_skill_bootstrap_capability_run", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cap = _load()

REPS = 2
TASKS: dict[str, Any] = {
    "preamble": "p",
    "tasks": [
        {"id": "A", "prompt": "pa", "grader": "set_f1", "answer_key": "top", "gold": ["a", "b"]},
        {"id": "B", "prompt": "pb", "grader": "set_f1", "answer_key": "top", "gold": ["c"]},
    ],
}


def _write_tasks(tmp_path: Path, data: Any) -> Path:
    path = tmp_path / "tasks.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _make_checkout(root: Path, name: str) -> Path:
    skill = root / name / ".claude" / "skills" / "skill-bootstrap"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("x", encoding="utf-8")
    return root / name


@pytest.fixture
def checkout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(cap.shutil, "which", lambda name: "/bin/claude")
    return _make_checkout(tmp_path, "co")


def _head(monkeypatch: pytest.MonkeyPatch, value: str | None) -> None:
    monkeypatch.setattr(cap, "_checkout_head", lambda path: value)


def _fake_answer(task: dict[str, Any]) -> str:
    return "```json\n" + json.dumps({task["answer_key"]: task["gold"]}) + "\n```"


def _run(args: list[str], tasks_file: Path, checkout: Path, out: Path, condition: str) -> int:
    return cap.main(
        [
            "run",
            "--checkout",
            str(checkout),
            "--condition",
            condition,
            "--tasks",
            str(tasks_file),
            "--reps",
            str(REPS),
            "--out",
            str(out),
            *args,
        ]
    )


def test_run_writes_jsonl_that_loads_and_scores(tmp_path, checkout, monkeypatch, capsys):
    tasks_file = _write_tasks(tmp_path, TASKS)
    by_prompt = {t["prompt"]: t for t in TASKS["tasks"]}

    def fake_run_one(path: Path, prompt: str, model: str) -> dict[str, Any]:
        task = by_prompt[prompt.rsplit("\n\n", 1)[1]]
        return {
            "result": _fake_answer(task),
            "is_error": False,
            "num_turns": 2,
            "cost_usd": 0.01,
            "output_tokens": 5,
            "wall_s": 1.0,
        }

    monkeypatch.setattr(cap, "run_one", fake_run_one)
    other = _make_checkout(tmp_path, "co-after")
    runs = {}
    for condition, root in (("before", checkout), ("after", other)):
        _head(monkeypatch, f"head-{condition}")
        out = tmp_path / f"{condition}.jsonl"
        assert _run([], tasks_file, root, out, condition) == 0
        runs[condition] = out

    task_ids = {t["id"] for t in TASKS["tasks"]}
    for out in runs.values():
        records = cap.load_records(str(out), task_ids)
        assert len(records) == REPS * len(task_ids)
    capsys.readouterr()
    code = cap.main(
        ["score", "--runs", str(runs["before"]), str(runs["after"]), "--tasks", str(tasks_file)]
    )
    assert code == 0


def test_run_records_error_kind_in_the_progress_line(tmp_path, checkout, monkeypatch, capsys):
    tasks_file = _write_tasks(tmp_path, TASKS)
    _head(monkeypatch, "h")
    monkeypatch.setattr(
        cap,
        "run_one",
        lambda *a: {
            "result": "",
            "is_error": True,
            "error_kind": "timeout",
            "num_turns": None,
            "cost_usd": None,
            "output_tokens": None,
            "wall_s": 1.0,
        },
    )

    code = _run(["--task", "A"], tasks_file, checkout, tmp_path / "o.jsonl", "before")

    line = capsys.readouterr().out.splitlines()[0]
    assert code == 0
    assert "err=timeout" in line
    assert "f1=" not in line


def test_claude_cli_missing_exits_3(tmp_path, monkeypatch):
    monkeypatch.setattr(cap.shutil, "which", lambda name: None)
    out = tmp_path / "o.jsonl"

    code = _run([], _write_tasks(tmp_path, TASKS), tmp_path, out, "before")

    assert code == 3
    assert not out.exists()


def test_checkout_without_skill_exits_2(tmp_path, monkeypatch):
    monkeypatch.setattr(cap.shutil, "which", lambda name: "/bin/claude")
    out = tmp_path / "o.jsonl"

    code = _run([], _write_tasks(tmp_path, TASKS), tmp_path, out, "before")

    assert code == 2
    assert not out.exists()


def test_head_failure_exits_3_before_opening_out(tmp_path, checkout, monkeypatch):
    _head(monkeypatch, None)
    out = tmp_path / "o.jsonl"

    code = _run([], _write_tasks(tmp_path, TASKS), checkout, out, "before")

    assert code == 3
    assert not out.exists()


@pytest.mark.parametrize(
    "outcome",
    [
        subprocess.CompletedProcess([], 128, "", "fatal"),
        subprocess.CompletedProcess([], 0, "  \n", ""),
        FileNotFoundError("git"),
        subprocess.TimeoutExpired("git", 30),
    ],
)
def test_checkout_head_returns_none_on_every_failure(tmp_path, monkeypatch, outcome):
    def fake(*args, **kwargs):
        assert kwargs["timeout"] == cap.GIT_TIMEOUT_S
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    monkeypatch.setattr(cap.subprocess, "run", fake)

    assert cap._checkout_head(tmp_path) is None


def test_checkout_head_returns_the_sha(tmp_path, monkeypatch):
    done = subprocess.CompletedProcess([], 0, "abc123\n", "")
    monkeypatch.setattr(cap.subprocess, "run", lambda *a, **k: done)

    assert cap._checkout_head(tmp_path) == "abc123"


def _tasks_without(key: str) -> dict[str, Any]:
    data = json.loads(json.dumps(TASKS))
    data.pop(key, None)
    return data


def _tasks_with_empty_gold() -> dict[str, Any]:
    data = json.loads(json.dumps(TASKS))
    data["tasks"][0]["gold"] = []
    return data


@pytest.mark.parametrize(
    "data",
    [
        _tasks_without("preamble"),
        {**TASKS, "preamble": "   "},
        {**TASKS, "preamble": 7},
        _tasks_with_empty_gold(),
        [1, 2],
        {**TASKS, "tasks": ["not an object"]},
    ],
)
def test_bad_tasks_file_exits_2_before_any_run(tmp_path, checkout, monkeypatch, data):
    _head(monkeypatch, "h")
    monkeypatch.setattr(cap, "run_one", lambda *a: pytest.fail("run_one must not be called"))
    out = tmp_path / "o.jsonl"

    code = _run([], _write_tasks(tmp_path, data), checkout, out, "before")

    assert code == 2
    assert not out.exists()


def test_non_object_tasks_file_is_a_config_error_for_score_too(tmp_path, capsys):
    runs = tmp_path / "r.jsonl"
    runs.write_text("", encoding="utf-8")

    code = cap.main(["score", "--runs", str(runs), "--tasks", str(_write_tasks(tmp_path, [1]))])

    assert code == 2


# --- run_one error observability ---------------------------------------------


def _patch_run(monkeypatch, outcome):
    def fake(*args, **kwargs):
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    monkeypatch.setattr(cap.subprocess, "run", fake)


def test_run_one_timeout_records_kind_and_stderr_tail(monkeypatch, tmp_path):
    exc = subprocess.TimeoutExpired("claude", 1, stderr=b"x" * 3000)
    _patch_run(monkeypatch, exc)

    record = cap.run_one(tmp_path, "p", "m")

    assert record["error_kind"] == "timeout"
    assert record["returncode"] is None
    assert record["stderr"] == "x" * cap.STDERR_TAIL_CHARS


def test_run_one_bad_json_records_kind_returncode_and_stderr(monkeypatch, tmp_path):
    _patch_run(monkeypatch, subprocess.CompletedProcess([], 1, "not json", "boom"))

    record = cap.run_one(tmp_path, "p", "m")

    assert (record["error_kind"], record["returncode"], record["stderr"]) == ("bad_json", 1, "boom")
    assert record["is_error"] is True


def test_run_one_cli_error_records_kind_and_stderr_tail(monkeypatch, tmp_path):
    payload = json.dumps({"is_error": True, "result": "auth failed"})
    _patch_run(monkeypatch, subprocess.CompletedProcess([], 1, payload, "y" * 3000))

    record = cap.run_one(tmp_path, "p", "m")

    assert record["error_kind"] == "cli_error"
    assert record["returncode"] == 1
    assert record["stderr"] == "y" * cap.STDERR_TAIL_CHARS


def test_run_one_success_has_no_error_fields(monkeypatch, tmp_path):
    payload = json.dumps({"result": "ok", "num_turns": 1})
    _patch_run(monkeypatch, subprocess.CompletedProcess([], 0, payload, ""))

    record = cap.run_one(tmp_path, "p", "m")

    assert record["is_error"] is False
    assert "error_kind" not in record
