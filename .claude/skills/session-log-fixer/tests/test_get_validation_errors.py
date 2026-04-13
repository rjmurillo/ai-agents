#!/usr/bin/env python3
"""Tests for session-log-fixer skill get_validation_errors.py."""

from __future__ import annotations

import importlib
import importlib.util
import os
import subprocess
from unittest import mock

import pytest

_SCRIPT = os.path.join(
    os.path.dirname(__file__), "..", "scripts", "get_validation_errors.py",
)


def _load_module():
    spec = importlib.util.spec_from_file_location("get_validation_errors", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestParseJobSummary:
    def test_parses_overall_verdict(self):
        mod = _load_module()
        summary = "Overall Verdict: **CRITICAL_FAIL**\n1 MUST requirement(s) not met"
        result = mod._parse_job_summary(summary)
        assert result["overall_verdict"] == "CRITICAL_FAIL"
        assert result["must_failure_count"] == 1

    def test_parses_non_compliant_sessions(self):
        mod = _load_module()
        summary = (
            "| Session File | Verdict | MUST Failures |\n"
            "|:---|:---|:---:|\n"
            "| `2025-12-29-session-11.md` | NON_COMPLIANT | 2 |\n"
        )
        result = mod._parse_job_summary(summary)
        assert len(result["non_compliant_sessions"]) == 1
        assert result["non_compliant_sessions"][0]["file"] == "2025-12-29-session-11.md"
        assert result["non_compliant_sessions"][0]["must_failures"] == 2

    def test_empty_summary(self):
        mod = _load_module()
        result = mod._parse_job_summary("")
        assert result["overall_verdict"] is None
        assert result["must_failure_count"] == 0
        assert result["non_compliant_sessions"] == []


class TestMainFunction:
    def test_requires_run_id_or_pull_request(self):
        mod = _load_module()
        with pytest.raises(SystemExit):
            mod.main([])

    def test_run_id_not_found_returns_1(self):
        mod = _load_module()

        def mock_run(cmd, **kwargs):
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="not found")

        with mock.patch("subprocess.run", side_effect=mock_run):
            result = mod.main(["--run-id", "999999"])

        assert result == 1

    def test_no_validation_errors_returns_2(self):
        mod = _load_module()

        def mock_run(cmd, **kwargs):
            return subprocess.CompletedProcess(cmd, 0, stdout="All checks passed", stderr="")

        with mock.patch("subprocess.run", side_effect=mock_run):
            result = mod.main(["--run-id", "12345"])

        assert result == 2
