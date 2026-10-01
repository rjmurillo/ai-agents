"""Tests for scripts/eval/eval_routing_corpus.py (issue #5425).

Drives `main(argv)` and the real process boundary, asserting on the exit code
and the printed JSON, per testing.md MUST-8.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tests.eval._routing_corpus_test_support import (
    BOUNDED,
    EVAL_DIR,
    SCOPE,
    cli,
    copy_corpus,
)

SCRIPT_PATH = EVAL_DIR / "eval_routing_corpus.py"


def test_main_exit_0_and_reports_six_examined_scenarios(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = cli.main([])

    report = json.loads(capsys.readouterr().out)
    assert exit_code == cli.EXIT_OK
    assert report["examined"] == 6 and report["failed"] == 0
    assert {row["category"] for row in report["scenarios"]} == {
        "bounded_implementation",
        "multi_file_invariants",
        "investigate_before_edit",
        "scope_expansion",
        "plausible_but_wrong",
        "architecture_resolved",
    }
    assert all(row["ok"] for row in report["scenarios"])


def test_main_exit_2_when_a_category_is_missing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = copy_corpus(tmp_path)
    shutil.move(root / SCOPE, tmp_path / "moved")

    exit_code = cli.main(["--corpus", str(root)])

    captured = capsys.readouterr()
    assert exit_code == cli.EXIT_CORPUS_INVALID
    assert "scope_expansion" in captured.err and captured.out == ""


def test_main_exit_2_when_the_corpus_path_is_not_a_directory(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = cli.main(["--corpus", str(tmp_path / "absent")])

    assert exit_code == cli.EXIT_CORPUS_INVALID
    assert "not a directory" in capsys.readouterr().err


def test_main_exit_1_when_a_control_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = copy_corpus(tmp_path)
    base = root / BOUNDED
    (base / "known_good").rename(base / "swap")
    (base / "known_bad").rename(base / "known_good")
    (base / "swap").rename(base / "known_bad")

    exit_code = cli.main(["--corpus", str(root)])

    report = json.loads(capsys.readouterr().out)
    assert exit_code == cli.EXIT_CONTROL_FAILED
    assert report["examined"] == 6 and report["failed"] == 1
    failing = [row for row in report["scenarios"] if not row["ok"]]
    assert [row["id"] for row in failing] == [BOUNDED]


def test_script_runs_as_a_process_and_exits_0() -> None:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT_PATH)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=120,
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)["examined"] == 6
