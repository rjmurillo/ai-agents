"""Tests for scripts/ci/smoke_report_result.py."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from scripts.ci.smoke_report_result import main, run


class TestRun:
    def test_check_paths_not_success_returns_1(self) -> None:
        env = {
            "CHECK_PATHS_RESULT": "failure",
            "CLI_CHANGED": "true",
            "SMOKE_RESULT": "success",
            "VERIFY_RESULT": "success",
        }
        with patch.dict(os.environ, env):
            assert run() == 1

    def test_cli_not_changed_returns_0(self) -> None:
        env = {
            "CHECK_PATHS_RESULT": "success",
            "CLI_CHANGED": "false",
            "SMOKE_RESULT": "failure",
            "VERIFY_RESULT": "failure",
        }
        with patch.dict(os.environ, env):
            assert run() == 0

    def test_smoke_not_success_returns_1(self) -> None:
        env = {
            "CHECK_PATHS_RESULT": "success",
            "CLI_CHANGED": "true",
            "SMOKE_RESULT": "failure",
            "VERIFY_RESULT": "success",
        }
        with patch.dict(os.environ, env):
            assert run() == 1

    def test_verify_not_success_returns_1(self) -> None:
        env = {
            "CHECK_PATHS_RESULT": "success",
            "CLI_CHANGED": "true",
            "SMOKE_RESULT": "success",
            "VERIFY_RESULT": "failure",
        }
        with patch.dict(os.environ, env):
            assert run() == 1

    def test_all_success_returns_0(self) -> None:
        env = {
            "CHECK_PATHS_RESULT": "success",
            "CLI_CHANGED": "true",
            "SMOKE_RESULT": "success",
            "VERIFY_RESULT": "success",
        }
        with patch.dict(os.environ, env):
            assert run() == 0

    def test_error_annotation_printed_on_failure(self, capsys: pytest.CaptureFixture[str]) -> None:
        env = {
            "CHECK_PATHS_RESULT": "success",
            "CLI_CHANGED": "true",
            "SMOKE_RESULT": "cancelled",
            "VERIFY_RESULT": "success",
        }
        with patch.dict(os.environ, env):
            run()
        assert "::error::" in capsys.readouterr().out

    def test_skipped_message_when_cli_not_changed(self, capsys: pytest.CaptureFixture[str]) -> None:
        env = {
            "CHECK_PATHS_RESULT": "success",
            "CLI_CHANGED": "false",
            "SMOKE_RESULT": "",
            "VERIFY_RESULT": "",
        }
        with patch.dict(os.environ, env):
            run()
        assert "skipped" in capsys.readouterr().out.lower()

    def test_success_message_printed(self, capsys: pytest.CaptureFixture[str]) -> None:
        env = {
            "CHECK_PATHS_RESULT": "success",
            "CLI_CHANGED": "true",
            "SMOKE_RESULT": "success",
            "VERIFY_RESULT": "success",
        }
        with patch.dict(os.environ, env):
            run()
        out = capsys.readouterr().out
        assert "passed" in out.lower()


class TestMain:
    def test_main_delegates_to_run(self) -> None:
        with patch("scripts.ci.smoke_report_result.run", return_value=2):
            assert main() == 2
