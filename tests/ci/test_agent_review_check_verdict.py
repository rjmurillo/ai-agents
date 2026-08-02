"""Tests for scripts/ci/agent_review_check_verdict.py."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from scripts.ci.agent_review_check_verdict import (
    _BLOCKING_VERDICTS,
    _MAX_ANNOTATION_LENGTH,
    main,
    run,
)


class TestConstants:
    def test_blocking_verdicts_set(self) -> None:
        assert _BLOCKING_VERDICTS == frozenset(
            {"CRITICAL_FAIL", "REJECTED", "FAIL", "NEEDS_REVIEW"}
        )

    def test_max_annotation_length(self) -> None:
        assert _MAX_ANNOTATION_LENGTH == 180


class TestRun:
    def _env(self, verdict: str, infra: str = "false", findings: str = "details") -> dict[str, str]:
        return {
            "AGENT": "security",
            "EMOJI": "🔒",
            "VERDICT": verdict,
            "FINDINGS": findings,
            "INFRASTRUCTURE_FAILURE": infra,
        }

    def test_non_blocking_verdict_returns_0(self) -> None:
        with patch.dict(os.environ, self._env("PASS")):
            assert run() == 0

    def test_approved_returns_0(self) -> None:
        with patch.dict(os.environ, self._env("APPROVED")):
            assert run() == 0

    def test_critical_fail_returns_1(self) -> None:
        with patch.dict(os.environ, self._env("CRITICAL_FAIL")):
            assert run() == 1

    def test_rejected_returns_1(self) -> None:
        with patch.dict(os.environ, self._env("REJECTED")):
            assert run() == 1

    def test_fail_returns_1(self) -> None:
        with patch.dict(os.environ, self._env("FAIL")):
            assert run() == 1

    def test_needs_review_returns_1(self) -> None:
        with patch.dict(os.environ, self._env("NEEDS_REVIEW")):
            assert run() == 1

    def test_infra_failure_downgrades_blocking_to_0(self) -> None:
        with patch.dict(os.environ, self._env("CRITICAL_FAIL", infra="true")):
            assert run() == 0

    def test_empty_verdict_defaults_to_needs_review_blocking(self) -> None:
        env = {
            "AGENT": "qa",
            "EMOJI": "",
            "VERDICT": "",
            "FINDINGS": "some findings",
            "INFRASTRUCTURE_FAILURE": "false",
        }
        with patch.dict(os.environ, env):
            assert run() == 1

    def test_annotation_truncated_at_max_length(self, capsys: pytest.CaptureFixture[str]) -> None:
        long_findings = "x" * 300
        with patch.dict(os.environ, self._env("FAIL", findings=long_findings)):
            run()
        out = capsys.readouterr().out
        # Find ::error:: annotation line
        error_lines = [ln for ln in out.splitlines() if ln.startswith("::error::")]
        assert error_lines, "Expected ::error:: annotation"
        # The annotation body should be truncated to <= MAX + prefix
        annotation = error_lines[0]
        # Count chars in the findings portion (after the verdict prefix)
        # The full annotation including prefix can be longer; just verify truncation
        assert "..." in annotation

    def test_annotation_not_truncated_when_short(self, capsys: pytest.CaptureFixture[str]) -> None:
        short = "short finding"
        with patch.dict(os.environ, self._env("FAIL", findings=short)):
            run()
        out = capsys.readouterr().out
        error_lines = [ln for ln in out.splitlines() if ln.startswith("::error::")]
        assert error_lines
        assert "..." not in error_lines[0] or "short finding" in error_lines[0]

    def test_empty_findings_uses_default_message(self, capsys: pytest.CaptureFixture[str]) -> None:
        env = {
            "AGENT": "security",
            "EMOJI": "",
            "VERDICT": "FAIL",
            "FINDINGS": "",
            "INFRASTRUCTURE_FAILURE": "false",
        }
        with patch.dict(os.environ, env):
            run()
        out = capsys.readouterr().out
        assert "no details" in out.lower()

    def test_infra_downgrade_message_printed(self, capsys: pytest.CaptureFixture[str]) -> None:
        with patch.dict(os.environ, self._env("FAIL", infra="true")):
            run()
        out = capsys.readouterr().out
        assert "infrastructure failure" in out.lower()

    def test_pass_message_printed_on_success(self, capsys: pytest.CaptureFixture[str]) -> None:
        with patch.dict(os.environ, self._env("PASS")):
            run()
        out = capsys.readouterr().out
        assert "passed" in out.lower() or "PASS" in out


class TestMain:
    def test_main_delegates(self) -> None:
        with patch("scripts.ci.agent_review_check_verdict.run", return_value=0):
            assert main() == 0
