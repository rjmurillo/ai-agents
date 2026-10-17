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
        {"id": "S", "prompt": "x", "grader": "set_f1", "gold": ["a", "b"]},
        {"id": "R", "prompt": "x", "grader": "set_f1_prefix", "gold": ["abcdef123"]},
        {
            "id": "P",
            "prompt": "x",
            "grader": "pairs_f1",
            "gold": [{"skill": "s1", "path": "x.py"}],
            "ignore": [{"skill": "s2", "path": "y.py"}],
        },
        {
            "id": "Q",
            "prompt": "x",
            "grader": "pairs_f1",
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


def record(task_id: str, condition: str, answer: Any, is_error: bool = False) -> dict[str, Any]:
    return {
        "task": task_id,
        "condition": condition,
        "answer": answer,
        "is_error": is_error,
        "num_turns": 3,
        "cost_usd": 0.01,
        "wall_s": 1.0,
    }


def write_runs(path: Path, *records: Any) -> Path:
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")
    return path


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
        cap.grade({"grader": "nope", "gold": []}, {"x": []})


def test_score_ignores_error_runs_in_quality_means(tmp_path, tasks_file, capsys):
    runs = write_runs(
        tmp_path / "r.jsonl",
        record("S", "after", {"top": ["a", "b"]}),
        record("S", "after", None, is_error=True),
    )

    code = cap.main(["score", "--runs", str(runs), "--tasks", str(tasks_file)])

    cell = json.loads(capsys.readouterr().out)["S"]["after"]
    assert code == 0
    assert cell["f1"] == 1.0
    assert cell["errors"] == 1


def test_score_exits_1_when_every_run_errored(tmp_path, tasks_file, capsys):
    runs = write_runs(tmp_path / "r.jsonl", record("S", "after", None, is_error=True))

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


def test_score_treats_a_non_object_answer_as_no_answer(tmp_path, tasks_file, capsys):
    runs = write_runs(tmp_path / "r.jsonl", record("S", "after", ["a", "b"]))

    cap.main(["score", "--runs", str(runs), "--tasks", str(tasks_file)])

    assert json.loads(capsys.readouterr().out)["S"]["after"]["f1"] == 0.0


def test_run_one_records_a_non_object_cli_payload_as_an_error(monkeypatch, tmp_path):
    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args, 0, "[1, 2]", "")

    monkeypatch.setattr(cap.subprocess, "run", fake_run)

    result = cap.run_one(tmp_path, "prompt", "model")

    assert result["is_error"] is True
    assert result["num_turns"] is None


def test_load_tasks_rejects_a_task_without_gold(tmp_path):
    path = tmp_path / "t.json"
    path.write_text(json.dumps({"tasks": [{"id": "a", "prompt": "p", "grader": "set_f1"}]}))

    with pytest.raises(ValueError, match="gold"):
        cap.load_tasks(path)


def test_frozen_fixture_loads():
    data = cap.load_tasks(cap.DEFAULT_TASKS)

    assert {t["id"] for t in data["tasks"]} >= {"T1-stale-refs", "T4-line-refs-at-scale"}


def test_run_one_records_a_timeout_as_an_error(monkeypatch, tmp_path):
    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="claude", timeout=1)

    monkeypatch.setattr(cap.subprocess, "run", fake_run)

    result = cap.run_one(tmp_path, "prompt", "model")

    assert result["is_error"] is True
    assert result["result"] == ""


def test_prefix_precision_counts_predictions_not_gold_matches():
    two_gold = {"id": "R2", "grader": "set_f1_prefix", "gold": ["abcdef123", "abcdef145"]}

    score = cap.grade(two_gold, {"reverts": ["abcdef1"]})

    assert score["precision"] == 1.0
    assert score["recall"] == 1.0


def test_prefix_precision_penalizes_a_prediction_that_matches_nothing():
    score = cap.grade(task("R"), {"reverts": ["abcdef1", "fffffff"]})

    assert score["precision"] == 0.5
    assert score["recall"] == 1.0


def test_run_one_grants_only_read_only_tools(monkeypatch, tmp_path):
    seen: list[list[str]] = []

    def fake_run(argv, *args, **kwargs):
        seen.append(argv)
        return subprocess.CompletedProcess(argv, 0, "{}", "")

    monkeypatch.setattr(cap.subprocess, "run", fake_run)

    cap.run_one(tmp_path, "prompt", "model")

    argv = seen[0]
    assert "bypassPermissions" not in argv
    granted = argv[argv.index("--allowedTools") + 1 : argv.index("--disallowedTools")]
    assert granted == list(cap.READ_ONLY_TOOLS)
    assert not any(t in ("Bash", "Edit", "Write") for t in granted)
