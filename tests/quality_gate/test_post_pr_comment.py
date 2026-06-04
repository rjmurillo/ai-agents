"""Tests for scripts/quality_gate/post_pr_comment.py.

Pins the precondition guards and the command shape of the extracted
``Post PR Comment`` workflow step. The subprocess is mocked so no real GitHub
call is made.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.quality_gate import post_pr_comment
from scripts.quality_gate.post_pr_comment import build_command, main, parse_pr_number


# ---------------------------------------------------------------------------
# build_command
# ---------------------------------------------------------------------------


class TestBuildCommand:
    def test_includes_retry_wrapper_and_poster(self) -> None:
        cmd = build_command(123, "/workspace/report.md")
        joined = " ".join(cmd)
        assert "run_with_retry.py" in joined
        assert "--" in cmd
        assert "post_issue_comment.py" in joined

    def test_passes_issue_body_marker_and_update_flag(self) -> None:
        cmd = build_command(123, "/workspace/report.md")
        assert "--issue" in cmd
        assert cmd[cmd.index("--issue") + 1] == "123"
        assert "--body-file" in cmd
        assert cmd[cmd.index("--body-file") + 1] == "/workspace/report.md"
        assert "--marker" in cmd
        assert cmd[cmd.index("--marker") + 1] == "AI-PR-QUALITY-GATE"
        assert "--update-if-exists" in cmd


# ---------------------------------------------------------------------------
# parse_pr_number
# ---------------------------------------------------------------------------


class TestParsePrNumber:
    def test_accepts_positive_integer(self) -> None:
        assert parse_pr_number("123") == 123

    def test_rejects_shell_metacharacters(self) -> None:
        assert parse_pr_number("1;echo") is None

    def test_rejects_zero(self) -> None:
        assert parse_pr_number("0") is None

    def test_rejects_negative(self) -> None:
        assert parse_pr_number("-1") is None


# ---------------------------------------------------------------------------
# main: guard clauses
# ---------------------------------------------------------------------------


class TestGuards:
    def test_missing_pr_number_returns_one(self, monkeypatch, capsys) -> None:
        monkeypatch.delenv("PR_NUMBER", raising=False)
        monkeypatch.setenv("REPORT_FILE", "/workspace/x.md")
        rc = main([])
        assert rc == 1
        assert "PR_NUMBER environment variable is missing" in capsys.readouterr().out

    def test_non_digit_pr_number_returns_one(self, monkeypatch, capsys, tmp_path) -> None:
        report = tmp_path / "report.md"
        report.write_text("body", encoding="utf-8")
        monkeypatch.setenv("PR_NUMBER", "1;echo")
        monkeypatch.setenv("REPORT_FILE", str(report))
        rc = main([])
        assert rc == 1
        assert "PR_NUMBER must be a positive integer" in capsys.readouterr().out

    def test_missing_report_file_var_returns_one(self, monkeypatch, capsys) -> None:
        monkeypatch.setenv("PR_NUMBER", "123")
        monkeypatch.delenv("REPORT_FILE", raising=False)
        rc = main([])
        assert rc == 1
        assert "REPORT_FILE environment variable is missing" in capsys.readouterr().out

    def test_report_file_not_found_returns_one(self, monkeypatch, capsys, tmp_path) -> None:
        monkeypatch.setenv("PR_NUMBER", "123")
        monkeypatch.setenv("REPORT_FILE", str(tmp_path / "absent.md"))
        rc = main([])
        assert rc == 1
        assert "Report file not found" in capsys.readouterr().out

    def test_report_file_outside_workspace_returns_one(self, monkeypatch, capsys, tmp_path) -> None:
        outside = tmp_path.parent / "outside.md"
        monkeypatch.setenv("PR_NUMBER", "123")
        monkeypatch.setenv("REPORT_FILE", str(outside))
        rc = main([])
        assert rc == 1
        assert "REPORT_FILE must stay within" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# main: subprocess behavior (mocked)
# ---------------------------------------------------------------------------


class TestSubprocess:
    def _setup_valid(self, monkeypatch, tmp_path) -> Path:
        report = tmp_path / "report.md"
        report.write_text("body", encoding="utf-8")
        monkeypatch.setenv("PR_NUMBER", "123")
        monkeypatch.setenv("REPORT_FILE", str(report))
        return report

    def test_returns_poster_exit_code_zero(self, monkeypatch, tmp_path) -> None:
        self._setup_valid(monkeypatch, tmp_path)

        def fake_run(cmd, timeout, check):  # noqa: ANN001
            assert "post_issue_comment.py" in " ".join(cmd)
            return subprocess.CompletedProcess(cmd, 0)

        monkeypatch.setattr(post_pr_comment.subprocess, "run", fake_run)
        assert main([]) == 0

    def test_propagates_poster_failure(self, monkeypatch, tmp_path) -> None:
        self._setup_valid(monkeypatch, tmp_path)

        def fake_run(cmd, timeout, check):  # noqa: ANN001
            return subprocess.CompletedProcess(cmd, 1)

        monkeypatch.setattr(post_pr_comment.subprocess, "run", fake_run)
        assert main([]) == 1

    def test_timeout_returns_three(self, monkeypatch, tmp_path, capsys) -> None:
        self._setup_valid(monkeypatch, tmp_path)

        def fake_run(cmd, timeout, check):  # noqa: ANN001
            raise subprocess.TimeoutExpired(cmd, timeout)

        monkeypatch.setattr(post_pr_comment.subprocess, "run", fake_run)
        rc = main(["--timeout", "5"])
        assert rc == 3
        assert "timed out" in capsys.readouterr().out

    def test_timeout_value_is_passed_through(self, monkeypatch, tmp_path) -> None:
        self._setup_valid(monkeypatch, tmp_path)
        seen = {}

        def fake_run(cmd, timeout, check):  # noqa: ANN001
            seen["timeout"] = timeout
            return subprocess.CompletedProcess(cmd, 0)

        monkeypatch.setattr(post_pr_comment.subprocess, "run", fake_run)
        main(["--timeout", "42"])
        assert seen["timeout"] == 42.0
