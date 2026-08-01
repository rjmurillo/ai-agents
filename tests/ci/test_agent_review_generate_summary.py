"""Tests for scripts/ci/agent_review_generate_summary.py."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from scripts.ci.agent_review_generate_summary import main, run


class TestRun:
    def _make_env(self, tmp_path: Path, verdict: str = "PASS") -> dict[str, str]:
        summary = tmp_path / "summary.md"
        return {
            "AGENT": "security",
            "EMOJI": "🔒",
            "VERDICT": verdict,
            "FINDINGS": "All clear",
            "RUN_ID": "100",
            "SERVER_URL": "https://github.com",
            "REPOSITORY": "owner/repo",
            "PR_NUMBER": "5",
            "CACHE_HIT": "false",
            "GITHUB_WORKSPACE": "",
            "GITHUB_STEP_SUMMARY": str(summary),
        }

    def test_writes_summary_to_file(self, tmp_path: Path) -> None:
        env = self._make_env(tmp_path)

        with patch.dict(os.environ, env):
            with patch("scripts.ci.agent_review_generate_summary.sys") as mock_sys:
                mock_sys.path = sys.path[:]
                mock_sys.executable = sys.executable
                mock_sys.exit = sys.exit

                mock_module = MagicMock()
                mock_module.get_verdict_alert_type = MagicMock(return_value="NOTE")
                mock_module.get_verdict_emoji = MagicMock(return_value="✅")

                with patch.dict(
                    "sys.modules",
                    {
                        "scripts": MagicMock(),
                        "scripts.ai_review_common": MagicMock(),
                        "scripts.ai_review_common.issue_triage": mock_module,
                    },
                ):
                    rc = run()
        assert rc == 0
        assert (tmp_path / "summary.md").read_text() != ""

    def test_default_verdict_when_empty(self, tmp_path: Path) -> None:
        env = self._make_env(tmp_path, verdict="")
        mock_module = MagicMock()
        mock_module.get_verdict_alert_type = MagicMock(return_value="WARNING")
        mock_module.get_verdict_emoji = MagicMock(return_value="⚠️")
        with patch.dict(os.environ, env):
            with patch.dict(
                "sys.modules",
                {
                    "scripts": MagicMock(),
                    "scripts.ai_review_common": MagicMock(),
                    "scripts.ai_review_common.issue_triage": mock_module,
                },
            ):
                rc = run()
        assert rc == 0

    def test_returns_1_on_import_error(self, tmp_path: Path) -> None:
        env = self._make_env(tmp_path)
        with patch.dict(os.environ, env):
            with patch.dict("sys.modules", {"scripts.ai_review_common.issue_triage": None}):
                rc = run()
        assert rc == 1

    def test_stdout_when_no_summary_file(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        env = self._make_env(tmp_path)
        env["GITHUB_STEP_SUMMARY"] = ""
        mock_module = MagicMock()
        mock_module.get_verdict_alert_type = MagicMock(return_value="NOTE")
        mock_module.get_verdict_emoji = MagicMock(return_value="✅")
        with patch.dict(os.environ, env):
            with patch.dict(
                "sys.modules",
                {
                    "scripts": MagicMock(),
                    "scripts.ai_review_common": MagicMock(),
                    "scripts.ai_review_common.issue_triage": mock_module,
                },
            ):
                run()
        out = capsys.readouterr().out
        assert "security" in out.lower() or "Security" in out or "PASS" in out


def _run_with_mocks(mock_alert: MagicMock, mock_emoji: MagicMock, args: tuple, kwargs: dict) -> int:
    return 0


class TestMain:
    def test_main_delegates(self) -> None:
        with patch("scripts.ci.agent_review_generate_summary.run", return_value=0):
            assert main() == 0
