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


class FakeChild:
    """Stand-in for Popen: communicate() returns the outcome or raises it once."""

    pid = 4242
    killed = False

    def __init__(self, outcome):
        self.outcome = outcome
        self.returncode = getattr(outcome, "returncode", None)
        self.calls = 0

    def communicate(self, timeout=None):
        self.calls += 1
        if isinstance(self.outcome, BaseException) and self.calls == 1:
            raise self.outcome
        if isinstance(self.outcome, BaseException):
            return "", ""
        return self.outcome.stdout, self.outcome.stderr

    def kill(self):
        self.killed = True


def _patch_run(monkeypatch, outcome):
    child = FakeChild(outcome)
    seen: dict[str, Any] = {}

    def fake_popen(*args, **kwargs):
        seen.update(kwargs)
        return child

    monkeypatch.setattr(cap.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(cap.os, "killpg", lambda pid, sig: seen.setdefault("killpg", (pid, sig)))
    return child, seen


def test_run_one_timeout_records_kind_and_stderr_tail(monkeypatch, tmp_path):
    exc = subprocess.TimeoutExpired("claude", 1, stderr=b"x" * 3000)
    child, seen = _patch_run(monkeypatch, exc)

    record = cap.run_one(tmp_path, "p", "m")

    assert seen["start_new_session"] is True
    assert seen["killpg"][0] == child.pid
    assert child.killed is True
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


def test_run_one_timeout_survives_killpg_oserror(monkeypatch, tmp_path):
    child, _ = _patch_run(monkeypatch, subprocess.TimeoutExpired("claude", 1))

    def gone(pid, sig):
        raise ProcessLookupError

    monkeypatch.setattr(cap.os, "killpg", gone)

    record = cap.run_one(tmp_path, "p", "m")

    assert record["error_kind"] == "timeout"
    assert child.killed is True


# --- extraction, deny rules, empty tasks, score paths -------------------------


def test_extract_answer_unterminated_draft_does_not_hide_final_block():
    text = '```json\n{"top": ["draft"\n```json\n{"top": ["final"]}\n```'

    assert cap.extract_answer(text) == {"top": ["final"]}


def test_extract_answer_returns_none_without_a_usable_block():
    assert cap.extract_answer("no fences") is None
    assert cap.extract_answer("```json\n[1]\n```") is None
    assert cap.extract_answer("```json\n{not json\n```") is None


def test_eval_in_repo_flag_is_denied(monkeypatch, tmp_path):
    seen: list[list[str]] = []
    child = FakeChild(subprocess.CompletedProcess([], 0, "{}", ""))

    def fake_popen(command, **kwargs):
        seen.append(command)
        return child

    monkeypatch.setattr(cap.subprocess, "Popen", fake_popen)

    cap.run_one(tmp_path, "p", "m")

    denied = seen[0][seen[0].index("--disallowedTools") + 1 :]
    assert cap.DENY_EVAL_IN_REPO in denied
    assert "*--allow-in-repo*" in cap.DENY_EVAL_IN_REPO
    assert "bootstrap_eval.py" in cap.DENY_EVAL_IN_REPO


def test_empty_tasks_list_exits_2(tmp_path, checkout, monkeypatch):
    _head(monkeypatch, "h")
    data = {**TASKS, "tasks": []}

    code = _run([], _write_tasks(tmp_path, data), checkout, tmp_path / "o.jsonl", "before")

    assert code == 2


def _record(task: str, condition: str, head: str, *, error: bool = False) -> dict[str, Any]:
    return {
        "task": task,
        "condition": condition,
        "model": "m",
        "checkout_head": head,
        "answer": {"top": ["c"]},
        "is_error": error,
        "num_turns": 1,
        "cost_usd": 0.1,
        "wall_s": 1.0,
    }


def _runs_file(tmp_path: Path, records: list[dict[str, Any]]) -> Path:
    path = tmp_path / "r.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")
    return path


def test_score_unknown_task_id_exits_2(tmp_path, capsys):
    tasks = _write_tasks(tmp_path, TASKS)
    runs = _runs_file(tmp_path, [_record("ZZ", "before", "h1")])

    code = cap.main(["score", "--runs", str(runs), "--tasks", str(tasks)])

    assert code == 2
    assert "unknown task" in capsys.readouterr().err


def test_score_writes_out_file_and_warns_on_errors(tmp_path, capsys):
    tasks = _write_tasks(tmp_path, TASKS)
    records = [
        _record(t, c, f"{c}-{t}", error=(t == "A" and c == "before" and i == 0))
        for t in ("A", "B")
        for c in ("before", "after")
        for i in range(2)
    ]
    runs = _runs_file(tmp_path, records)
    out = tmp_path / "report.json"

    code = cap.main(["score", "--runs", str(runs), "--tasks", str(tasks), "--out", str(out)])

    captured = capsys.readouterr()
    assert code == 0
    assert json.loads(out.read_text(encoding="utf-8"))["A"]["before"]["errors"] == 1
    assert "warning" in captured.err and "A/before" in captured.err


def test_load_records_skips_blank_lines_and_rejects_non_json(tmp_path):
    path = tmp_path / "r.jsonl"
    path.write_text("\n" + json.dumps(_record("A", "before", "h")) + "\n\n", encoding="utf-8")

    assert len(cap.load_records(str(path), {"A"})) == 1
