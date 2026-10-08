"""Quota-skip count safety tests for scripts/validation/smoke_result.py.

A bad count file must never turn into a trusted number: negatives, undecodable
or unreadable files are ignored with a warning and the count reads "unknown".
The count message is also published as a notice and a step summary line.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.validation.smoke_result import main, sum_counts

Capsys = pytest.CaptureFixture[str]


def _count_args(count_dir: Path) -> list[str]:
    return [
        *("--check", "A", "success", "a failed"),
        *("--success-message", "all green"),
        *("--count-dir", str(count_dir)),
        *("--count-message", "passed with {count} prompt checks quota-skipped"),
    ]


def test_sum_counts_ignores_a_negative_integer_with_a_warning(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """CWE-20: -5 must not cancel a real count and hide a skip."""
    (tmp_path / "c.txt").write_text("2\n-5\n", encoding="utf-8")

    assert sum_counts(tmp_path) == (2, False)
    assert "::warning::ignoring negative count '-5'" in capsys.readouterr().out


def test_sum_counts_continues_past_an_unreadable_or_undecodable_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "a-bad.txt").write_bytes(b"\xff\xfe\x00")
    (tmp_path / "b-good.txt").write_text("4\n", encoding="utf-8")
    (tmp_path / "c-dir.txt").mkdir()

    assert sum_counts(tmp_path) == (4, False)
    assert "::warning::ignoring unreadable count file" in capsys.readouterr().out


def test_sum_counts_warns_on_a_read_oserror(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "c.txt"
    target.write_text("1\n", encoding="utf-8")

    def boom(self: Path, *args: object, **kwargs: object) -> str:
        raise PermissionError("denied")

    monkeypatch.setattr(Path, "read_text", boom)

    assert sum_counts(tmp_path) == (0, False)
    assert "PermissionError" in capsys.readouterr().out


def test_rejected_token_prints_unknown_count_even_when_total_is_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("A", "success")
    (tmp_path / "c.txt").write_text("-1\n", encoding="utf-8")

    assert main(_count_args(tmp_path)) == 0

    out = capsys.readouterr().out
    assert "::notice::passed with unknown prompt checks quota-skipped" in out


def test_count_message_is_appended_to_the_step_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    summary = tmp_path / "summary.md"
    counts = tmp_path / "counts"
    counts.mkdir()
    (counts / "c.txt").write_text("2\n", encoding="utf-8")
    monkeypatch.setenv("A", "success")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))

    assert main(_count_args(counts)) == 0

    assert summary.read_text(encoding="utf-8") == "passed with 2 prompt checks quota-skipped\n"


def test_success_message_does_not_touch_the_step_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("A", "success")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))

    assert main(_count_args(tmp_path / "absent")) == 0

    assert not summary.exists()


def test_count_message_without_count_dir_is_a_usage_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("A", "success")
    rc = main(["--check", "A", "success", "x", "--count-message", "n={count}"])

    assert rc == 2
    assert "--count-message needs --count-dir" in capsys.readouterr().err
