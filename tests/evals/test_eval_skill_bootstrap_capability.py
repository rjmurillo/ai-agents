"""Tests for scripts/eval/eval_skill_bootstrap_capability.py (grading and scoring)."""

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
    spec = importlib.util.spec_from_file_location("eval_skill_bootstrap_capability", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cap = _load()

TASKS: dict[str, Any] = {
    "preamble": "p",
    "tasks": [
        {"id": "S", "prompt": "x", "grader": "set_f1", "answer_key": "top", "gold": ["a", "b"]},
        {
            "id": "R",
            "prompt": "x",
            "grader": "set_f1_prefix",
            "answer_key": "reverts",
            "gold": ["abcdef123"],
        },
        {
            "id": "P",
            "prompt": "x",
            "grader": "pairs_f1",
            "answer_key": "stale",
            "gold": [{"skill": "s1", "path": "x.py"}],
            "ignore": [{"skill": "s2", "path": "y.py"}],
        },
        {
            "id": "Q",
            "prompt": "x",
            "grader": "pairs_f1",
            "answer_key": "stale",
            "answer_fields": ["skill", "ref"],
            "gold": [{"skill": "s1", "ref": "A.md:40"}],
        },
    ],
}


def task(task_id: str) -> dict[str, Any]:
    return next(t for t in TASKS["tasks"] if t["id"] == task_id)


@pytest.fixture
def tasks_file(tmp_path: Path) -> Path:
    path = tmp_path / "tasks.json"
    path.write_text(json.dumps(TASKS), encoding="utf-8")
    return path


def record(task_id: str, condition: str, answer: Any, is_error: bool = False, **extra: Any):
    return {
        "task": task_id,
        "condition": condition,
        "model": "m",
        "checkout_head": f"head-{condition}",
        "answer": answer,
        "is_error": is_error,
        "num_turns": 3,
        "cost_usd": 0.01,
        "wall_s": 1.0,
        **extra,
    }


def write_runs(path: Path, *records: Any) -> Path:
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")
    return path


def full_matrix(*records: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    """Add one answered run for every task and condition the given records leave empty."""
    present = {(r["task"], r["condition"]) for r in records}
    filler = [
        record(t["id"], c, {"x": []})
        for t in TASKS["tasks"]
        for c in cap.CONDITIONS
        if (t["id"], c) not in present
    ]
    return (*records, *filler)


def test_extract_answer_takes_the_last_valid_json_object():
    text = '```json\n{"a": 1}\n```\n```json\nnot json\n```\n```json\n{"a": 2}\n```'

    assert cap.extract_answer(text) == {"a": 2}


def test_extract_answer_without_a_block_is_none():
    assert cap.extract_answer("no block") is None


def test_set_f1_scores_overlap():
    score = cap.grade(task("S"), {"top": ["a", "c"]})

    assert score == {"precision": 0.5, "recall": 0.5, "f1": 0.5}


def test_prefix_grader_accepts_a_shorter_sha():
    assert cap.grade(task("R"), {"reverts": ["abcdef1"]})["f1"] == 1.0


def test_pairs_grader_drops_ignored_pairs_and_line_suffixes():
    answer = {"stale": [{"skill": "s1", "path": "x.py:12"}, {"skill": "s2", "path": "y.py"}]}

    assert cap.grade(task("P"), answer)["f1"] == 1.0


def test_pairs_grader_uses_configured_fields_verbatim():
    assert cap.grade(task("Q"), {"stale": [{"skill": "s1", "ref": "A.md:40"}]})["f1"] == 1.0
    assert cap.grade(task("Q"), {"stale": [{"skill": "s1", "ref": "A.md:41"}]})["f1"] == 0.0


def test_missing_answer_scores_zero():
    assert cap.grade(task("S"), None) == {"precision": 0.0, "recall": 0.0, "f1": 0.0}


def test_unknown_grader_is_a_config_error():
    with pytest.raises(ValueError, match="unknown grader"):
        cap.grade({"grader": "nope", "answer_key": "x", "gold": []}, {"x": []})


def test_score_ignores_error_runs_in_quality_means(tmp_path, tasks_file, capsys):
    runs = write_runs(
        tmp_path / "r.jsonl",
        *full_matrix(
            record("S", "after", {"top": ["a", "b"]}),
            record("S", "after", None, is_error=True),
        ),
    )

    code = cap.main(["score", "--runs", str(runs), "--tasks", str(tasks_file)])

    cell = json.loads(capsys.readouterr().out)["S"]["after"]
    assert code == 0
    assert cell["f1"] == 1.0
    assert cell["errors"] == 1


def test_score_exits_1_when_every_run_errored(tmp_path, tasks_file, capsys):
    runs = write_runs(tmp_path / "r.jsonl", *full_matrix(record("S", "after", None, is_error=True)))

    assert cap.main(["score", "--runs", str(runs), "--tasks", str(tasks_file)]) == 1


@pytest.mark.parametrize(
    "line",
    [
        '["not", "an", "object"]',
        '"text"',
        '{"task": "S"}',
        '{"task": "X", "condition": "a", "answer": null, "is_error": false}',
        "{broken",
    ],
)
def test_score_rejects_unusable_lines_with_exit_2(tmp_path, tasks_file, capsys, line):
    runs = tmp_path / "r.jsonl"
    runs.write_text(line + "\n", encoding="utf-8")

    assert cap.main(["score", "--runs", str(runs), "--tasks", str(tasks_file)]) == 2


def test_score_rejects_invalid_utf8_with_exit_2(tmp_path, tasks_file, capsys):
    runs = tmp_path / "r.jsonl"
    runs.write_bytes(b"\xff\xfe\n")

    assert cap.main(["score", "--runs", str(runs), "--tasks", str(tasks_file)]) == 2


@pytest.mark.parametrize(
    "overrides",
    [
        {"answer": ["a", "b"]},
        {"is_error": "false"},
        {"num_turns": True},
        {"wall_s": None},
        {"model": None},
    ],
)
def test_score_rejects_a_mistyped_record_field_with_exit_2(tmp_path, tasks_file, capsys, overrides):
    runs = write_runs(
        tmp_path / "r.jsonl", *full_matrix({**record("S", "after", None), **overrides})
    )

    assert cap.main(["score", "--runs", str(runs), "--tasks", str(tasks_file)]) == 2
    assert next(iter(overrides)) in capsys.readouterr().err


def test_score_rejects_a_record_missing_its_checkout_head(tmp_path, tasks_file, capsys):
    rec = record("S", "after", None)
    del rec["checkout_head"]
    runs = write_runs(tmp_path / "r.jsonl", *full_matrix(rec))

    assert cap.main(["score", "--runs", str(runs), "--tasks", str(tasks_file)]) == 2
    assert "checkout_head" in capsys.readouterr().err


class _Child:
    pid = 1

    def __init__(self, outcome):
        self.outcome, self.returncode, self.timed_out = outcome, 0, False

    def communicate(self, timeout=None):
        if isinstance(self.outcome, BaseException) and not self.timed_out:
            self.timed_out = True
            raise self.outcome
        if isinstance(self.outcome, BaseException):
            return "", ""
        return self.outcome.stdout, self.outcome.stderr

    def kill(self):
        pass


def _patch_popen(monkeypatch, outcome, seen=None):
    def fake_popen(argv, **kwargs):
        if seen is not None:
            seen.append(argv)
        return _Child(outcome)

    monkeypatch.setattr(cap.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(cap.os, "killpg", lambda pid, sig: None)


def test_run_one_records_a_non_object_cli_payload_as_an_error(monkeypatch, tmp_path):
    _patch_popen(monkeypatch, subprocess.CompletedProcess([], 0, "[1, 2]", ""))

    result = cap.run_one(tmp_path, "prompt", "model")

    assert result["is_error"] is True
    assert result["num_turns"] is None


def test_load_tasks_rejects_a_task_without_gold(tmp_path):
    path = tmp_path / "t.json"
    task = {"id": "a", "prompt": "p", "grader": "set_f1", "answer_key": "k"}
    path.write_text(json.dumps({"preamble": "p", "tasks": [task]}), encoding="utf-8")

    with pytest.raises(ValueError, match="gold"):
        cap.load_tasks(path)


def test_frozen_fixture_loads():
    data = cap.load_tasks(cap.DEFAULT_TASKS)

    assert {t["id"] for t in data["tasks"]} >= {"T1-stale-refs", "T4-line-refs-at-scale"}


def test_run_one_records_a_timeout_as_an_error(monkeypatch, tmp_path):
    _patch_popen(monkeypatch, subprocess.TimeoutExpired(cmd="claude", timeout=1))

    result = cap.run_one(tmp_path, "prompt", "model")

    assert result["is_error"] is True
    assert result["result"] == ""


def test_prefix_precision_counts_predictions_not_gold_matches():
    two_gold = {**task("R"), "gold": ["abcdef123", "abcdef145"]}

    score = cap.grade(two_gold, {"reverts": ["abcdef1"]})

    assert score["precision"] == 1.0
    assert score["recall"] == 1.0


def test_prefix_precision_penalizes_a_prediction_that_matches_nothing():
    score = cap.grade(task("R"), {"reverts": ["abcdef1", "fffffff"]})

    assert score["precision"] == 0.5
    assert score["recall"] == 1.0


def test_run_one_grants_only_read_only_tools(monkeypatch, tmp_path):
    seen: list[list[str]] = []
    _patch_popen(monkeypatch, subprocess.CompletedProcess([], 0, "{}", ""), seen)

    cap.run_one(tmp_path, "prompt", "model")

    argv = seen[0]
    assert "bypassPermissions" not in argv
    granted = argv[argv.index("--allowedTools") + 1 : argv.index("--disallowedTools")]
    assert granted == list(cap.READ_ONLY_TOOLS)
    assert not any(t in ("Bash", "Edit", "Write") for t in granted)


def test_run_one_denies_bootstrap_drift_allow_commands(monkeypatch, tmp_path):
    seen: list[list[str]] = []
    _patch_popen(monkeypatch, subprocess.CompletedProcess([], 0, "{}", ""), seen)

    cap.run_one(tmp_path, "prompt", "model")

    denied = seen[0][seen[0].index("--disallowedTools") + 1 :]
    assert cap.DENY_DRIFT_COMMANDS in denied
    assert "bootstrap_drift.py" in cap.DENY_DRIFT_COMMANDS
    assert "--allow-commands" in cap.DENY_DRIFT_COMMANDS


def test_score_rejects_a_task_missing_from_one_condition_with_exit_2(tmp_path, tasks_file, capsys):
    records = [r for r in full_matrix() if (r["task"], r["condition"]) != ("R", "before")]
    runs = write_runs(tmp_path / "r.jsonl", *records)

    code = cap.main(["score", "--runs", str(runs), "--tasks", str(tasks_file)])

    assert code == 2
    assert "R/before" in capsys.readouterr().err


def test_score_rejects_an_unexpected_condition_with_exit_2(tmp_path, tasks_file, capsys):
    runs = write_runs(tmp_path / "r.jsonl", *full_matrix(record("S", "baseline", None)))

    code = cap.main(["score", "--runs", str(runs), "--tasks", str(tasks_file)])

    assert code == 2
    assert "baseline" in capsys.readouterr().err


def test_score_accepts_a_complete_matrix(tmp_path, tasks_file, capsys):
    runs = write_runs(tmp_path / "r.jsonl", *full_matrix())

    assert cap.main(["score", "--runs", str(runs), "--tasks", str(tasks_file)]) == 0
    assert set(json.loads(capsys.readouterr().out)["S"]) == {"before", "after"}


def test_run_rejects_an_unknown_condition(tmp_path):
    with pytest.raises(SystemExit) as exc:
        cap.main(["run", "--checkout", str(tmp_path), "--condition", "x", "--out", "o"])

    assert exc.value.code == 2


def test_tool_grant_names_each_skill_script_and_no_git_grep():
    python_grants = [t for t in cap.READ_ONLY_TOOLS if t.startswith("Bash(python3")]

    assert "Bash(git grep:*)" not in cap.READ_ONLY_TOOLS
    assert all(g.endswith(".py:*)") for g in python_grants)
    scripts = Path(SCRIPT).resolve().parents[2] / ".claude/skills/skill-bootstrap/scripts"
    named = {g.split("scripts/")[1].removesuffix(":*)") for g in python_grants}
    assert named == {p.name for p in scripts.glob("bootstrap_*.py")}


def test_grade_ignores_a_list_under_another_key():
    assert cap.grade(task("R"), {"other": ["abcdef123"]})["f1"] == 0.0


def test_grade_reads_the_named_key_after_an_unrelated_list():
    assert cap.grade(task("R"), {"notes": ["x"], "reverts": ["abcdef123"]})["f1"] == 1.0


def test_grade_scores_a_non_list_answer_field_zero():
    assert cap.grade(task("S"), {"top": "a"})["f1"] == 0.0


def test_frozen_fixture_prompts_name_their_answer_key():
    for t in cap.load_tasks(cap.DEFAULT_TASKS)["tasks"]:
        assert f'{{"{t["answer_key"]}":' in t["prompt"], t["id"]


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"model": "other"}, "mix models"),
        ({"checkout_head": "head-other"}, "2 checkouts"),
    ],
)
def test_score_rejects_a_confounded_comparison(tmp_path, tasks_file, capsys, overrides, message):
    runs = write_runs(
        tmp_path / "r.jsonl",
        *full_matrix(record("S", "after", None), record("S", "after", None, **overrides)),
    )

    assert cap.main(["score", "--runs", str(runs), "--tasks", str(tasks_file)]) == 2
    assert message in capsys.readouterr().err


def test_score_rejects_before_and_after_on_one_checkout(tmp_path, tasks_file, capsys):
    same = [{**r, "checkout_head": "h"} if r["task"] == "S" else r for r in full_matrix()]
    runs = write_runs(tmp_path / "r.jsonl", *same)

    assert cap.main(["score", "--runs", str(runs), "--tasks", str(tasks_file)]) == 2
    assert "same checkout" in capsys.readouterr().err


def test_score_allows_a_different_after_checkout_per_task(tmp_path, tasks_file, capsys):
    runs = write_runs(
        tmp_path / "r.jsonl", *full_matrix(record("S", "after", None, checkout_head="h2"))
    )

    assert cap.main(["score", "--runs", str(runs), "--tasks", str(tasks_file)]) == 0


@pytest.fixture
def checkout(tmp_path, monkeypatch):
    skill = tmp_path / "co" / ".claude" / "skills" / "skill-bootstrap"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("x", encoding="utf-8")
    monkeypatch.setattr(cap.shutil, "which", lambda name: "/bin/claude")
    return skill.parents[2]


@pytest.mark.parametrize("extra", [["--task", "nope"], ["--reps", "0"]])
def test_run_that_selects_no_work_exits_2_without_writing(tmp_path, tasks_file, checkout, extra):
    out = tmp_path / "out.jsonl"
    argv = ["run", "--checkout", str(checkout), "--condition", "after", "--tasks", str(tasks_file)]

    code = cap.main([*argv, "--out", str(out), *extra])

    assert code == 2
    assert not out.exists()
