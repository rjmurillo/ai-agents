"""Tests for scripts/quality_gate/consume_pytest_signal.py.

Covers:
- Positive: resolves PASS/FAIL from a completed pytest.yml run
- Negative: config errors (missing repo, pr, sha)
- Edge: PENDING with retry exhaustion, UNKNOWN, deadline=0 (no retry)
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.quality_gate import consume_pytest_signal as mod
from scripts.quality_gate.resolve_pytest_signal import Resolution

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_main(args: list[str], env: dict[str, str] | None = None) -> int:
    """Run main() with the given args, clearing env vars."""
    clean_env = {
        "GITHUB_REPOSITORY": "",
        "PR_NUMBER": "",
        "EXPECTED_HEAD_SHA": "",
        "GITHUB_OUTPUT": "",
    }
    if env:
        clean_env.update(env)
    with patch.dict(os.environ, clean_env, clear=False):
        return mod.main(args)


# ---------------------------------------------------------------------------
# Config error tests (negative)
# ---------------------------------------------------------------------------


class TestConfigErrors:
    def test_missing_repo(self) -> None:
        rc = _run_main(["--pr", "123", "--expected-head-sha", "a" * 40])
        assert rc == 2

    def test_missing_pr(self) -> None:
        rc = _run_main(["--repo", "owner/repo", "--expected-head-sha", "a" * 40])
        assert rc == 2

    def test_missing_sha(self) -> None:
        rc = _run_main(["--repo", "owner/repo", "--pr", "123"])
        assert rc == 2

    def test_invalid_sha(self) -> None:
        rc = _run_main(["--repo", "owner/repo", "--pr", "123", "--expected-head-sha", "short"])
        assert rc == 2

    def test_invalid_timeout(self) -> None:
        rc = _run_main(
            [
                "--repo",
                "owner/repo",
                "--pr",
                "123",
                "--expected-head-sha",
                "a" * 40,
                "--timeout",
                "-1",
            ]
        )
        assert rc == 2


# ---------------------------------------------------------------------------
# Resolution tests (positive)
# ---------------------------------------------------------------------------


class TestResolution:
    @pytest.fixture()
    def output_file(self, tmp_path: Path) -> Path:
        p = tmp_path / "github_output"
        p.touch()
        return p

    def test_resolves_pass(self, output_file: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """When pytest.yml reports PASS, outputs match run_pytest.py format."""
        monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))
        monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
        monkeypatch.setenv("PR_NUMBER", "42")
        monkeypatch.setenv("EXPECTED_HEAD_SHA", "a" * 40)
        resolution = Resolution(
            status="PASS", reason="1 executor job(s) of 1 matching job(s) resolve to PASS"
        )

        with patch.object(mod, "_wait_for_resolution", return_value=resolution):
            rc = mod.main(
                [
                    "--repo",
                    "owner/repo",
                    "--pr",
                    "42",
                    "--expected-head-sha",
                    "a" * 40,
                ]
            )

        assert rc == 0
        content = output_file.read_text()
        assert "pytest_status=PASS" in content
        assert "pytest_summary=All tests passed (resolved from pytest.yml)" in content

    def test_resolves_fail(self, output_file: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """When pytest.yml reports FAIL, outputs match."""
        monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))
        resolution = Resolution(status="FAIL", reason="failure")

        with patch.object(mod, "_wait_for_resolution", return_value=resolution):
            rc = mod.main(
                [
                    "--repo",
                    "owner/repo",
                    "--pr",
                    "42",
                    "--expected-head-sha",
                    "a" * 40,
                ]
            )

        assert rc == 0
        content = output_file.read_text()
        assert "pytest_status=FAIL" in content
        assert "pytest_summary=Tests failed (resolved from pytest.yml)" in content

    def test_resolves_skipped(self, output_file: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """When pytest.yml reports SKIPPED (pass-through), outputs match."""
        monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))
        resolution = Resolution(status="SKIPPED", reason="pass-through")

        with patch.object(mod, "_wait_for_resolution", return_value=resolution):
            rc = mod.main(
                [
                    "--repo",
                    "owner/repo",
                    "--pr",
                    "42",
                    "--expected-head-sha",
                    "a" * 40,
                ]
            )

        assert rc == 0
        content = output_file.read_text()
        assert "pytest_status=SKIPPED" in content

    def test_no_github_output_still_succeeds(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Script succeeds even when GITHUB_OUTPUT is unset (local dev)."""
        monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
        resolution = Resolution(status="PASS", reason="ok")

        with patch.object(mod, "_wait_for_resolution", return_value=resolution):
            rc = mod.main(
                [
                    "--repo",
                    "owner/repo",
                    "--pr",
                    "42",
                    "--expected-head-sha",
                    "a" * 40,
                ]
            )

        assert rc == 0


# ---------------------------------------------------------------------------
# Retry/deadline tests (edge)
# ---------------------------------------------------------------------------


class TestRetryBehavior:
    def test_pending_retries_then_resolves(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """PENDING on first call, PASS on second - verify retry works."""
        monkeypatch.setenv("GITHUB_OUTPUT", "")
        call_count = {"n": 0}
        pending = Resolution(status="PENDING", reason="no run yet")
        passed = Resolution(status="PASS", reason="executor")

        def mock_resolve(*args, **kwargs):
            call_count["n"] += 1
            return pending if call_count["n"] == 1 else passed

        with patch.object(mod, "resolve", side_effect=mock_resolve):
            with patch("time.sleep"):
                result = mod._wait_for_resolution(
                    None,
                    repo="o/r",
                    pr="1",
                    expected_sha="a" * 40,
                    workflow="pytest.yml",
                    job_name="Run Python Tests",
                    deadline=30.0,
                    poll_interval=1.0,
                )

        assert result.status == "PASS"
        assert call_count["n"] == 2

    def test_deadline_zero_no_retry(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """With deadline=0, PENDING is returned without retry."""
        monkeypatch.setenv("GITHUB_OUTPUT", "")
        pending = Resolution(status="PENDING", reason="no run yet")

        with patch.object(mod, "resolve", return_value=pending):
            result = mod._wait_for_resolution(
                None,
                repo="o/r",
                pr="1",
                expected_sha="a" * 40,
                workflow="pytest.yml",
                job_name="Run Python Tests",
                deadline=0.0,
                poll_interval=1.0,
            )

        assert result.status == "PENDING"

    def test_unknown_status_not_retried(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """UNKNOWN (API error) is NOT retried - only transient states trigger retry."""
        monkeypatch.setenv("GITHUB_OUTPUT", "")
        unknown = Resolution(status="UNKNOWN", reason="API error")

        with patch.object(mod, "resolve", return_value=unknown):
            result = mod._wait_for_resolution(
                None,
                repo="o/r",
                pr="1",
                expected_sha="a" * 40,
                workflow="pytest.yml",
                job_name="Run Python Tests",
                deadline=30.0,
                poll_interval=1.0,
            )

        assert result.status == "UNKNOWN"

    def test_unknown_no_job_retries_then_resolves(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """UNKNOWN with no-job reason is transient (job not yet created)."""
        monkeypatch.setenv("GITHUB_OUTPUT", "")
        call_count = {"n": 0}
        no_job = Resolution(status="UNKNOWN", reason=mod.REASON_NO_JOB)
        passed = Resolution(status="PASS", reason="executor")

        def mock_resolve(*args, **kwargs):
            call_count["n"] += 1
            return no_job if call_count["n"] == 1 else passed

        with patch.object(mod, "resolve", side_effect=mock_resolve):
            with patch("time.sleep"):
                result = mod._wait_for_resolution(
                    None,
                    repo="o/r",
                    pr="1",
                    expected_sha="a" * 40,
                    workflow="pytest.yml",
                    job_name="Run Python Tests",
                    deadline=30.0,
                    poll_interval=1.0,
                )

        assert result.status == "PASS"
        assert call_count["n"] == 2


# ---------------------------------------------------------------------------
# format_summary tests
# ---------------------------------------------------------------------------


class TestFormatSummary:
    def test_known_statuses_have_templates(self) -> None:
        for status in ("PASS", "FAIL", "SKIPPED", "PENDING"):
            result = mod.format_summary(Resolution(status=status, reason="x"))
            assert result  # Each has a non-empty template

    def test_unknown_status_includes_reason(self) -> None:
        result = mod.format_summary(Resolution(status="STALE", reason="head moved"))
        assert "STALE" in result
        assert "head moved" in result
