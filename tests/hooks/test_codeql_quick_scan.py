"""Tests for codeql_quick_scan.py Claude Code PostToolUse hook."""

import io
import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Add hooks directory to path for import
HOOKS_DIR = (
    Path(__file__).resolve().parents[2] / ".claude" / "hooks" / "PostToolUse"
)
sys.path.insert(0, str(HOOKS_DIR))

import codeql_quick_scan


class TestGetFilePathFromInput:
    """Tests for _get_file_path_from_input."""

    def test_extracts_file_path(self):
        hook_input = {"tool_input": {"file_path": "/tmp/test.py"}}
        assert codeql_quick_scan._get_file_path_from_input(hook_input) == "/tmp/test.py"

    def test_returns_none_for_missing_tool_input(self):
        assert codeql_quick_scan._get_file_path_from_input({}) is None

    def test_returns_none_for_non_dict_tool_input(self):
        assert codeql_quick_scan._get_file_path_from_input(
            {"tool_input": "string"}
        ) is None

    def test_returns_none_for_missing_file_path(self):
        assert codeql_quick_scan._get_file_path_from_input(
            {"tool_input": {"command": "test"}}
        ) is None


class TestGetProjectDirectory:
    """Tests for _get_project_directory."""

    def test_uses_env_var(self, monkeypatch):
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", "/custom")
        result = codeql_quick_scan._get_project_directory({"cwd": "/other"})
        assert result == "/custom"

    def test_uses_cwd_from_input(self, monkeypatch):
        monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
        result = codeql_quick_scan._get_project_directory({"cwd": "/from/input"})
        assert result == "/from/input"

    def test_falls_back_to_os_getcwd(self, monkeypatch):
        monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
        result = codeql_quick_scan._get_project_directory({})
        assert result == os.getcwd()


class TestShouldScanFile:
    """Tests for _should_scan_file."""

    def test_python_file(self, tmp_path):
        py_file = tmp_path / "test.py"
        py_file.write_text("print('hello')")
        assert codeql_quick_scan._should_scan_file(str(py_file)) is True

    def test_workflow_yml(self, tmp_path):
        workflow_dir = tmp_path / ".github" / "workflows"
        workflow_dir.mkdir(parents=True)
        yml_file = workflow_dir / "ci.yml"
        yml_file.write_text("name: CI")
        assert codeql_quick_scan._should_scan_file(str(yml_file)) is True

    def test_workflow_yaml(self, tmp_path):
        workflow_dir = tmp_path / ".github" / "workflows"
        workflow_dir.mkdir(parents=True)
        yaml_file = workflow_dir / "ci.yaml"
        yaml_file.write_text("name: CI")
        assert codeql_quick_scan._should_scan_file(str(yaml_file)) is True

    def test_non_workflow_yml(self, tmp_path):
        yml_file = tmp_path / "config.yml"
        yml_file.write_text("key: value")
        assert codeql_quick_scan._should_scan_file(str(yml_file)) is False

    def test_empty_path(self):
        assert codeql_quick_scan._should_scan_file("") is False

    def test_none_path(self):
        assert codeql_quick_scan._should_scan_file(None) is False

    def test_nonexistent_file(self):
        assert codeql_quick_scan._should_scan_file("/nonexistent/file.py") is False

    def test_non_scannable_file(self, tmp_path):
        txt_file = tmp_path / "readme.txt"
        txt_file.write_text("hello")
        assert codeql_quick_scan._should_scan_file(str(txt_file)) is False


class TestIsCodeQLInstalled:
    """Tests for _is_codeql_installed."""

    def test_found_in_path(self, tmp_path):
        with patch("shutil.which", return_value="/usr/bin/codeql"):
            assert codeql_quick_scan._is_codeql_installed(str(tmp_path)) is True

    def test_found_at_default_path(self, tmp_path):
        codeql_dir = tmp_path / ".codeql" / "cli"
        codeql_dir.mkdir(parents=True)
        codeql_bin = codeql_dir / "codeql"
        codeql_bin.write_text("#!/bin/sh")
        with patch("shutil.which", return_value=None):
            assert codeql_quick_scan._is_codeql_installed(str(tmp_path)) is True

    def test_not_installed(self, tmp_path):
        with patch("shutil.which", return_value=None):
            assert codeql_quick_scan._is_codeql_installed(str(tmp_path)) is False


class TestGetLanguageFromFile:
    """Tests for _get_language_from_file."""

    def test_python_file(self):
        assert codeql_quick_scan._get_language_from_file("test.py") == "python"

    def test_yml_file(self):
        assert codeql_quick_scan._get_language_from_file("ci.yml") == "actions"

    def test_yaml_file(self):
        assert codeql_quick_scan._get_language_from_file("ci.yaml") == "actions"

    def test_unknown_file(self):
        assert codeql_quick_scan._get_language_from_file("test.rs") is None

    def test_case_insensitive(self):
        assert codeql_quick_scan._get_language_from_file("Test.PY") == "python"


class TestMain:
    """Tests for main() entry point."""

    def test_empty_input(self, monkeypatch):
        monkeypatch.setattr("sys.stdin", io.StringIO(""))
        assert codeql_quick_scan.main() == 0

    def test_non_scannable_file(self, monkeypatch, tmp_path):
        txt_file = tmp_path / "readme.txt"
        txt_file.write_text("hello")
        input_data = json.dumps({
            "tool_input": {"file_path": str(txt_file)},
            "cwd": str(tmp_path),
        })
        monkeypatch.setattr("sys.stdin", io.StringIO(input_data))
        assert codeql_quick_scan.main() == 0

    def test_codeql_not_installed_skips(self, monkeypatch, tmp_path):
        py_file = tmp_path / "test.py"
        py_file.write_text("x = 1")
        input_data = json.dumps({
            "tool_input": {"file_path": str(py_file)},
            "cwd": str(tmp_path),
        })
        monkeypatch.setattr("sys.stdin", io.StringIO(input_data))
        with patch.object(
            codeql_quick_scan, "_is_codeql_installed", return_value=False
        ):
            assert codeql_quick_scan.main() == 0

    def test_scan_script_missing_skips(self, monkeypatch, tmp_path):
        py_file = tmp_path / "test.py"
        py_file.write_text("x = 1")
        input_data = json.dumps({
            "tool_input": {"file_path": str(py_file)},
            "cwd": str(tmp_path),
        })
        monkeypatch.setattr("sys.stdin", io.StringIO(input_data))
        with patch.object(
            codeql_quick_scan, "_is_codeql_installed", return_value=True
        ):
            assert codeql_quick_scan.main() == 0

    def test_scan_timeout(self, monkeypatch, tmp_path, capsys):
        py_file = tmp_path / "test.py"
        py_file.write_text("x = 1")
        scan_dir = tmp_path / ".codeql" / "scripts"
        scan_dir.mkdir(parents=True)
        (scan_dir / "Invoke-CodeQLScan.ps1").write_text("# scan")
        input_data = json.dumps({
            "tool_input": {"file_path": str(py_file)},
            "cwd": str(tmp_path),
        })
        monkeypatch.setattr("sys.stdin", io.StringIO(input_data))
        with patch.object(
            codeql_quick_scan, "_is_codeql_installed", return_value=True
        ):
            with patch(
                "subprocess.run",
                side_effect=subprocess.TimeoutExpired(cmd="pwsh", timeout=30),
            ):
                result = codeql_quick_scan.main()
        assert result == 0
        captured = capsys.readouterr()
        assert "timed out" in captured.out

    def test_scan_failure(self, monkeypatch, tmp_path, capsys):
        py_file = tmp_path / "test.py"
        py_file.write_text("x = 1")
        scan_dir = tmp_path / ".codeql" / "scripts"
        scan_dir.mkdir(parents=True)
        (scan_dir / "Invoke-CodeQLScan.ps1").write_text("# scan")
        input_data = json.dumps({
            "tool_input": {"file_path": str(py_file)},
            "cwd": str(tmp_path),
        })
        monkeypatch.setattr("sys.stdin", io.StringIO(input_data))
        with patch.object(
            codeql_quick_scan, "_is_codeql_installed", return_value=True
        ):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = subprocess.CompletedProcess(
                    args=[], returncode=1, stdout="", stderr="error"
                )
                result = codeql_quick_scan.main()
        assert result == 0
        captured = capsys.readouterr()
        assert "ERROR" in captured.out

    def test_scan_with_findings(self, monkeypatch, tmp_path, capsys):
        py_file = tmp_path / "test.py"
        py_file.write_text("x = 1")
        scan_dir = tmp_path / ".codeql" / "scripts"
        scan_dir.mkdir(parents=True)
        (scan_dir / "Invoke-CodeQLScan.ps1").write_text("# scan")
        scan_output = json.dumps({"TotalFindings": 3})
        input_data = json.dumps({
            "tool_input": {"file_path": str(py_file)},
            "cwd": str(tmp_path),
        })
        monkeypatch.setattr("sys.stdin", io.StringIO(input_data))
        with patch.object(
            codeql_quick_scan, "_is_codeql_installed", return_value=True
        ):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = subprocess.CompletedProcess(
                    args=[], returncode=0,
                    stdout=scan_output,
                    stderr=""
                )
                result = codeql_quick_scan.main()
        assert result == 0
        captured = capsys.readouterr()
        assert "3 finding(s)" in captured.out

    def test_scan_no_findings(self, monkeypatch, tmp_path, capsys):
        py_file = tmp_path / "test.py"
        py_file.write_text("x = 1")
        scan_dir = tmp_path / ".codeql" / "scripts"
        scan_dir.mkdir(parents=True)
        (scan_dir / "Invoke-CodeQLScan.ps1").write_text("# scan")
        scan_output = json.dumps({"TotalFindings": 0})
        input_data = json.dumps({
            "tool_input": {"file_path": str(py_file)},
            "cwd": str(tmp_path),
        })
        monkeypatch.setattr("sys.stdin", io.StringIO(input_data))
        with patch.object(
            codeql_quick_scan, "_is_codeql_installed", return_value=True
        ):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = subprocess.CompletedProcess(
                    args=[], returncode=0,
                    stdout=scan_output,
                    stderr=""
                )
                result = codeql_quick_scan.main()
        assert result == 0
        captured = capsys.readouterr()
        assert "No findings" in captured.out

    def test_scan_invalid_json_output(self, monkeypatch, tmp_path, capsys):
        py_file = tmp_path / "test.py"
        py_file.write_text("x = 1")
        scan_dir = tmp_path / ".codeql" / "scripts"
        scan_dir.mkdir(parents=True)
        (scan_dir / "Invoke-CodeQLScan.ps1").write_text("# scan")
        input_data = json.dumps({
            "tool_input": {"file_path": str(py_file)},
            "cwd": str(tmp_path),
        })
        monkeypatch.setattr("sys.stdin", io.StringIO(input_data))
        with patch.object(
            codeql_quick_scan, "_is_codeql_installed", return_value=True
        ):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = subprocess.CompletedProcess(
                    args=[], returncode=0,
                    stdout="not json output",
                    stderr=""
                )
                result = codeql_quick_scan.main()
        assert result == 0

    def test_invalid_json_input(self, monkeypatch):
        monkeypatch.setattr("sys.stdin", io.StringIO("not json"))
        assert codeql_quick_scan.main() == 0

    def test_always_returns_zero(self, monkeypatch):
        """Non-blocking hook always exits 0."""
        monkeypatch.setattr("sys.stdin", io.StringIO(""))
        assert codeql_quick_scan.main() == 0

    def test_stdin_not_readable(self, monkeypatch):
        """When stdin is not readable, main returns 0."""
        mock_stdin = io.StringIO("")
        mock_stdin.readable = lambda: False
        monkeypatch.setattr("sys.stdin", mock_stdin)
        assert codeql_quick_scan.main() == 0

    def test_language_returns_none_for_scannable_file(self, monkeypatch, tmp_path):
        """When _get_language_from_file returns None, main exits early."""
        txt_file = tmp_path / "test.rs"
        txt_file.write_text("fn main() {}")
        input_data = json.dumps({
            "tool_input": {"file_path": str(txt_file)},
            "cwd": str(tmp_path),
        })
        monkeypatch.setattr("sys.stdin", io.StringIO(input_data))
        with patch.object(
            codeql_quick_scan, "_should_scan_file", return_value=True
        ):
            with patch.object(
                codeql_quick_scan, "_is_codeql_installed", return_value=True
            ):
                assert codeql_quick_scan.main() == 0

    def test_oserror_caught(self, monkeypatch, tmp_path):
        """OSError in main body is caught and returns 0."""
        py_file = tmp_path / "test.py"
        py_file.write_text("x = 1")
        input_data = json.dumps({
            "tool_input": {"file_path": str(py_file)},
            "cwd": str(tmp_path),
        })
        monkeypatch.setattr("sys.stdin", io.StringIO(input_data))
        with patch.object(
            codeql_quick_scan, "_is_codeql_installed",
            side_effect=OSError("permission denied"),
        ):
            assert codeql_quick_scan.main() == 0

    def test_permission_error_caught(self, monkeypatch, tmp_path):
        """PermissionError in main body is caught and returns 0."""
        py_file = tmp_path / "test.py"
        py_file.write_text("x = 1")
        input_data = json.dumps({
            "tool_input": {"file_path": str(py_file)},
            "cwd": str(tmp_path),
        })
        monkeypatch.setattr("sys.stdin", io.StringIO(input_data))
        with patch.object(
            codeql_quick_scan, "_is_codeql_installed",
            side_effect=PermissionError("denied"),
        ):
            assert codeql_quick_scan.main() == 0

    def test_unexpected_exception_caught(self, monkeypatch, tmp_path):
        """Unexpected Exception in main body is caught and returns 0."""
        py_file = tmp_path / "test.py"
        py_file.write_text("x = 1")
        input_data = json.dumps({
            "tool_input": {"file_path": str(py_file)},
            "cwd": str(tmp_path),
        })
        monkeypatch.setattr("sys.stdin", io.StringIO(input_data))
        with patch.object(
            codeql_quick_scan, "_is_codeql_installed",
            side_effect=RuntimeError("unexpected"),
        ):
            assert codeql_quick_scan.main() == 0

    def test_scan_invalid_json_output_with_error_message(
        self, monkeypatch, tmp_path, capsys
    ):
        """Invalid JSON from scan output prints error message."""
        py_file = tmp_path / "test.py"
        py_file.write_text("x = 1")
        scan_dir = tmp_path / ".codeql" / "scripts"
        scan_dir.mkdir(parents=True)
        (scan_dir / "Invoke-CodeQLScan.ps1").write_text("# scan")
        input_data = json.dumps({
            "tool_input": {"file_path": str(py_file)},
            "cwd": str(tmp_path),
        })
        monkeypatch.setattr("sys.stdin", io.StringIO(input_data))
        with patch.object(
            codeql_quick_scan, "_is_codeql_installed", return_value=True
        ):
            with patch("subprocess.run") as mock_run:
                # Output with { prefix lines that fail JSON parsing
                mock_run.return_value = subprocess.CompletedProcess(
                    args=[], returncode=0,
                    stdout="{not valid json at all",
                    stderr=""
                )
                result = codeql_quick_scan.main()
        assert result == 0
        captured = capsys.readouterr()
        assert "ERROR" in captured.out


class TestIsCodeQLInstalledWin32:
    """Tests for _is_codeql_installed on Windows platform."""

    def test_win32_appends_exe(self, tmp_path):
        """On win32 platform, .exe is appended to codeql path."""
        with patch("shutil.which", return_value=None):
            with patch.object(sys, "platform", "win32"):
                codeql_dir = tmp_path / ".codeql" / "cli"
                codeql_dir.mkdir(parents=True)
                codeql_bin = codeql_dir / "codeql.exe"
                codeql_bin.write_text("binary")
                result = codeql_quick_scan._is_codeql_installed(str(tmp_path))
                assert result is True


class TestModuleAsScript:
    """Test that the hook can be executed as a script via __main__."""

    def test_codeql_quick_scan_as_script(self):
        hook_path = str(
            Path(__file__).resolve().parents[2]
            / ".claude" / "hooks" / "PostToolUse" / "codeql_quick_scan.py"
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
            / ".claude" / "hooks" / "PostToolUse" / "codeql_quick_scan.py"
        )
        monkeypatch.setattr("sys.stdin", io.StringIO(""))
        with pytest.raises(SystemExit) as exc_info:
            runpy.run_path(hook_path, run_name="__main__")
        assert exc_info.value.code == 0
