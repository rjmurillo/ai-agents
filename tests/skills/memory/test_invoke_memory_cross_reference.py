"""Tests for invoke_memory_cross_reference.py."""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

SCRIPT_DIR = Path(__file__).resolve().parents[3] / ".claude" / "skills" / "memory" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import invoke_memory_cross_reference


class TestRunScript:
    """Tests for run_script function."""

    @patch("invoke_memory_cross_reference.subprocess.run")
    def test_parses_json_output(self, mock_run):
        mock_run.return_value = type("R", (), {
            "stdout": '{"LinksAdded": 5, "FilesModified": 2}',
            "returncode": 0,
        })()
        result = invoke_memory_cross_reference.run_script("/fake/script.py", [])
        assert result is not None
        assert result["LinksAdded"] == 5

    @patch("invoke_memory_cross_reference.subprocess.run")
    def test_returns_none_on_empty_output(self, mock_run):
        mock_run.return_value = type("R", (), {"stdout": "", "returncode": 0})()
        result = invoke_memory_cross_reference.run_script("/fake/script.py", [])
        assert result is None

    @patch("invoke_memory_cross_reference.subprocess.run")
    def test_handles_timeout(self, mock_run):
        from subprocess import TimeoutExpired
        mock_run.side_effect = TimeoutExpired(cmd="python", timeout=60)
        result = invoke_memory_cross_reference.run_script("/fake/script.py", [])
        assert result is not None
        assert "Error" in result


class TestMainAlwaysExitsZero:
    """Test that script always exits 0 (fail-open for hooks)."""

    @patch("invoke_memory_cross_reference.run_script")
    def test_exits_zero_on_success(self, mock_run):
        mock_run.return_value = {
            "LinksAdded": 0, "FilesModified": 0, "Errors": [],
        }
        with patch("sys.argv", ["invoke_memory_cross_reference.py"]):
            with pytest.raises(SystemExit) as exc:
                invoke_memory_cross_reference.main()
            assert exc.value.code == 0

    @patch("invoke_memory_cross_reference.run_script")
    def test_exits_zero_on_error(self, mock_run):
        mock_run.return_value = {"Error": "something broke"}
        with patch("sys.argv", ["invoke_memory_cross_reference.py"]):
            with pytest.raises(SystemExit) as exc:
                invoke_memory_cross_reference.main()
            assert exc.value.code == 0
