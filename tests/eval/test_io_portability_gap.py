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
