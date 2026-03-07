"""Tests for invoke_adr_review_guard.py Claude Code PreToolUse hook."""

import io
import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Add hooks directory to path for import
HOOKS_DIR = Path(__file__).resolve().parents[2] / ".claude" / "hooks" / "PreToolUse"
sys.path.insert(0, str(HOOKS_DIR))

import invoke_adr_review_guard  # noqa: E402


class TestGetStagedADRChanges:
    """Tests for get_staged_adr_changes."""

    def test_returns_adr_files(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0,
                stdout="src/main.py\n.agents/architecture/ADR-001.md\nREADME.md\n",
                stderr=""
            )
            result = invoke_adr_review_guard.get_staged_adr_changes()
            assert result == [".agents/architecture/ADR-001.md"]

    def test_returns_empty_for_no_staged(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr=""
            )
            result = invoke_adr_review_guard.get_staged_adr_changes()
            assert result == []

    def test_raises_on_git_error(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=1, stdout="", stderr="fatal error"
            )
            with pytest.raises(RuntimeError, match="git diff --cached failed"):
                invoke_adr_review_guard.get_staged_adr_changes()

    def test_case_insensitive_adr_match(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0,
                stdout="docs/adr-042.md\n",
                stderr=""
            )
            result = invoke_adr_review_guard.get_staged_adr_changes()
            assert result == ["docs/adr-042.md"]

    def test_multiple_adr_files(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0,
                stdout="ADR-001.md\nADR-002.md\nsrc/code.py\n",
                stderr=""
            )
            result = invoke_adr_review_guard.get_staged_adr_changes()
            assert len(result) == 2


class TestCheckADRReviewEvidence:
    """Tests for check_adr_review_evidence."""

    def test_finds_adr_review_invocation(self, tmp_path):
        session_log = tmp_path / "session.json"
        session_log.write_text("Ran /adr-review for ADR-042")
        analysis_dir = tmp_path / ".agents" / "analysis"
        analysis_dir.mkdir(parents=True)
        (analysis_dir / "adr-042-debate.md").write_text("debate")
        result = invoke_adr_review_guard.check_adr_review_evidence(
            session_log, str(tmp_path)
        )
        assert result["complete"] is True

    def test_no_evidence_found(self, tmp_path):
        session_log = tmp_path / "session.json"
        session_log.write_text("Just a normal session")
        result = invoke_adr_review_guard.check_adr_review_evidence(
            session_log, str(tmp_path)
        )
        assert result["complete"] is False
        assert "No adr-review evidence" in result["reason"]

    def test_evidence_but_no_debate_log(self, tmp_path):
        session_log = tmp_path / "session.json"
        session_log.write_text("Ran /adr-review for ADR-042")
        analysis_dir = tmp_path / ".agents" / "analysis"
        analysis_dir.mkdir(parents=True)
        # No debate log files
        result = invoke_adr_review_guard.check_adr_review_evidence(
            session_log, str(tmp_path)
        )
        assert result["complete"] is False
        assert "no debate log artifact found" in result["reason"]

    def test_evidence_but_no_analysis_dir(self, tmp_path):
        session_log = tmp_path / "session.json"
        session_log.write_text("Ran /adr-review for ADR-042")
        result = invoke_adr_review_guard.check_adr_review_evidence(
            session_log, str(tmp_path)
        )
        assert result["complete"] is False
        assert "does not exist" in result["reason"]

    def test_permission_error(self, tmp_path):
        session_log = tmp_path / "session.json"
        session_log.write_text("content")
        os.chmod(session_log, 0o000)
        try:
            result = invoke_adr_review_guard.check_adr_review_evidence(
                session_log, str(tmp_path)
            )
            assert result["complete"] is False
            assert "locked" in result["reason"] or "permissions" in result["reason"]
        finally:
            os.chmod(session_log, 0o644)

    def test_file_not_found(self, tmp_path):
        result = invoke_adr_review_guard.check_adr_review_evidence(
            tmp_path / "missing.json", str(tmp_path)
        )
        assert result["complete"] is False
        assert "deleted" in result["reason"]

    def test_adr_review_skill_pattern(self, tmp_path):
        session_log = tmp_path / "session.json"
        session_log.write_text("Used adr-review skill for changes")
        analysis_dir = tmp_path / ".agents" / "analysis"
        analysis_dir.mkdir(parents=True)
        (analysis_dir / "debate-notes.md").write_text("notes")
        result = invoke_adr_review_guard.check_adr_review_evidence(
            session_log, str(tmp_path)
        )
        assert result["complete"] is True

    def test_adr_review_protocol_pattern(self, tmp_path):
        session_log = tmp_path / "session.json"
        session_log.write_text("## ADR Review Protocol\nFindings...")
        analysis_dir = tmp_path / ".agents" / "analysis"
        analysis_dir.mkdir(parents=True)
        (analysis_dir / "debate-log.md").write_text("log")
        result = invoke_adr_review_guard.check_adr_review_evidence(
            session_log, str(tmp_path)
        )
        assert result["complete"] is True

    def test_value_error_returns_incomplete(self, tmp_path):
        session_log = tmp_path / "session.json"
        session_log.write_text("Ran /adr-review")
        analysis_dir = tmp_path / ".agents" / "analysis"
        analysis_dir.mkdir(parents=True)
        (analysis_dir / "debate-log.md").write_text("notes")

        with patch.object(Path, "read_text", side_effect=ValueError("bad value")):
            result = invoke_adr_review_guard.check_adr_review_evidence(
                session_log, str(tmp_path)
            )
        assert result["complete"] is False
        assert "ValueError" in result["reason"]

    def test_oserror_returns_incomplete(self, tmp_path):
        session_log = tmp_path / "session.json"
        session_log.write_text("Ran /adr-review")

        with patch.object(Path, "read_text", side_effect=OSError("io error")):
            result = invoke_adr_review_guard.check_adr_review_evidence(
                session_log, str(tmp_path)
            )
        assert result["complete"] is False
        assert "Error reading" in result["reason"]


class TestWriteAuditLog:
    """Tests for write_audit_log."""

    def test_no_crash_on_call(self):
        invoke_adr_review_guard.write_audit_log("test message")

    def test_prints_critical_on_oserror(self, capsys):
        with patch("builtins.open", side_effect=OSError("write failed")):
            invoke_adr_review_guard.write_audit_log("test msg")
        captured = capsys.readouterr()
        assert "CRITICAL" in captured.err


class TestMain:
    """Tests for main() entry point."""

    @pytest.fixture(autouse=True)
    def _no_consumer_repo_skip(self):
        with patch("invoke_adr_review_guard.skip_if_consumer_repo", return_value=False):
            yield

    def test_allows_non_commit_command(self, monkeypatch):
        input_data = json.dumps({
            "tool_input": {"command": "git push"},
        })
        monkeypatch.setattr("sys.stdin", io.StringIO(input_data))
        assert invoke_adr_review_guard.main() == 0

    def test_allows_empty_input(self, monkeypatch):
        monkeypatch.setattr("sys.stdin", io.StringIO(""))
        assert invoke_adr_review_guard.main() == 0

    @patch("invoke_adr_review_guard.get_staged_adr_changes", return_value=[])
    def test_allows_commit_without_adr_changes(self, mock_changes, monkeypatch):
        input_data = json.dumps({
            "tool_input": {"command": "git commit -m 'fix'"},
        })
        monkeypatch.setattr("sys.stdin", io.StringIO(input_data))
        assert invoke_adr_review_guard.main() == 0

    @patch("invoke_adr_review_guard.get_today_session_log", return_value=None)
    @patch("invoke_adr_review_guard.get_project_directory", return_value="/project")
    @patch("invoke_adr_review_guard.get_staged_adr_changes", return_value=["ADR-001.md"])
    def test_blocks_adr_commit_without_session_log(
        self, mock_changes, mock_proj, mock_session,
        monkeypatch, capsys
    ):
        input_data = json.dumps({
            "tool_input": {"command": "git commit -m 'update adr'"},
        })
        monkeypatch.setattr("sys.stdin", io.StringIO(input_data))
        result = invoke_adr_review_guard.main()
        assert result == 2
        captured = capsys.readouterr()
        assert "BLOCKED" in captured.out

    @patch("invoke_adr_review_guard.check_adr_review_evidence")
    @patch("invoke_adr_review_guard.get_today_session_log")
    @patch("invoke_adr_review_guard.get_project_directory", return_value="/project")
    @patch("invoke_adr_review_guard.get_staged_adr_changes", return_value=["ADR-001.md"])
    def test_blocks_adr_commit_without_evidence(
        self, mock_changes, mock_proj, mock_session, mock_evidence,
        monkeypatch, tmp_path
    ):
        session_log = tmp_path / "session.json"
        session_log.write_text("{}")
        mock_session.return_value = session_log
        mock_evidence.return_value = {"complete": False, "reason": "No evidence"}
        input_data = json.dumps({
            "tool_input": {"command": "git commit -m 'update adr'"},
        })
        monkeypatch.setattr("sys.stdin", io.StringIO(input_data))
        result = invoke_adr_review_guard.main()
        assert result == 2

    @patch("invoke_adr_review_guard.check_adr_review_evidence")
    @patch("invoke_adr_review_guard.get_today_session_log")
    @patch("invoke_adr_review_guard.get_project_directory", return_value="/project")
    @patch("invoke_adr_review_guard.get_staged_adr_changes", return_value=["ADR-001.md"])
    def test_allows_adr_commit_with_evidence(
        self, mock_changes, mock_proj, mock_session, mock_evidence,
        monkeypatch, tmp_path
    ):
        session_log = tmp_path / "session.json"
        session_log.write_text("{}")
        mock_session.return_value = session_log
        mock_evidence.return_value = {"complete": True, "evidence": "found"}
        input_data = json.dumps({
            "tool_input": {"command": "git commit -m 'update adr'"},
        })
        monkeypatch.setattr("sys.stdin", io.StringIO(input_data))
        assert invoke_adr_review_guard.main() == 0

    @patch("invoke_adr_review_guard.get_staged_adr_changes", side_effect=RuntimeError("git failed"))
    def test_blocks_on_git_error_fail_closed(self, mock_changes, monkeypatch):
        input_data = json.dumps({
            "tool_input": {"command": "git commit -m 'update'"},
        })
        monkeypatch.setattr("sys.stdin", io.StringIO(input_data))
        assert invoke_adr_review_guard.main() == 2

    def test_fails_open_on_unexpected_error(self, monkeypatch):
        monkeypatch.setattr("sys.stdin", io.StringIO("not valid json at all {{{"))
        # Should fail-open (exit 0) on JSON parse error in outer try
        assert invoke_adr_review_guard.main() == 0

    def test_allows_missing_tool_input(self, monkeypatch):
        input_data = json.dumps({"cwd": "/tmp"})
        monkeypatch.setattr("sys.stdin", io.StringIO(input_data))
        assert invoke_adr_review_guard.main() == 0

    def test_allows_non_dict_tool_input(self, monkeypatch):
        input_data = json.dumps({"tool_input": "string"})
        monkeypatch.setattr("sys.stdin", io.StringIO(input_data))
        assert invoke_adr_review_guard.main() == 0

    def test_stdin_tty_returns_zero(self, monkeypatch):
        """When stdin is tty, main returns 0 (fail-open)."""
        mock_stdin = io.StringIO("")
        mock_stdin.isatty = lambda: True
        monkeypatch.setattr("sys.stdin", mock_stdin)
        assert invoke_adr_review_guard.main() == 0


class TestModuleAsScript:
    """Test that the hook can be executed as a script via __main__."""

    def test_adr_review_guard_as_script(self):
        import subprocess

        hook_path = str(
            Path(__file__).resolve().parents[2]
            / ".claude" / "hooks" / "PreToolUse" / "invoke_adr_review_guard.py"
        )
        result = subprocess.run(
            ["python3", hook_path],
            input='{"tool_input": {"command": "git push"}}',
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0

    def test_main_guard_via_runpy(self, monkeypatch):
        """Cover the sys.exit(main()) line via runpy in-process execution."""
        import runpy

        hook_path = str(
            Path(__file__).resolve().parents[2]
            / ".claude" / "hooks" / "PreToolUse" / "invoke_adr_review_guard.py"
        )
        monkeypatch.setattr("sys.stdin", io.StringIO(""))
        with pytest.raises(SystemExit) as exc_info:
            runpy.run_path(hook_path, run_name="__main__")
        assert exc_info.value.code == 0
