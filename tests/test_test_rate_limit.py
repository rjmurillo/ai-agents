"""Tests for .github/scripts/test_rate_limit.py."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure the repo root is on sys.path so the script can import github_core
sys.path.insert(
    0,
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..")),
)
sys.path.insert(
    0,
    os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", ".github", "scripts")
    ),
)

import test_rate_limit  # must come after sys.path setup

from scripts.github_core.api import RateLimitResult, RateLimitStatus


def _make_result(
    success: bool = True,
    core_remaining: int = 500,
    status: RateLimitStatus | None = None,
) -> RateLimitResult:
    return RateLimitResult(
        success=success,
        status=status,
        resources={
            "core": {
                "Remaining": core_remaining,
                "Limit": 5000,
                "Reset": 0,
                "Threshold": 100,
                "Passed": success,
            },
        },
        summary_markdown="### Rate Limit OK",
        core_remaining=core_remaining,
    )


class TestMain:
    """Tests for the main() entry point."""

    @patch("test_rate_limit.check_workflow_rate_limit")
    def test_success_returns_zero(self, mock_check: MagicMock) -> None:
        mock_check.return_value = _make_result(success=True)
        assert test_rate_limit.main([]) == 0

    @patch("test_rate_limit.check_workflow_rate_limit")
    def test_low_rate_limit_returns_one(self, mock_check: MagicMock) -> None:
        mock_check.return_value = _make_result(
            success=False, core_remaining=10
        )
        assert test_rate_limit.main([]) == 1

    @patch("test_rate_limit.check_workflow_rate_limit")
    def test_indeterminate_rate_limit_returns_one(
        self, mock_check: MagicMock, capsys
    ) -> None:
        mock_check.return_value = _make_result(
            success=False,
            status=RateLimitStatus.COULD_NOT_DETERMINE,
        )
        assert test_rate_limit.main([]) == 1
        assert "could_not_determine" in capsys.readouterr().err

    @patch("test_rate_limit.check_workflow_rate_limit")
    def test_runtime_error_returns_one(self, mock_check: MagicMock) -> None:
        mock_check.side_effect = RuntimeError("API failure")
        assert test_rate_limit.main([]) == 1

    @patch("test_rate_limit.check_workflow_rate_limit")
    def test_custom_thresholds_passed(self, mock_check: MagicMock) -> None:
        mock_check.return_value = _make_result(success=True)
        test_rate_limit.main(
            ["--core-threshold", "200", "--graphql-threshold", "100"]
        )
        mock_check.assert_called_once_with(
            resource_thresholds={"core": 200, "graphql": 100},
        )

    @patch("test_rate_limit.check_workflow_rate_limit")
    def test_writes_github_output(
        self, mock_check: MagicMock, tmp_path: Path
    ) -> None:
        mock_check.return_value = _make_result(
            success=True, core_remaining=4500
        )
        output_file = tmp_path / "github_output"
        output_file.write_text("")
        with patch.dict(
            os.environ, {"GITHUB_OUTPUT": str(output_file)}
        ):
            test_rate_limit.main([])
        content = output_file.read_text()
        assert "core_remaining=4500" in content

    @patch("test_rate_limit.check_workflow_rate_limit")
    def test_writes_step_summary(
        self, mock_check: MagicMock, tmp_path: Path
    ) -> None:
        mock_check.return_value = _make_result(success=True)
        summary_file = tmp_path / "step_summary"
        summary_file.write_text("")
        with patch.dict(
            os.environ, {"GITHUB_STEP_SUMMARY": str(summary_file)}
        ):
            test_rate_limit.main([])
        content = summary_file.read_text()
        assert "Rate Limit OK" in content

    @patch("test_rate_limit.check_workflow_rate_limit")
    def test_default_thresholds(self, mock_check: MagicMock) -> None:
        mock_check.return_value = _make_result(success=True)
        test_rate_limit.main([])
        mock_check.assert_called_once_with(
            resource_thresholds={"core": 100, "graphql": 50},
        )


# ---------------------------------------------------------------------------
# Tests for probe_api_reachability (issue #4326)
# ---------------------------------------------------------------------------


from scripts.github_core.rate_limit import probe_api_reachability  # noqa: E402


class TestProbeApiReachability:
    """probe_api_reachability detects burst-limiter 403s that rate_limit misses."""

    @patch("subprocess.run")
    def test_returns_true_on_success(self, mock_run: MagicMock) -> None:
        """A 200 response from repos/{owner}/{repo} returns True."""
        mock_run.return_value = MagicMock(returncode=0, stdout="owner/repo")
        assert probe_api_reachability("owner", "repo") is True

    @patch("subprocess.run")
    def test_returns_false_on_403(self, mock_run: MagicMock) -> None:
        """A 403 burst refusal returns False while primary quota is healthy (issue #4326)."""
        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="API rate limit exceeded (HTTP 403)"
        )
        assert probe_api_reachability("owner", "repo") is False

    @patch("subprocess.run")
    def test_returns_false_on_timeout(self, mock_run: MagicMock) -> None:
        """A timeout from the probe returns False without raising."""
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="gh", timeout=15)
        assert probe_api_reachability("owner", "repo") is False

    @patch("subprocess.run")
    def test_returns_false_on_os_error(self, mock_run: MagicMock) -> None:
        """If gh is not installed, OSError returns False without raising."""
        mock_run.side_effect = OSError("gh not found")
        assert probe_api_reachability("owner", "repo") is False

    @patch("subprocess.run")
    def test_probe_calls_repos_endpoint_not_rate_limit(self, mock_run: MagicMock) -> None:
        """Probe makes a real repos/{owner}/{repo} call, not just rate_limit (issue #4326).

        rate_limit does NOT expose the burst limiter; only a real probe does.
        """
        mock_run.return_value = MagicMock(returncode=0, stdout="rjmurillo/ai-agents")
        probe_api_reachability("rjmurillo", "ai-agents")
        called = mock_run.call_args
        cmd = called[0][0] if called[0] else called.kwargs.get("args", [])
        assert "repos/rjmurillo/ai-agents" in " ".join(cmd)
        assert "rate_limit" not in " ".join(cmd)
