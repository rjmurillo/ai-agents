"""Tests for scripts/eval/eval_io_portability_gap.py that need no git history; ruff is faked."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

EVAL_DIR = Path(__file__).resolve().parents[2] / "scripts" / "eval"


def _load() -> Any:
    spec = importlib.util.spec_from_file_location(
        "eval_io_portability_gap", EVAL_DIR / "eval_io_portability_gap.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


gap = _load()
MULTILINE = "import subprocess\nsubprocess.run(\n    ['git'],\n    text=True,\n)\n"


def test_treatment_lines_cover_the_whole_call() -> None:
    assert gap.treatment_lines("t.py", MULTILINE, "subprocess-text-encoding") == [2, 3, 4, 5]


def test_near_uses_the_line_window() -> None:
    assert gap.near([10], 10 + gap.LINE_WINDOW)
    assert not gap.near([10], 11 + gap.LINE_WINDOW)


def test_rule_count_counts_only_the_named_rule() -> None:
    source = MULTILINE + "open('f')\n"

    assert gap.rule_count("t.py", source, "file-text-encoding") == 1


def test_summarize_splits_and_counts_errors() -> None:
    rows = [
        {"split": "derive", "rule": "r", "baseline_caught": False, "treatment_caught": True},
        {"split": "heldout", "rule": "r", "baseline_caught": False, "treatment_caught": False},
        {"split": "heldout", "rule": "r", "error": "unreadable"},
    ]

    out = gap.summarize(rows)

    assert out["errors"] == 1
    assert out["all"]["treatment"]["hits"] == 1
    assert out["heldout"]["treatment"]["n"] == 1
    assert out["r"]["baseline"]["hits"] == 0


def test_shipped_lines_without_a_merge_base_is_empty() -> None:
    row = {"rule": "file-text-encoding", "path": "t.py", "reviewed": "a" * 40}

    assert gap.shipped_lines(row, "open('f')\n") == []


def test_malformed_commit_id_becomes_an_error_row_not_a_miss() -> None:
    row = {"thread": "T1", "rule": "file-text-encoding", "path": "t.py", "line": 1,
           "reviewed": "--output=/tmp/x", "final_head": "a" * 40, "merge_base": None}  # fmt: skip

    result = gap.evaluate(row)

    assert "not a 40-hex commit id" in result["error"]
    assert "treatment_caught" not in result


def test_a_ruff_failure_is_raised_not_scored(monkeypatch: pytest.MonkeyPatch) -> None:
    import subprocess

    def failed(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess([], 2, stdout="", stderr="boom")

    monkeypatch.setattr(gap.subprocess, "run", failed)

    with pytest.raises(RuntimeError, match="ruff exited 2"):
        gap.ruff_lines("t.py", "x = 1\n", {"PLW1514"})


def test_a_failed_shipped_diff_is_an_error_row(monkeypatch: pytest.MonkeyPatch) -> None:
    def failing(_root: object, base: str, head: str) -> dict[str, set[int]]:
        raise ValueError(f"git diff {base}...{head} failed")

    monkeypatch.setattr(gap.treatment, "added_line_numbers", failing)
    row = {
        "rule": "file-text-encoding",
        "path": "t.py",
        "reviewed": "a" * 40,
        "merge_base": "b" * 40,
    }

    with pytest.raises(ValueError, match="failed"):
        gap.shipped_lines(row, "open('f')\n")


def test_evaluate_turns_a_tool_timeout_into_an_error_row(monkeypatch: pytest.MonkeyPatch) -> None:
    import subprocess

    def stalled(*_a: object, **_k: object) -> str:
        raise subprocess.TimeoutExpired("git", 60)

    monkeypatch.setattr(gap, "git_show", stalled)
    row = {"thread": "T1", "rule": "file-text-encoding", "path": "t.py", "line": 1,
           "reviewed": "a" * 40, "final_head": "b" * 40, "merge_base": None}  # fmt: skip

    assert "timed out" in gap.evaluate(row)["error"]


def test_unreadable_final_head_is_counted_apart_from_the_control() -> None:
    rows = [
        {"split": "heldout", "rule": "r", "baseline_caught": False, "treatment_caught": True,
         "shipped_caught": True, "final_head_not_lower": None},
        {"split": "heldout", "rule": "r", "baseline_caught": False, "treatment_caught": True,
         "shipped_caught": True, "final_head_not_lower": False},
    ]  # fmt: skip

    out = gap.summarize(rows)

    assert out["heldout"]["final_head_unreadable"] == 1
    assert out["heldout"]["final_head_not_lower"]["hits"] == 0
    assert out["heldout"]["final_head_not_lower"]["n"] == 1


def test_evaluate_turns_a_failed_shipped_diff_into_an_error_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def failing(_root: object, base: str, head: str) -> dict[str, set[int]]:
        raise ValueError(f"git diff {base}...{head} failed")

    monkeypatch.setattr(gap.treatment, "added_line_numbers", failing)
    monkeypatch.setattr(gap, "git_show", lambda _c, _p: "open('f')\n")
    monkeypatch.setattr(gap, "ruff_lines", lambda _p, _s, _c: [])
    row = {"thread": "T1", "rule": "file-text-encoding", "path": "t.py", "line": 1,
           "reviewed": "a" * 40, "final_head": "b" * 40, "merge_base": "c" * 40}  # fmt: skip

    out = gap.evaluate(row)

    assert "failed" in out["error"]
    assert "shipped_caught" not in out


def test_git_that_times_out_raises_runtime_error(monkeypatch: pytest.MonkeyPatch) -> None:
    import subprocess

    def stalled(*_a: object, **_k: object) -> None:
        raise subprocess.TimeoutExpired("git", 60)

    monkeypatch.setattr(subprocess, "run", stalled)

    with pytest.raises(RuntimeError, match="could not run"):
        gap.git_show("a" * 40, "t.py")


def test_main_exits_3_when_a_row_cannot_be_scored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    corpus = tmp_path / "c.json"
    corpus.write_text(
        '{"rows": [{"thread": "T1", "rule": "file-text-encoding", "path": "t.py", "line": 1,'
        ' "reviewed": "--output=x", "final_head": null, "merge_base": null, "split": "derive"}]}',
        encoding="utf-8",
    )
    monkeypatch.setattr(gap, "REPO_ROOT", tmp_path)

    code = gap.main(["--corpus", "c.json"])

    assert code == 3
    assert "T1: reviewed is not a 40-hex commit id" in capsys.readouterr().err
