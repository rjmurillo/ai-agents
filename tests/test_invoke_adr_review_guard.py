"""Tests for invoke_adr_review_guard.py PreToolUse hook."""

from __future__ import annotations

import json
import sys
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add project root to path for hook imports
_project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_project_root / ".claude" / "hooks" / "PreToolUse"))

from invoke_adr_review_guard import (  # noqa: E402
    _is_gated_file,
    check_adr_review_evidence,
    get_staged_adr_changes,
    main,
)


class TestGetStagedADRChanges:
    @patch("invoke_adr_review_guard.subprocess.run")
    def test_returns_adr_files_only(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="src/main.py\n.agents/architecture/ADR-042.md\nREADME.md\n",
            stderr="",
        )
        result = get_staged_adr_changes()
        assert result == [".agents/architecture/ADR-042.md"]

    @patch("invoke_adr_review_guard.subprocess.run")
    def test_returns_empty_when_no_staged(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        result = get_staged_adr_changes()
        assert result == []

    @patch("invoke_adr_review_guard.subprocess.run")
    def test_raises_on_git_error(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="fatal: not a git repository",
        )
        with pytest.raises(RuntimeError, match="git diff --cached failed"):
            get_staged_adr_changes()

    @patch("invoke_adr_review_guard.subprocess.run")
    def test_matches_case_insensitive(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="docs/adr-001.md\n",
            stderr="",
        )
        result = get_staged_adr_changes()
        assert result == ["docs/adr-001.md"]

    @patch("invoke_adr_review_guard.subprocess.run")
    def test_returns_session_protocol(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="src/main.py\n.agents/SESSION-PROTOCOL.md\nREADME.md\n",
            stderr="",
        )
        result = get_staged_adr_changes()
        assert result == [".agents/SESSION-PROTOCOL.md"]

    @patch("invoke_adr_review_guard.subprocess.run")
    def test_returns_both_adr_and_session_protocol(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=".agents/architecture/ADR-042.md\n.agents/SESSION-PROTOCOL.md\n",
            stderr="",
        )
        result = get_staged_adr_changes()
        assert result == [
            ".agents/architecture/ADR-042.md",
            ".agents/SESSION-PROTOCOL.md",
        ]


class TestIsGatedFile:
    def test_matches_adr_file(self) -> None:
        assert _is_gated_file(".agents/architecture/ADR-042.md") is True

    def test_matches_session_protocol(self) -> None:
        assert _is_gated_file(".agents/SESSION-PROTOCOL.md") is True

    def test_rejects_unrelated_file(self) -> None:
        assert _is_gated_file("README.md") is False

    def test_rejects_partial_session_protocol(self) -> None:
        assert _is_gated_file("MY-SESSION-PROTOCOL.md.bak") is False


class TestTestADRReviewEvidence:
    def test_complete_when_evidence_and_debate_log(self, tmp_path: Path) -> None:
        log_file = tmp_path / "session.json"
        log_file.write_text("/adr-review was run", encoding="utf-8")

        analysis_dir = tmp_path / ".agents" / "analysis"
        analysis_dir.mkdir(parents=True)
        (analysis_dir / "adr-debate-log.md").write_text("debate", encoding="utf-8")

        result = check_adr_review_evidence(log_file, str(tmp_path))
        assert result["complete"] is True
        assert "evidence" in result

    def test_incomplete_when_no_evidence_in_log(self, tmp_path: Path) -> None:
        log_file = tmp_path / "session.json"
        log_file.write_text("nothing relevant here", encoding="utf-8")

        result = check_adr_review_evidence(log_file, str(tmp_path))
        assert result["complete"] is False
        assert "No adr-review evidence" in str(result["reason"])

    def test_incomplete_when_no_analysis_dir(self, tmp_path: Path) -> None:
        log_file = tmp_path / "session.json"
        log_file.write_text("/adr-review was run", encoding="utf-8")

        result = check_adr_review_evidence(log_file, str(tmp_path))
        assert result["complete"] is False
        assert "directory does not exist" in str(result["reason"])

    def test_incomplete_when_no_debate_logs(self, tmp_path: Path) -> None:
        log_file = tmp_path / "session.json"
        log_file.write_text("/adr-review was run", encoding="utf-8")

        analysis_dir = tmp_path / ".agents" / "analysis"
        analysis_dir.mkdir(parents=True)
        (analysis_dir / "other-file.md").write_text("not a debate", encoding="utf-8")

        result = check_adr_review_evidence(log_file, str(tmp_path))
        assert result["complete"] is False
        assert "no debate log artifact" in str(result["reason"])

    def test_handles_file_not_found(self, tmp_path: Path) -> None:
        missing_file = tmp_path / "nonexistent.json"
        result = check_adr_review_evidence(missing_file, str(tmp_path))
        assert result["complete"] is False
        assert "deleted" in str(result["reason"]).lower()

    def test_matches_consensus_pattern(self, tmp_path: Path) -> None:
        log_file = tmp_path / "session.json"
        log_file.write_text(
            "multi-agent consensus was reached on this ADR",
            encoding="utf-8",
        )

        analysis_dir = tmp_path / ".agents" / "analysis"
        analysis_dir.mkdir(parents=True)
        (analysis_dir / "debate-123.md").write_text("debate", encoding="utf-8")

        result = check_adr_review_evidence(log_file, str(tmp_path))
        assert result["complete"] is True


class TestMainAllowPath:
    @patch("invoke_adr_review_guard.sys.stdin")
    def test_allows_when_tty(self, mock_stdin: MagicMock) -> None:
        mock_stdin.isatty.return_value = True
        assert main() == 0

    @patch("invoke_adr_review_guard.sys.stdin", new_callable=StringIO)
    def test_allows_non_commit_commands(self, mock_stdin: StringIO) -> None:
        data = json.dumps({"tool_input": {"command": "git status"}})
        mock_stdin.write(data)
        mock_stdin.seek(0)
        with patch.object(mock_stdin, "isatty", return_value=False):
            assert main() == 0

    @patch("invoke_adr_review_guard.get_staged_adr_changes", return_value=[])
    @patch("invoke_adr_review_guard.sys.stdin", new_callable=StringIO)
    def test_allows_when_no_adr_changes(
        self,
        mock_stdin: StringIO,
        _mock_staged: MagicMock,
    ) -> None:
        data = json.dumps({"tool_input": {"command": "git commit -m test"}})
        mock_stdin.write(data)
        mock_stdin.seek(0)
        with patch.object(mock_stdin, "isatty", return_value=False):
            assert main() == 0


class TestMainBlockPath:
    @patch("invoke_adr_review_guard.get_today_session_log", return_value=None)
    @patch("invoke_adr_review_guard.get_project_directory", return_value="/tmp/test")
    @patch(
        "invoke_adr_review_guard.get_staged_adr_changes",
        return_value=["ADR-042.md"],
    )
    @patch("invoke_adr_review_guard.sys.stdin", new_callable=StringIO)
    def test_blocks_when_no_session_log(
        self,
        mock_stdin: StringIO,
        _mock_staged: MagicMock,
        _mock_project_dir: MagicMock,
        _mock_session_log: MagicMock,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        data = json.dumps({"tool_input": {"command": "git commit -m test"}})
        mock_stdin.write(data)
        mock_stdin.seek(0)
        with patch.object(mock_stdin, "isatty", return_value=False):
            assert main() == 2
            captured = capsys.readouterr()
            assert "BLOCKED" in captured.out

    @patch("invoke_adr_review_guard.check_adr_review_evidence")
    @patch("invoke_adr_review_guard.get_today_session_log")
    @patch("invoke_adr_review_guard.get_project_directory", return_value="/tmp/test")
    @patch(
        "invoke_adr_review_guard.get_staged_adr_changes",
        return_value=["ADR-042.md"],
    )
    @patch("invoke_adr_review_guard.sys.stdin", new_callable=StringIO)
    def test_blocks_when_no_evidence(
        self,
        mock_stdin: StringIO,
        _mock_staged: MagicMock,
        _mock_project_dir: MagicMock,
        mock_session_log: MagicMock,
        mock_evidence: MagicMock,
    ) -> None:
        mock_log = MagicMock()
        mock_log.name = "2026-02-12-session-1.json"
        mock_session_log.return_value = mock_log
        mock_evidence.return_value = {
            "complete": False,
            "reason": "No adr-review evidence in session log",
        }

        data = json.dumps({"tool_input": {"command": "git commit -m test"}})
        mock_stdin.write(data)
        mock_stdin.seek(0)
        with patch.object(mock_stdin, "isatty", return_value=False):
            assert main() == 2

    @patch("invoke_adr_review_guard.write_audit_log")
    @patch("invoke_adr_review_guard.get_staged_adr_changes")
    @patch("invoke_adr_review_guard.sys.stdin", new_callable=StringIO)
    def test_blocks_when_git_fails_failclosed(
        self,
        mock_stdin: StringIO,
        mock_staged: MagicMock,
        _mock_audit: MagicMock,
    ) -> None:
        mock_staged.side_effect = RuntimeError("git failed")
        data = json.dumps({"tool_input": {"command": "git commit -m test"}})
        mock_stdin.write(data)
        mock_stdin.seek(0)
        with patch.object(mock_stdin, "isatty", return_value=False):
            assert main() == 2


class TestMainFailOpen:
    @patch("invoke_adr_review_guard.write_audit_log")
    @patch("invoke_adr_review_guard.is_git_commit_command", side_effect=Exception("unexpected"))
    @patch("invoke_adr_review_guard.sys.stdin", new_callable=StringIO)
    def test_failopen_on_infrastructure_error(
        self,
        mock_stdin: StringIO,
        _mock_commit: MagicMock,
        _mock_audit: MagicMock,
    ) -> None:
        data = json.dumps({"tool_input": {"command": "git commit -m test"}})
        mock_stdin.write(data)
        mock_stdin.seek(0)
        with patch.object(mock_stdin, "isatty", return_value=False):
            assert main() == 0
