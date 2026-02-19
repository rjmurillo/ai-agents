"""Tests for invoke_routing_gates.py routing-level enforcement hook."""

from __future__ import annotations

import json
import os
import sys
import time
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add project root to path for hook imports
_project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_project_root / ".claude" / "hooks"))

from invoke_routing_gates import (  # noqa: E402
    check_documentation_only,
    check_qa_evidence,
    get_today_session_log_local,
    is_valid_project_root,
    main,
)


class TestIsValidProjectRoot:
    def test_valid_with_git_dir(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        (tmp_path / ".git").mkdir()
        monkeypatch.chdir(tmp_path)
        assert is_valid_project_root() is True

    def test_valid_with_settings_json(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        (claude_dir / "settings.json").write_text("{}", encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        assert is_valid_project_root() is True

    def test_invalid_without_indicators(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.chdir(tmp_path)
        assert is_valid_project_root() is False


class TestGetTodaySessionLogLocal:
    def test_returns_latest_session_log(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.chdir(tmp_path)
        sessions = tmp_path / ".agents" / "sessions"
        sessions.mkdir(parents=True)

        from datetime import UTC, datetime

        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        (sessions / f"{today}-session-1.json").write_text("{}", encoding="utf-8")
        (sessions / f"{today}-session-2.json").write_text("{}", encoding="utf-8")

        result = get_today_session_log_local()
        assert result is not None
        assert "session-2" in result.name

    def test_returns_none_when_no_sessions(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.chdir(tmp_path)
        sessions = tmp_path / ".agents" / "sessions"
        sessions.mkdir(parents=True)
        assert get_today_session_log_local() is None

    def test_returns_none_when_dir_missing(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.chdir(tmp_path)
        assert get_today_session_log_local() is None


class TestTestQAEvidence:
    def test_finds_recent_qa_report(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.chdir(tmp_path)
        qa_dir = tmp_path / ".agents" / "qa"
        qa_dir.mkdir(parents=True)
        report = qa_dir / "test-report.md"
        report.write_text("# QA Report", encoding="utf-8")
        # Ensure file is recent
        os.utime(report, (time.time(), time.time()))
        assert check_qa_evidence() is True

    def test_ignores_old_qa_reports(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.chdir(tmp_path)
        qa_dir = tmp_path / ".agents" / "qa"
        qa_dir.mkdir(parents=True)
        report = qa_dir / "test-report.md"
        report.write_text("# QA Report", encoding="utf-8")
        # Set modification time to 48 hours ago
        old_time = time.time() - (48 * 3600)
        os.utime(report, (old_time, old_time))

        # Also make sure no session log exists
        sessions = tmp_path / ".agents" / "sessions"
        sessions.mkdir(parents=True)

        assert check_qa_evidence() is False

    def test_finds_qa_section_in_session_log(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.chdir(tmp_path)
        sessions = tmp_path / ".agents" / "sessions"
        sessions.mkdir(parents=True)

        from datetime import UTC, datetime

        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        log_content = "## QA\nAll tests passed."
        (sessions / f"{today}-session-1.json").write_text(log_content, encoding="utf-8")

        assert check_qa_evidence() is True


class TestTestDocumentationOnly:
    @patch("invoke_routing_gates.subprocess.run")
    def test_true_when_only_md_files(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="README.md\ndocs/guide.md\n",
            stderr="",
        )
        assert check_documentation_only() is True

    @patch("invoke_routing_gates.subprocess.run")
    def test_false_when_code_files_present(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="README.md\nsrc/main.py\n",
            stderr="",
        )
        assert check_documentation_only() is False

    @patch("invoke_routing_gates.subprocess.run")
    def test_true_when_no_changes(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        assert check_documentation_only() is True

    @patch("invoke_routing_gates.subprocess.run")
    def test_failclosed_on_git_error(self, mock_run: MagicMock) -> None:
        # Both three-dot and two-dot fail
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="fatal: not a git repository",
        )
        assert check_documentation_only() is False

    @patch("invoke_routing_gates.subprocess.run")
    def test_handles_gitignore_as_doc(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=".gitignore\nLICENSE\nCHANGELOG\n",
            stderr="",
        )
        assert check_documentation_only() is True

    @patch("invoke_routing_gates.subprocess.run")
    def test_config_files_not_docs(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="config.yml\n",
            stderr="",
        )
        assert check_documentation_only() is False

    @patch("invoke_routing_gates.subprocess.run")
    def test_fallback_to_two_dot_diff(self, mock_run: MagicMock) -> None:
        # First call (three-dot) fails, second (two-dot) succeeds
        mock_run.side_effect = [
            MagicMock(returncode=1, stdout="", stderr="error"),
            MagicMock(returncode=0, stdout="README.md\n", stderr=""),
        ]
        assert check_documentation_only() is True


class TestMainAllowPath:
    @patch("invoke_routing_gates.is_valid_project_root", return_value=False)
    def test_failopen_on_invalid_project_root(self, _mock_root: MagicMock) -> None:
        assert main() == 0

    @patch("invoke_routing_gates.is_valid_project_root", return_value=True)
    @patch("invoke_routing_gates.sys.stdin")
    def test_allows_when_tty(
        self,
        mock_stdin: MagicMock,
        _mock_root: MagicMock,
    ) -> None:
        mock_stdin.isatty.return_value = True
        assert main() == 0

    @patch("invoke_routing_gates.is_valid_project_root", return_value=True)
    @patch("invoke_routing_gates.sys.stdin", new_callable=StringIO)
    def test_allows_non_pr_create_commands(
        self,
        mock_stdin: StringIO,
        _mock_root: MagicMock,
    ) -> None:
        data = json.dumps({"tool_input": {"command": "git commit -m test"}})
        mock_stdin.write(data)
        mock_stdin.seek(0)
        with patch.object(mock_stdin, "isatty", return_value=False):
            assert main() == 0


class TestMainQAGate:
    @patch("invoke_routing_gates.write_audit_log")
    @patch("invoke_routing_gates.is_valid_project_root", return_value=True)
    @patch("invoke_routing_gates.sys.stdin", new_callable=StringIO)
    def test_bypass_with_skip_qa_gate_env(
        self,
        mock_stdin: StringIO,
        _mock_root: MagicMock,
        _mock_audit: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("SKIP_QA_GATE", "true")
        data = json.dumps({"tool_input": {"command": "gh pr create --title test"}})
        mock_stdin.write(data)
        mock_stdin.seek(0)
        with patch.object(mock_stdin, "isatty", return_value=False):
            assert main() == 0

    @patch("invoke_routing_gates.check_documentation_only", return_value=True)
    @patch("invoke_routing_gates.is_valid_project_root", return_value=True)
    @patch("invoke_routing_gates.sys.stdin", new_callable=StringIO)
    def test_bypass_for_docs_only_prs(
        self,
        mock_stdin: StringIO,
        _mock_root: MagicMock,
        _mock_docs: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("SKIP_QA_GATE", raising=False)
        data = json.dumps({"tool_input": {"command": "gh pr create --title docs"}})
        mock_stdin.write(data)
        mock_stdin.seek(0)
        with patch.object(mock_stdin, "isatty", return_value=False):
            assert main() == 0

    @patch("invoke_routing_gates.check_qa_evidence", return_value=False)
    @patch("invoke_routing_gates.check_documentation_only", return_value=False)
    @patch("invoke_routing_gates.is_valid_project_root", return_value=True)
    @patch("invoke_routing_gates.sys.stdin", new_callable=StringIO)
    def test_denies_pr_without_qa_evidence(
        self,
        mock_stdin: StringIO,
        _mock_root: MagicMock,
        _mock_docs: MagicMock,
        _mock_qa: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.delenv("SKIP_QA_GATE", raising=False)
        data = json.dumps({"tool_input": {"command": "gh pr create --title test"}})
        mock_stdin.write(data)
        mock_stdin.seek(0)
        with patch.object(mock_stdin, "isatty", return_value=False):
            # Returns 0 with JSON deny decision (not exit 2)
            assert main() == 0
            captured = capsys.readouterr()
            output = json.loads(captured.out.strip())
            assert output["decision"] == "deny"
            assert "QA" in output["reason"]

    @patch("invoke_routing_gates.check_qa_evidence", return_value=True)
    @patch("invoke_routing_gates.check_documentation_only", return_value=False)
    @patch("invoke_routing_gates.is_valid_project_root", return_value=True)
    @patch("invoke_routing_gates.sys.stdin", new_callable=StringIO)
    def test_allows_pr_with_qa_evidence(
        self,
        mock_stdin: StringIO,
        _mock_root: MagicMock,
        _mock_docs: MagicMock,
        _mock_qa: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("SKIP_QA_GATE", raising=False)
        data = json.dumps({"tool_input": {"command": "gh pr create --title test"}})
        mock_stdin.write(data)
        mock_stdin.seek(0)
        with patch.object(mock_stdin, "isatty", return_value=False):
            assert main() == 0
