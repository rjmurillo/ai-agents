"""Tests for scripts/ci/spec_external_signal_wrapper.py."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from scripts.ci.spec_external_signal_wrapper import _pr_body_fallback, main, run


class TestPrBodyFallback:
    def test_returns_empty_when_no_pr_number(self) -> None:
        assert _pr_body_fallback("", "owner/repo") == ""

    def test_returns_empty_when_no_repo(self) -> None:
        assert _pr_body_fallback("5", "") == ""

    def test_calls_gh_and_returns_body(self) -> None:
        mock = MagicMock(returncode=0, stdout="PR body text")
        with patch("scripts.ci.spec_external_signal_wrapper.subprocess.run", return_value=mock):
            result = _pr_body_fallback("3", "owner/repo")
        assert result == "PR body text"

    def test_returns_empty_on_gh_failure(self) -> None:
        mock = MagicMock(returncode=1, stdout="")
        with patch("scripts.ci.spec_external_signal_wrapper.subprocess.run", return_value=mock):
            result = _pr_body_fallback("3", "owner/repo")
        assert result == ""


class TestRun:
    def test_passes_through_gate_exit_code_0(self, tmp_path: Path) -> None:
        summary = tmp_path / "summary.md"
        env = {
            "PR_BODY": "some body",
            "PR_NUMBER": "",
            "GITHUB_REPOSITORY": "owner/repo",
            "GITHUB_RUN_ID": "1",
            "GITHUB_RUN_ATTEMPT": "1",
            "RUNNER_TEMP": str(tmp_path),
            "GITHUB_STEP_SUMMARY": str(summary),
        }
        ok = MagicMock(returncode=0, stdout='{"result":"pass"}', stderr="")
        with patch.dict(os.environ, env):
            with patch("scripts.ci.spec_external_signal_wrapper.subprocess.run", return_value=ok):
                rc = run()
        assert rc == 0

    def test_passes_through_gate_exit_code_nonzero(self, tmp_path: Path) -> None:
        summary = tmp_path / "summary.md"
        env = {
            "PR_BODY": "body",
            "GITHUB_RUN_ID": "2",
            "GITHUB_RUN_ATTEMPT": "1",
            "RUNNER_TEMP": str(tmp_path),
            "GITHUB_STEP_SUMMARY": str(summary),
        }
        fail = MagicMock(returncode=2, stdout="error output", stderr="")
        with patch.dict(os.environ, env):
            with patch("scripts.ci.spec_external_signal_wrapper.subprocess.run", return_value=fail):
                rc = run()
        assert rc == 2

    def test_writes_to_step_summary(self, tmp_path: Path) -> None:
        summary = tmp_path / "summary.md"
        env = {
            "PR_BODY": "body",
            "GITHUB_RUN_ID": "3",
            "GITHUB_RUN_ATTEMPT": "1",
            "RUNNER_TEMP": str(tmp_path),
            "GITHUB_STEP_SUMMARY": str(summary),
        }
        ok = MagicMock(returncode=0, stdout="gate output", stderr="")
        with patch.dict(os.environ, env):
            with patch("scripts.ci.spec_external_signal_wrapper.subprocess.run", return_value=ok):
                run()
        assert "External-signal gate" in summary.read_text()

    def test_falls_back_to_gh_when_pr_body_empty(self, tmp_path: Path) -> None:
        summary = tmp_path / "summary.md"
        env = {
            "PR_BODY": "",
            "PR_NUMBER": "7",
            "GITHUB_REPOSITORY": "owner/repo",
            "GITHUB_RUN_ID": "4",
            "GITHUB_RUN_ATTEMPT": "1",
            "RUNNER_TEMP": str(tmp_path),
            "GITHUB_STEP_SUMMARY": str(summary),
        }
        gh_mock = MagicMock(returncode=0, stdout="from gh cli")
        gate_mock = MagicMock(returncode=0, stdout="gate output", stderr="")
        call_count = [0]

        def mock_run(cmd: list[str], **kw: object) -> MagicMock:
            call_count[0] += 1
            if "gh" in cmd:
                return gh_mock
            return gate_mock

        with patch.dict(os.environ, env):
            with patch(
                "scripts.ci.spec_external_signal_wrapper.subprocess.run", side_effect=mock_run
            ):
                run()
        # gh was called (fallback)
        assert call_count[0] >= 2


class TestMain:
    def test_main_delegates(self) -> None:
        with patch("scripts.ci.spec_external_signal_wrapper.run", return_value=0):
            assert main() == 0
