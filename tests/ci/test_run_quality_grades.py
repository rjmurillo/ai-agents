"""Tests for scripts/ci/run_quality_grades.py.

Covers the grading step extracted from quality-grades.yml. These tests pin the
`top_n` contract the bash regex encoded (empty and `0` mean unlimited, anything
non-numeric is a usage error), confirm the flag reaches the grader as separate
argv elements rather than an unquoted word-split string, and confirm the job
summary is appended only when GITHUB_STEP_SUMMARY is set.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPTS_CI = Path(__file__).resolve().parent.parent.parent / "scripts" / "ci"
_original_path = sys.path.copy()
try:
    sys.path.insert(0, str(_SCRIPTS_CI))
    from run_quality_grades import main, top_n_flag
finally:
    sys.path[:] = _original_path


@pytest.mark.parametrize("raw", ["", "0", "   ", " 0 "])
def test_unlimited_inputs_produce_no_flag(raw: str) -> None:
    assert top_n_flag(raw) == []


@pytest.mark.parametrize("raw", ["5", "10", " 25 "])
def test_numeric_input_produces_a_two_element_flag(raw: str) -> None:
    assert top_n_flag(raw) == ["--top-n", raw.strip()]


@pytest.mark.parametrize("raw", ["abc", "5; rm -rf /", "-1", "1.5", "5 10"])
def test_non_numeric_input_is_rejected(raw: str) -> None:
    with pytest.raises(ValueError, match="numeric"):
        top_n_flag(raw)


@pytest.mark.parametrize("raw", ["٥", "５", "١٠"])
def test_non_ascii_digits_are_rejected(raw: str) -> None:
    """The replaced bash regex ^[0-9]+$ only accepted ASCII digits."""
    with pytest.raises(ValueError, match="numeric"):
        top_n_flag(raw)


class _Grader:
    """Stand-in for subprocess.run that records argv and returns canned stdout."""

    def __init__(self, code: int = 0) -> None:
        self.calls: list[list[str]] = []
        self._code = code

    def __call__(self, argv, **kwargs):
        self.calls.append(list(argv))
        fmt = argv[argv.index("--format") + 1]
        return subprocess.CompletedProcess(argv, self._code, f"{fmt} body\n", "boom")


def _grader_file(tmp_path: Path) -> Path:
    path = tmp_path / "grade_domains.py"
    path.write_text("", encoding="utf-8")
    return path


def _args(tmp_path: Path, top_n: str = "") -> list[str]:
    return [
        "--grader", str(_grader_file(tmp_path)),
        "--json-out", str(tmp_path / "g.json"),
        "--markdown-out", str(tmp_path / "g.md"),
        "--top-n", top_n,
    ]


def test_writes_both_reports(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    monkeypatch.setattr(subprocess, "run", _Grader())
    assert main(_args(tmp_path)) == 0
    assert (tmp_path / "g.json").read_text(encoding="utf-8") == "json body\n"
    assert (tmp_path / "g.md").read_text(encoding="utf-8") == "markdown body\n"


def test_top_n_reaches_the_grader_as_separate_argv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    grader = _Grader()
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    monkeypatch.setattr(subprocess, "run", grader)
    main(_args(tmp_path, top_n="7"))
    assert grader.calls[0][-2:] == ["--top-n", "7"]


def test_unlimited_omits_the_flag_entirely(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    grader = _Grader()
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    monkeypatch.setattr(subprocess, "run", grader)
    main(_args(tmp_path, top_n="0"))
    assert "--top-n" not in grader.calls[0]


def test_non_numeric_top_n_exits_two_before_running_the_grader(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    grader = _Grader()
    monkeypatch.setattr(subprocess, "run", grader)
    assert main(_args(tmp_path, top_n="abc")) == 2
    assert grader.calls == []
    assert "numeric" in capsys.readouterr().err


def test_missing_grader_is_a_usage_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = main(
        [
            "--grader", str(tmp_path / "absent.py"),
            "--json-out", str(tmp_path / "g.json"),
            "--markdown-out", str(tmp_path / "g.md"),
        ]
    )
    assert rc == 2
    assert "grader not found" in capsys.readouterr().err


def test_grader_failure_is_forwarded_as_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(subprocess, "run", _Grader(code=3))
    assert main(_args(tmp_path)) == 1
    assert "grader failed" in capsys.readouterr().err


def test_summary_is_appended_when_the_env_var_is_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    summary = tmp_path / "summary.md"
    summary.write_text("existing\n", encoding="utf-8")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    monkeypatch.setattr(subprocess, "run", _Grader())
    main(_args(tmp_path))
    body = summary.read_text(encoding="utf-8")
    assert body.startswith("existing\n")
    assert "## Quality Grades Report" in body
    assert "markdown body" in body


def test_no_summary_env_var_is_not_an_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    monkeypatch.setattr(subprocess, "run", _Grader())
    assert main(_args(tmp_path)) == 0
