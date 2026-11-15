"""Tests for the pure parts of scripts/eval/eval_io_portability_gap.py (no git, no ruff)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

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
