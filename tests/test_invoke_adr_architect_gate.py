"""Tests for invoke_adr_architect_gate.py PreToolUse hook."""

from __future__ import annotations

import json
import sys
import time
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add project root to path for hook imports
_project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_project_root / ".claude" / "hooks" / "PreToolUse"))

from invoke_adr_architect_gate import (  # noqa: E402
    check_architect_evidence,
    is_adr_file,
    main,
)


class TestIsADRFile:
    def test_matches_standard_adr_path(self) -> None:
        assert is_adr_file(".agents/architecture/ADR-042.md") is True

    def test_matches_docs_adr_path(self) -> None:
        assert is_adr_file("docs/architecture/ADR-001.md") is True

    def test_matches_nested_adr_path(self) -> None:
        assert is_adr_file("some/nested/path/ADR-999.md") is True

    def test_matches_case_insensitive(self) -> None:
        assert is_adr_file("docs/adr-001.md") is True

    def test_matches_with_suffix(self) -> None:
        assert is_adr_file("ADR-042-my-decision.md") is True

    def test_rejects_non_adr_file(self) -> None:
        assert is_adr_file("src/main.py") is False

    def test_rejects_readme(self) -> None:
        assert is_adr_file("README.md") is False

    def test_rejects_partial_match(self) -> None:
        assert is_adr_file("ADR-notes.txt") is False


class TestCheckArchitectEvidence:
    def test_complete_when_debate_log_in_analysis(self, tmp_path: Path) -> None:
        analysis_dir = tmp_path / ".agents" / "analysis"
        analysis_dir.mkdir(parents=True)
        debate_log = analysis_dir / "adr-debate-log.md"
        debate_log.write_text("debate content", encoding="utf-8")
        # Touch with recent mtime
        debate_log.touch()

        result = check_architect_evidence(str(tmp_path))
        assert result["complete"] is True
        assert "evidence" in result
        assert "debate" in result["evidence"].lower()

    def test_complete_when_debate_log_in_critique(self, tmp_path: Path) -> None:
        critique_dir = tmp_path / ".agents" / "critique"
        critique_dir.mkdir(parents=True)
        debate_log = critique_dir / "debate-123.md"
        debate_log.write_text("critique content", encoding="utf-8")
        debate_log.touch()

        result = check_architect_evidence(str(tmp_path))
        assert result["complete"] is True

    def test_complete_when_session_log_has_adr_review(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sessions_dir = tmp_path / ".agents" / "sessions"
        sessions_dir.mkdir(parents=True)
        from datetime import UTC, datetime

        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        session_log = sessions_dir / f"{today}-session-001.json"
        session_log.write_text('{"content": "/adr-review was invoked"}', encoding="utf-8")

        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
        result = check_architect_evidence(str(tmp_path))
        assert result["complete"] is True

    def test_complete_when_session_log_has_architect_agent(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sessions_dir = tmp_path / ".agents" / "sessions"
        sessions_dir.mkdir(parents=True)
        from datetime import UTC, datetime

        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        session_log = sessions_dir / f"{today}-session-001.json"
        session_log.write_text(
            '{"content": "subagent_type=\'architect\'"}',
            encoding="utf-8",
        )

        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
        result = check_architect_evidence(str(tmp_path))
        assert result["complete"] is True

    def test_incomplete_when_no_evidence(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sessions_dir = tmp_path / ".agents" / "sessions"
        sessions_dir.mkdir(parents=True)
        from datetime import UTC, datetime

        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        session_log = sessions_dir / f"{today}-session-001.json"
        session_log.write_text('{"content": "nothing relevant"}', encoding="utf-8")

        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
        result = check_architect_evidence(str(tmp_path))
        assert result["complete"] is False
        assert "reason" in result

    def test_ignores_old_debate_logs(self, tmp_path: Path) -> None:
        analysis_dir = tmp_path / ".agents" / "analysis"
        analysis_dir.mkdir(parents=True)
        debate_log = analysis_dir / "old-debate-log.md"
        debate_log.write_text("old debate", encoding="utf-8")
        # Set mtime to 2 days ago
        old_time = time.time() - 172800
        debate_log.touch()
        import os

        os.utime(debate_log, (old_time, old_time))

        result = check_architect_evidence(str(tmp_path))
        assert result["complete"] is False


class TestMainAllowPath:
    @patch("invoke_adr_architect_gate.sys.stdin")
    def test_allows_when_tty(self, mock_stdin: MagicMock) -> None:
        mock_stdin.isatty.return_value = True
        assert main() == 0

    @patch("invoke_adr_architect_gate.sys.stdin", new_callable=StringIO)
    def test_allows_non_edit_tools(self, mock_stdin: StringIO) -> None:
        data = json.dumps({"tool_name": "Read", "tool_input": {"file_path": "ADR-042.md"}})
        mock_stdin.write(data)
        mock_stdin.seek(0)
        with patch.object(mock_stdin, "isatty", return_value=False):
            assert main() == 0

    @patch("invoke_adr_architect_gate.sys.stdin", new_callable=StringIO)
    def test_allows_non_adr_files(self, mock_stdin: StringIO) -> None:
        data = json.dumps({"tool_name": "Edit", "tool_input": {"file_path": "src/main.py"}})
        mock_stdin.write(data)
        mock_stdin.seek(0)
        with patch.object(mock_stdin, "isatty", return_value=False):
            assert main() == 0

    @patch("invoke_adr_architect_gate.check_architect_evidence")
    @patch("invoke_adr_architect_gate.get_project_directory", return_value="/tmp/test")
    @patch("invoke_adr_architect_gate.sys.stdin", new_callable=StringIO)
    def test_allows_when_evidence_exists(
        self,
        mock_stdin: StringIO,
        _mock_project_dir: MagicMock,
        mock_evidence: MagicMock,
    ) -> None:
        mock_evidence.return_value = {"complete": True, "evidence": "debate log found"}
        data = json.dumps({"tool_name": "Edit", "tool_input": {"file_path": "ADR-042.md"}})
        mock_stdin.write(data)
        mock_stdin.seek(0)
        with patch.object(mock_stdin, "isatty", return_value=False):
            assert main() == 0


class TestMainBlockPath:
    @patch("invoke_adr_architect_gate.check_architect_evidence")
    @patch("invoke_adr_architect_gate.get_project_directory", return_value="/tmp/test")
    @patch("invoke_adr_architect_gate.sys.stdin", new_callable=StringIO)
    def test_blocks_edit_without_evidence(
        self,
        mock_stdin: StringIO,
        _mock_project_dir: MagicMock,
        mock_evidence: MagicMock,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        mock_evidence.return_value = {"complete": False, "reason": "No evidence"}
        data = json.dumps({"tool_name": "Edit", "tool_input": {"file_path": "ADR-042.md"}})
        mock_stdin.write(data)
        mock_stdin.seek(0)
        with patch.object(mock_stdin, "isatty", return_value=False):
            assert main() == 2
            captured = capsys.readouterr()
            assert "BLOCKED" in captured.out
            assert "architect" in captured.out.lower()

    @patch("invoke_adr_architect_gate.check_architect_evidence")
    @patch("invoke_adr_architect_gate.get_project_directory", return_value="/tmp/test")
    @patch("invoke_adr_architect_gate.sys.stdin", new_callable=StringIO)
    def test_blocks_write_without_evidence(
        self,
        mock_stdin: StringIO,
        _mock_project_dir: MagicMock,
        mock_evidence: MagicMock,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        mock_evidence.return_value = {"complete": False, "reason": "No evidence"}
        data = json.dumps(
            {"tool_name": "Write", "tool_input": {"file_path": ".agents/architecture/ADR-001.md"}}
        )
        mock_stdin.write(data)
        mock_stdin.seek(0)
        with patch.object(mock_stdin, "isatty", return_value=False):
            assert main() == 2

    @patch("invoke_adr_architect_gate.check_architect_evidence")
    @patch("invoke_adr_architect_gate.get_project_directory", return_value="/tmp/test")
    @patch("invoke_adr_architect_gate.sys.stdin", new_callable=StringIO)
    def test_blocks_nested_adr_path(
        self,
        mock_stdin: StringIO,
        _mock_project_dir: MagicMock,
        mock_evidence: MagicMock,
    ) -> None:
        mock_evidence.return_value = {"complete": False, "reason": "No evidence"}
        data = json.dumps(
            {"tool_name": "Edit", "tool_input": {"file_path": "docs/arch/ADR-042-decision.md"}}
        )
        mock_stdin.write(data)
        mock_stdin.seek(0)
        with patch.object(mock_stdin, "isatty", return_value=False):
            assert main() == 2


class TestMainFailOpen:
    @patch("invoke_adr_architect_gate.write_audit_log")
    @patch("invoke_adr_architect_gate.is_adr_file", side_effect=Exception("unexpected"))
    @patch("invoke_adr_architect_gate.sys.stdin", new_callable=StringIO)
    def test_failopen_on_infrastructure_error(
        self,
        mock_stdin: StringIO,
        _mock_adr: MagicMock,
        _mock_audit: MagicMock,
    ) -> None:
        data = json.dumps({"tool_name": "Edit", "tool_input": {"file_path": "ADR-042.md"}})
        mock_stdin.write(data)
        mock_stdin.seek(0)
        with patch.object(mock_stdin, "isatty", return_value=False):
            assert main() == 0

    @patch("invoke_adr_architect_gate.write_audit_log")
    @patch("invoke_adr_architect_gate.sys.stdin", new_callable=StringIO)
    def test_failopen_on_json_error(
        self,
        mock_stdin: StringIO,
        _mock_audit: MagicMock,
    ) -> None:
        mock_stdin.write("not valid json")
        mock_stdin.seek(0)
        with patch.object(mock_stdin, "isatty", return_value=False):
            assert main() == 0
