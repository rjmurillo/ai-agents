"""Quota-skip count tests for scripts/validation/smoke_result.py.

`--count-dir` sums the per-leg counts and swaps the success message for the
count message when the total is above zero.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.validation.smoke_result import main, sum_counts


def test_sum_counts_adds_every_file_and_ignores_missing_dir(tmp_path: Path) -> None:
    (tmp_path / "leg-a").mkdir()
    (tmp_path / "leg-a" / "quota-skips.txt").write_text("1\n0\n", encoding="utf-8")
    (tmp_path / "leg-b.txt").write_text("2\n", encoding="utf-8")
    assert sum_counts(tmp_path) == 3
    assert sum_counts(tmp_path / "absent") == 0


def test_sum_counts_warns_on_a_non_integer_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "c.txt").write_text("2\nbogus\n", encoding="utf-8")
    assert sum_counts(tmp_path) == 2
    assert "::warning::ignoring non-integer count 'bogus'" in capsys.readouterr().out


def _count_args(count_dir: Path) -> list[str]:
    return [
        "--check",
        "A",
        "success",
        "a failed",
        "--success-message",
        "all green",
        "--count-dir",
        str(count_dir),
        "--count-message",
        "passed with {count} prompt checks quota-skipped",
    ]


def test_count_message_replaces_success_when_total_is_positive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("A", "success")
    (tmp_path / "c.txt").write_text("1\n2\n", encoding="utf-8")
    assert main(_count_args(tmp_path)) == 0
    assert capsys.readouterr().out.strip() == "passed with 3 prompt checks quota-skipped"


def test_success_message_stays_when_total_is_zero_or_dir_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("A", "success")
    (tmp_path / "c.txt").write_text("0\n0\n", encoding="utf-8")
    assert main(_count_args(tmp_path)) == 0
    assert capsys.readouterr().out.strip() == "all green"
    assert main(_count_args(tmp_path / "absent")) == 0
    assert capsys.readouterr().out.strip() == "all green"


def test_count_message_is_not_printed_when_a_check_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("A", "failure")
    (tmp_path / "c.txt").write_text("5\n", encoding="utf-8")
    assert main(_count_args(tmp_path)) == 1
    assert "quota-skipped" not in capsys.readouterr().out


def test_count_dir_without_count_message_keeps_the_success_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("A", "success")
    (tmp_path / "c.txt").write_text("4\n", encoding="utf-8")
    rc = main(
        ["--check", "A", "success", "x", "--success-message", "ok", "--count-dir", str(tmp_path)]
    )
    assert rc == 0
    assert capsys.readouterr().out.strip() == "ok"
