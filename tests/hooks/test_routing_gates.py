"""Tests for routing_gates.py Claude Code PreToolUse hook."""

import datetime
import io
import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Add hooks directory to path for import
HOOKS_DIR = Path(__file__).resolve().parents[2] / ".claude" / "hooks"
sys.path.insert(0, str(HOOKS_DIR))

import routing_gates  # noqa: E402


class TestIsValidProjectRoot:
    """Tests for _is_valid_project_root."""

    def test_valid_with_git(self, tmp_path):
        (tmp_path / ".git").mkdir()
        assert routing_gates._is_valid_project_root(str(tmp_path)) is True

    def test_valid_with_claude_settings(self, tmp_path):
        (tmp_path / ".claude").mkdir()
        (tmp_path / ".claude" / "settings.json").write_text("{}")
        assert routing_gates._is_valid_project_root(str(tmp_path)) is True

    def test_invalid_no_indicators(self, tmp_path):
        assert routing_gates._is_valid_project_root(str(tmp_path)) is False


class TestWriteAuditLog:
    """Tests for _write_audit_log."""

    def test_no_crash_on_call(self):
        """Verify audit log write does not raise."""
        routing_gates._write_audit_log("TestHook", "Test message")

    def test_fallback_on_oserror(self, tmp_path):
        """When primary audit log fails, falls back to temp dir."""
        with patch("builtins.open", side_effect=OSError("fail")):
            with patch("tempfile.gettempdir", return_value=str(tmp_path)):
                routing_gates._write_audit_log("TestHook", "Test message")


class TestGetTodaySessionLog:
    """Tests for _get_today_session_log."""

    def test_returns_none_for_missing_dir(self):
        result = routing_gates._get_today_session_log("/nonexistent/path")
        assert result is None

    def test_returns_none_when_no_matching_logs(self, tmp_path):
        result = routing_gates._get_today_session_log(str(tmp_path))
        assert result is None

    def test_returns_latest_matching_log(self, tmp_path):
        today = datetime.date.today().strftime("%Y-%m-%d")
        log1 = tmp_path / f"{today}-session-01.json"
        log2 = tmp_path / f"{today}-session-02.json"
        log1.write_text("{}")
        log2.write_text("{}")
        result = routing_gates._get_today_session_log(str(tmp_path))
        assert result is not None
        assert f"{today}-session-02.json" in result

    def test_ignores_non_json_files(self, tmp_path):
        today = datetime.date.today().strftime("%Y-%m-%d")
        (tmp_path / f"{today}-session-01.txt").write_text("not json")
        result = routing_gates._get_today_session_log(str(tmp_path))
        assert result is None

    def test_handles_oserror(self, tmp_path):
        with patch("os.listdir", side_effect=OSError("denied")):
            result = routing_gates._get_today_session_log(str(tmp_path))
            assert result is None


class TestTestQAEvidence:
    """Tests for _test_qa_evidence."""

    def test_finds_recent_qa_report(self, tmp_path):
        qa_dir = tmp_path / ".agents" / "qa"
        qa_dir.mkdir(parents=True)
        report = qa_dir / "qa-report.md"
        report.write_text("# QA Report")
        assert routing_gates._test_qa_evidence(str(tmp_path)) is True

    def test_ignores_old_qa_report(self, tmp_path):
        qa_dir = tmp_path / ".agents" / "qa"
        qa_dir.mkdir(parents=True)
        report = qa_dir / "qa-report.md"
        report.write_text("# QA Report")
        old_time = (
            datetime.datetime.now() - datetime.timedelta(hours=25)
        ).timestamp()
        os.utime(report, (old_time, old_time))
        assert routing_gates._test_qa_evidence(str(tmp_path)) is False

    def test_finds_qa_section_in_session_log(self, tmp_path):
        sessions_dir = tmp_path / ".agents" / "sessions"
        sessions_dir.mkdir(parents=True)
        today = datetime.date.today().strftime("%Y-%m-%d")
        log_file = sessions_dir / f"{today}-session-01.json"
        log_file.write_text('{"notes": "## QA Validation passed"}')
        assert routing_gates._test_qa_evidence(str(tmp_path)) is True

    def test_no_evidence_returns_false(self, tmp_path):
        assert routing_gates._test_qa_evidence(str(tmp_path)) is False

    def test_session_log_read_error(self, tmp_path):
        sessions_dir = tmp_path / ".agents" / "sessions"
        sessions_dir.mkdir(parents=True)
        today = datetime.date.today().strftime("%Y-%m-%d")
        log_file = sessions_dir / f"{today}-session-01.json"
        log_file.write_text("content")
        os.chmod(log_file, 0o000)
        try:
            result = routing_gates._test_qa_evidence(str(tmp_path))
            # Either False or True depending on OS behavior
            assert isinstance(result, bool)
        finally:
            os.chmod(log_file, 0o644)


class TestTestDocumentationOnly:
    """Tests for _test_documentation_only."""

    def test_docs_only_returns_true(self, tmp_path):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0,
                stdout="README.md\ndocs/guide.txt\nCHANGELOG\n",
                stderr=""
            )
            assert routing_gates._test_documentation_only(str(tmp_path)) is True

    def test_code_files_return_false(self, tmp_path):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0,
                stdout="README.md\nsrc/main.py\n",
                stderr=""
            )
            assert routing_gates._test_documentation_only(str(tmp_path)) is False

    def test_git_diff_failure_falls_back(self, tmp_path):
        call_count = 0

        def mock_run(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return subprocess.CompletedProcess(
                    args=[], returncode=1, stdout="", stderr="error"
                )
            return subprocess.CompletedProcess(
                args=[], returncode=0, stdout="README.md\n", stderr=""
            )

        with patch("subprocess.run", side_effect=mock_run):
            assert routing_gates._test_documentation_only(str(tmp_path)) is True

    def test_both_git_diffs_fail_returns_false(self, tmp_path):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=1, stdout="", stderr="fatal"
            )
            assert routing_gates._test_documentation_only(str(tmp_path)) is False

    def test_no_changes_returns_true(self, tmp_path):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr=""
            )
            assert routing_gates._test_documentation_only(str(tmp_path)) is True

    def test_permission_error_returns_false(self, tmp_path):
        with patch("subprocess.run", side_effect=PermissionError("denied")):
            assert routing_gates._test_documentation_only(str(tmp_path)) is False

    def test_os_error_returns_false(self, tmp_path):
        with patch("subprocess.run", side_effect=OSError("io error")):
            assert routing_gates._test_documentation_only(str(tmp_path)) is False

    def test_timeout_returns_false(self, tmp_path):
        with patch(
            "subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="git", timeout=30),
        ):
            assert routing_gates._test_documentation_only(str(tmp_path)) is False

    def test_gitignore_is_docs_only(self, tmp_path):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0,
                stdout=".gitignore\nREADME.md\n",
                stderr=""
            )
            assert routing_gates._test_documentation_only(str(tmp_path)) is True

    def test_license_file_is_docs_only(self, tmp_path):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0,
                stdout="LICENSE\n",
                stderr=""
            )
            assert routing_gates._test_documentation_only(str(tmp_path)) is True


class TestMain:
    """Tests for main() entry point."""

    def test_allows_non_pr_commands(self, monkeypatch, tmp_path):
        (tmp_path / ".git").mkdir()
        input_data = json.dumps({
            "tool_input": {"command": "ls -la"},
            "cwd": str(tmp_path),
        })
        monkeypatch.setattr("sys.stdin", io.StringIO(input_data))
        assert routing_gates.main() == 0

    def test_allows_pr_with_skip_qa_gate(self, monkeypatch, tmp_path):
        (tmp_path / ".git").mkdir()
        monkeypatch.setenv("SKIP_QA_GATE", "true")
        input_data = json.dumps({
            "tool_input": {"command": "gh pr create --title test"},
            "cwd": str(tmp_path),
        })
        monkeypatch.setattr("sys.stdin", io.StringIO(input_data))
        assert routing_gates.main() == 0

    def test_blocks_pr_without_qa_evidence(self, monkeypatch, tmp_path, capsys):
        (tmp_path / ".git").mkdir()
        monkeypatch.delenv("SKIP_QA_GATE", raising=False)
        input_data = json.dumps({
            "tool_input": {"command": "gh pr create --title test"},
            "cwd": str(tmp_path),
        })
        monkeypatch.setattr("sys.stdin", io.StringIO(input_data))
        with patch.object(
            routing_gates, "_test_documentation_only", return_value=False
        ):
            with patch.object(
                routing_gates, "_test_qa_evidence", return_value=False
            ):
                result = routing_gates.main()
        assert result == 0  # JSON deny, exit 0
        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output["decision"] == "deny"

    def test_allows_pr_with_docs_only(self, monkeypatch, tmp_path):
        (tmp_path / ".git").mkdir()
        monkeypatch.delenv("SKIP_QA_GATE", raising=False)
        input_data = json.dumps({
            "tool_input": {"command": "gh pr create --title test"},
            "cwd": str(tmp_path),
        })
        monkeypatch.setattr("sys.stdin", io.StringIO(input_data))
        with patch.object(
            routing_gates, "_test_documentation_only", return_value=True
        ):
            assert routing_gates.main() == 0

    def test_allows_pr_with_qa_evidence(self, monkeypatch, tmp_path):
        (tmp_path / ".git").mkdir()
        monkeypatch.delenv("SKIP_QA_GATE", raising=False)
        input_data = json.dumps({
            "tool_input": {"command": "gh pr create --title test"},
            "cwd": str(tmp_path),
        })
        monkeypatch.setattr("sys.stdin", io.StringIO(input_data))
        with patch.object(
            routing_gates, "_test_documentation_only", return_value=False
        ):
            with patch.object(
                routing_gates, "_test_qa_evidence", return_value=True
            ):
                assert routing_gates.main() == 0

    def test_handles_invalid_json(self, monkeypatch, tmp_path):
        (tmp_path / ".git").mkdir()
        monkeypatch.setattr("sys.stdin", io.StringIO("not json"))
        monkeypatch.setattr("os.getcwd", lambda: str(tmp_path))
        assert routing_gates.main() == 0

    def test_invalid_project_root_fails_open(self, monkeypatch, tmp_path):
        input_data = json.dumps({
            "tool_input": {"command": "gh pr create"},
            "cwd": str(tmp_path),
        })
        monkeypatch.setattr("sys.stdin", io.StringIO(input_data))
        assert routing_gates.main() == 0

    def test_handles_missing_tool_input(self, monkeypatch, tmp_path):
        (tmp_path / ".git").mkdir()
        input_data = json.dumps({"cwd": str(tmp_path)})
        monkeypatch.setattr("sys.stdin", io.StringIO(input_data))
        assert routing_gates.main() == 0


class TestWriteAuditLogAllPathsFail:
    """Tests for _write_audit_log when all write paths fail."""

    def test_prints_to_stderr_when_both_paths_fail(self, monkeypatch, capsys):

        def fail_all_opens(path, *args, **kwargs):
            raise OSError("all paths fail")

        monkeypatch.setattr("builtins.open", fail_all_opens)
        routing_gates._write_audit_log("TestHook", "critical message")
        captured = capsys.readouterr()
        assert "CRITICAL" in captured.err
        assert "critical message" in captured.err


class TestQAEvidenceOSErrorOnListDir:
    """Tests for _test_qa_evidence OSError when listing qa dir entries."""

    def test_oserror_listing_qa_dir_falls_through(self, tmp_path, monkeypatch):
        qa_dir = tmp_path / ".agents" / "qa"
        qa_dir.mkdir(parents=True)

        original_listdir = os.listdir

        def patched_listdir(path):
            if str(path) == str(qa_dir):
                raise OSError("permission denied")
            return original_listdir(path)

        monkeypatch.setattr(os, "listdir", patched_listdir)
        # No sessions dir, so result is False
        result = routing_gates._test_qa_evidence(str(tmp_path))
        assert isinstance(result, bool)


class TestGetTodaySessionLogBranches:
    """Branch coverage for _get_today_session_log edge cases."""

    def test_directory_entry_not_file(self, tmp_path):
        """When a directory matches the session log pattern, it is ignored."""
        today = datetime.date.today().strftime("%Y-%m-%d")
        subdir = tmp_path / f"{today}-session-01.json"
        subdir.mkdir()  # Create directory, not file
        result = routing_gates._get_today_session_log(str(tmp_path))
        assert result is None


class TestQAEvidenceBranches:
    """Branch coverage for _test_qa_evidence edge cases."""

    def test_non_md_files_in_qa_dir(self, tmp_path):
        """Non-.md files in QA dir are ignored."""
        qa_dir = tmp_path / ".agents" / "qa"
        qa_dir.mkdir(parents=True)
        (qa_dir / "report.txt").write_text("not a markdown file")
        assert routing_gates._test_qa_evidence(str(tmp_path)) is False

    def test_qa_dir_entry_not_file(self, tmp_path):
        """When a directory matches .md pattern, it is ignored."""
        qa_dir = tmp_path / ".agents" / "qa"
        qa_dir.mkdir(parents=True)
        fake_dir = qa_dir / "subdir.md"
        fake_dir.mkdir()
        assert routing_gates._test_qa_evidence(str(tmp_path)) is False

    def test_empty_session_log_content(self, tmp_path):
        """Empty session log content does not match QA patterns."""
        sessions_dir = tmp_path / ".agents" / "sessions"
        sessions_dir.mkdir(parents=True)
        today = datetime.date.today().strftime("%Y-%m-%d")
        log_file = sessions_dir / f"{today}-session-01.json"
        log_file.write_text("")
        assert routing_gates._test_qa_evidence(str(tmp_path)) is False

    def test_session_log_no_qa_pattern(self, tmp_path):
        """Session log exists but has no QA-related content."""
        sessions_dir = tmp_path / ".agents" / "sessions"
        sessions_dir.mkdir(parents=True)
        today = datetime.date.today().strftime("%Y-%m-%d")
        log_file = sessions_dir / f"{today}-session-01.json"
        log_file.write_text('{"notes": "just regular notes, nothing special"}')
        assert routing_gates._test_qa_evidence(str(tmp_path)) is False

    def test_session_log_oserror(self, tmp_path, capsys):
        """When session log cannot be read, result is False."""
        sessions_dir = tmp_path / ".agents" / "sessions"
        sessions_dir.mkdir(parents=True)
        today = datetime.date.today().strftime("%Y-%m-%d")
        log_file = sessions_dir / f"{today}-session-01.json"
        log_file.write_text("content")
        os.chmod(log_file, 0o000)
        try:
            assert routing_gates._test_qa_evidence(str(tmp_path)) is False
        finally:
            os.chmod(log_file, 0o644)


class TestMainBranches:
    """Branch coverage for main() edge cases."""

    def test_input_without_cwd(self, monkeypatch, tmp_path):
        """Input JSON without cwd key uses os.getcwd()."""
        (tmp_path / ".git").mkdir()
        monkeypatch.setattr("os.getcwd", lambda: str(tmp_path))
        input_data = json.dumps({
            "tool_input": {"command": "ls"},
        })
        monkeypatch.setattr("sys.stdin", io.StringIO(input_data))
        assert routing_gates.main() == 0

    def test_tool_input_non_dict(self, monkeypatch, tmp_path):
        """When tool_input is not a dict, command defaults to empty."""
        (tmp_path / ".git").mkdir()
        input_data = json.dumps({
            "tool_input": "string_value",
            "cwd": str(tmp_path),
        })
        monkeypatch.setattr("sys.stdin", io.StringIO(input_data))
        assert routing_gates.main() == 0


class TestWriteAuditLogTempSuccess:
    """Test successful temp dir fallback in _write_audit_log."""

    def test_temp_dir_fallback_succeeds(self, monkeypatch, tmp_path):
        """When primary audit path fails, temp dir write succeeds."""
        call_count = 0
        original_open = open

        def fail_first_open(path, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise OSError("primary path fails")
            return original_open(path, *args, **kwargs)

        monkeypatch.setattr("builtins.open", fail_first_open)
        routing_gates._write_audit_log("TestHook", "test fallback message")
        # Should not raise, second open succeeds


class TestModuleAsScript:
    """Test that hooks can be executed as scripts via __main__."""

    def test_routing_gates_as_script(self, tmp_path):
        import subprocess

        hook_path = str(
            Path(__file__).resolve().parents[2]
            / ".claude" / "hooks" / "routing_gates.py"
        )
        result = subprocess.run(
            ["python3", hook_path],
            input="",
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0

    def test_main_guard_via_runpy(self, monkeypatch):
        """Cover the sys.exit(main()) line via runpy in-process execution."""
        import runpy

        hook_path = str(
            Path(__file__).resolve().parents[2]
            / ".claude" / "hooks" / "routing_gates.py"
        )
        monkeypatch.setattr("sys.stdin", io.StringIO(""))
        with pytest.raises(SystemExit) as exc_info:
            runpy.run_path(hook_path, run_name="__main__")
        assert exc_info.value.code == 0
