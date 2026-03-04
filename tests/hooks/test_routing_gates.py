"""Tests for invoke_routing_gates.py Claude Code PreToolUse hook."""

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

import invoke_routing_gates  # noqa: E402


class TestWriteAuditLog:
    """Tests for write_audit_log."""

    def test_no_crash_on_call(self):
        """Verify audit log write does not raise."""
        invoke_routing_gates.write_audit_log("TestHook", "Test message")

    def test_fallback_on_oserror(self, tmp_path):
        """When primary audit log fails, falls back to temp dir."""
        with patch("builtins.open", side_effect=OSError("fail")):
            with patch("tempfile.gettempdir", return_value=str(tmp_path)):
                invoke_routing_gates.write_audit_log("TestHook", "Test message")


class TestCheckQAEvidence:
    """Tests for check_qa_evidence."""

    def test_finds_recent_qa_report(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        qa_dir = tmp_path / ".agents" / "qa"
        qa_dir.mkdir(parents=True)
        report = qa_dir / "qa-report.md"
        report.write_text("# QA Report")
        assert invoke_routing_gates.check_qa_evidence() is True

    def test_no_evidence_returns_false(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert invoke_routing_gates.check_qa_evidence() is False


class TestCheckDocumentationOnly:
    """Tests for check_documentation_only."""

    def test_docs_only_returns_true(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0,
                stdout="README.md\ndocs/guide.txt\nCHANGELOG\n",
                stderr=""
            )
            assert invoke_routing_gates.check_documentation_only() is True

    def test_code_files_return_false(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0,
                stdout="README.md\nsrc/main.py\n",
                stderr=""
            )
            assert invoke_routing_gates.check_documentation_only() is False

    def test_git_diff_failure_falls_back(self):
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
            assert invoke_routing_gates.check_documentation_only() is True

    def test_both_git_diffs_fail_returns_false(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=1, stdout="", stderr="fatal"
            )
            assert invoke_routing_gates.check_documentation_only() is False

    def test_no_changes_returns_true(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr=""
            )
            assert invoke_routing_gates.check_documentation_only() is True

    def test_permission_error_returns_false(self):
        with patch("subprocess.run", side_effect=PermissionError("denied")):
            assert invoke_routing_gates.check_documentation_only() is False

    def test_os_error_returns_false(self):
        with patch("subprocess.run", side_effect=OSError("io error")):
            assert invoke_routing_gates.check_documentation_only() is False

    def test_timeout_returns_false(self):
        with patch(
            "subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="git", timeout=30),
        ):
            assert invoke_routing_gates.check_documentation_only() is False

    def test_gitignore_is_docs_only(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0,
                stdout=".gitignore\nREADME.md\n",
                stderr=""
            )
            assert invoke_routing_gates.check_documentation_only() is True

    def test_license_file_is_docs_only(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0,
                stdout="LICENSE\n",
                stderr=""
            )
            assert invoke_routing_gates.check_documentation_only() is True


class TestIsValidProjectRoot:
    """Tests for is_valid_project_root."""

    def test_valid_with_git(self, tmp_path, monkeypatch):
        (tmp_path / ".git").mkdir()
        monkeypatch.chdir(tmp_path)
        assert invoke_routing_gates.is_valid_project_root() is True

    def test_valid_with_claude_settings(self, tmp_path, monkeypatch):
        (tmp_path / ".claude").mkdir()
        (tmp_path / ".claude" / "settings.json").write_text("{}")
        monkeypatch.chdir(tmp_path)
        assert invoke_routing_gates.is_valid_project_root() is True

    def test_invalid_no_indicators(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert invoke_routing_gates.is_valid_project_root() is False


class TestMain:
    """Tests for main() entry point."""

    @patch("invoke_routing_gates.skip_if_consumer_repo", return_value=False)
    @patch("invoke_routing_gates.is_valid_project_root", return_value=True)
    def test_allows_non_pr_commands(self, mock_valid, mock_skip, monkeypatch, tmp_path):
        (tmp_path / ".agents" / "sessions").mkdir(parents=True)
        monkeypatch.chdir(tmp_path)
        input_data = json.dumps({
            "tool_input": {"command": "ls -la"},
        })
        monkeypatch.setattr("sys.stdin", io.StringIO(input_data))
        assert invoke_routing_gates.main() == 0

    @patch("invoke_routing_gates.skip_if_consumer_repo", return_value=False)
    @patch("invoke_routing_gates.is_valid_project_root", return_value=True)
    def test_allows_pr_with_skip_qa_gate(self, mock_valid, mock_skip, monkeypatch, tmp_path):
        (tmp_path / ".agents" / "sessions").mkdir(parents=True)
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("SKIP_QA_GATE", "true")
        input_data = json.dumps({
            "tool_input": {"command": "gh pr create --title test"},
        })
        monkeypatch.setattr("sys.stdin", io.StringIO(input_data))
        assert invoke_routing_gates.main() == 0

    @patch("invoke_routing_gates.skip_if_consumer_repo", return_value=False)
    @patch("invoke_routing_gates.is_valid_project_root", return_value=True)
    @patch("invoke_routing_gates.check_qa_evidence", return_value=False)
    @patch("invoke_routing_gates.check_documentation_only", return_value=False)
    def test_blocks_pr_without_qa_evidence(
        self, mock_doc, mock_qa, mock_valid, mock_skip, monkeypatch, tmp_path, capsys
    ):
        (tmp_path / ".agents" / "sessions").mkdir(parents=True)
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("SKIP_QA_GATE", raising=False)
        input_data = json.dumps({
            "tool_input": {"command": "gh pr create --title test"},
        })
        monkeypatch.setattr("sys.stdin", io.StringIO(input_data))
        result = invoke_routing_gates.main()
        assert result == 0  # JSON deny, exit 0
        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output["decision"] == "deny"

    @patch("invoke_routing_gates.skip_if_consumer_repo", return_value=False)
    @patch("invoke_routing_gates.is_valid_project_root", return_value=True)
    @patch("invoke_routing_gates.check_documentation_only", return_value=True)
    def test_allows_pr_with_docs_only(self, mock_doc, mock_valid, mock_skip, monkeypatch, tmp_path):
        (tmp_path / ".agents" / "sessions").mkdir(parents=True)
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("SKIP_QA_GATE", raising=False)
        input_data = json.dumps({
            "tool_input": {"command": "gh pr create --title test"},
        })
        monkeypatch.setattr("sys.stdin", io.StringIO(input_data))
        assert invoke_routing_gates.main() == 0

    @patch("invoke_routing_gates.skip_if_consumer_repo", return_value=False)
    @patch("invoke_routing_gates.is_valid_project_root", return_value=True)
    @patch("invoke_routing_gates.check_qa_evidence", return_value=True)
    @patch("invoke_routing_gates.check_documentation_only", return_value=False)
    def test_allows_pr_with_qa_evidence(
        self, mock_doc, mock_qa, mock_valid, mock_skip, monkeypatch, tmp_path
    ):
        (tmp_path / ".agents" / "sessions").mkdir(parents=True)
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("SKIP_QA_GATE", raising=False)
        input_data = json.dumps({
            "tool_input": {"command": "gh pr create --title test"},
        })
        monkeypatch.setattr("sys.stdin", io.StringIO(input_data))
        assert invoke_routing_gates.main() == 0

    @patch("invoke_routing_gates.skip_if_consumer_repo", return_value=False)
    @patch("invoke_routing_gates.is_valid_project_root", return_value=True)
    def test_handles_invalid_json(self, mock_valid, mock_skip, monkeypatch, tmp_path):
        (tmp_path / ".agents" / "sessions").mkdir(parents=True)
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr("sys.stdin", io.StringIO("not json"))
        assert invoke_routing_gates.main() == 0

    @patch("invoke_routing_gates.skip_if_consumer_repo", return_value=False)
    @patch("invoke_routing_gates.is_valid_project_root", return_value=False)
    def test_invalid_project_root_fails_open(self, mock_valid, mock_skip, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        input_data = json.dumps({
            "tool_input": {"command": "gh pr create"},
        })
        monkeypatch.setattr("sys.stdin", io.StringIO(input_data))
        assert invoke_routing_gates.main() == 0


class TestWriteAuditLogAllPathsFail:
    """Tests for write_audit_log when all write paths fail."""

    def test_prints_to_stderr_when_both_paths_fail(self, monkeypatch, capsys):
        def fail_all_opens(path, *args, **kwargs):
            raise OSError("all paths fail")

        monkeypatch.setattr("builtins.open", fail_all_opens)
        invoke_routing_gates.write_audit_log("TestHook", "critical message")
        captured = capsys.readouterr()
        assert "CRITICAL" in captured.err
        assert "critical message" in captured.err


class TestModuleAsScript:
    """Test that hooks can be executed as scripts via __main__."""

    def test_routing_gates_as_script(self, tmp_path):
        import subprocess

        hook_path = str(
            Path(__file__).resolve().parents[2]
            / ".claude" / "hooks" / "invoke_routing_gates.py"
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
            / ".claude" / "hooks" / "invoke_routing_gates.py"
        )
        monkeypatch.setattr("sys.stdin", io.StringIO(""))
        with pytest.raises(SystemExit) as exc_info:
            runpy.run_path(hook_path, run_name="__main__")
        assert exc_info.value.code == 0
