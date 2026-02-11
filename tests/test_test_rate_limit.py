"""Tests for .github/scripts/test_rate_limit.py."""

from __future__ import annotations

import os
import sys
from unittest.mock import patch

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

import test_rate_limit  # noqa: E402  # must come after sys.path setup

from scripts.github_core.api import RateLimitResult  # noqa: E402


def _make_result(
    success: bool = True,
    core_remaining: int = 500,
) -> RateLimitResult:
    return RateLimitResult(
        success=success,
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
    def test_success_returns_zero(self, mock_check: object) -> None:
        mock_check.return_value = _make_result(success=True)  # type: ignore[union-attr]
        assert test_rate_limit.main([]) == 0

    @patch("test_rate_limit.check_workflow_rate_limit")
    def test_low_rate_limit_returns_one(self, mock_check: object) -> None:
        mock_check.return_value = _make_result(  # type: ignore[union-attr]
            success=False, core_remaining=10
        )
        assert test_rate_limit.main([]) == 1

    @patch("test_rate_limit.check_workflow_rate_limit")
    def test_runtime_error_returns_one(self, mock_check: object) -> None:
        mock_check.side_effect = RuntimeError("API failure")  # type: ignore[union-attr]
        assert test_rate_limit.main([]) == 1

    @patch("test_rate_limit.check_workflow_rate_limit")
    def test_custom_thresholds_passed(self, mock_check: object) -> None:
        mock_check.return_value = _make_result(success=True)  # type: ignore[union-attr]
        test_rate_limit.main(
            ["--core-threshold", "200", "--graphql-threshold", "100"]
        )
        mock_check.assert_called_once_with(  # type: ignore[union-attr]
            resource_thresholds={"core": 200, "graphql": 100},
        )

    @patch("test_rate_limit.check_workflow_rate_limit")
    def test_writes_github_output(
        self, mock_check: object, tmp_path: object
    ) -> None:
        mock_check.return_value = _make_result(  # type: ignore[union-attr]
            success=True, core_remaining=4500
        )
        output_file = tmp_path / "github_output"  # type: ignore[operator]
        output_file.write_text("")  # type: ignore[union-attr]
        with patch.dict(
            os.environ, {"GITHUB_OUTPUT": str(output_file)}
        ):
            test_rate_limit.main([])
        content = output_file.read_text()  # type: ignore[union-attr]
        assert "core_remaining=4500" in content

    @patch("test_rate_limit.check_workflow_rate_limit")
    def test_writes_step_summary(
        self, mock_check: object, tmp_path: object
    ) -> None:
        mock_check.return_value = _make_result(success=True)  # type: ignore[union-attr]
        summary_file = tmp_path / "step_summary"  # type: ignore[operator]
        summary_file.write_text("")  # type: ignore[union-attr]
        with patch.dict(
            os.environ, {"GITHUB_STEP_SUMMARY": str(summary_file)}
        ):
            test_rate_limit.main([])
        content = summary_file.read_text()  # type: ignore[union-attr]
        assert "Rate Limit OK" in content

    @patch("test_rate_limit.check_workflow_rate_limit")
    def test_default_thresholds(self, mock_check: object) -> None:
        mock_check.return_value = _make_result(success=True)  # type: ignore[union-attr]
        test_rate_limit.main([])
        mock_check.assert_called_once_with(  # type: ignore[union-attr]
            resource_thresholds={"core": 100, "graphql": 50},
        )
