"""Timeout hardening for the security gate (issue #2810).

A pathological semgrep run must not hang the pre-push scan. The surviving
cases cover ``run_semgrep`` only. A PSScriptAnalyzer timeout case went with
the retired ``invoke_precommit_security.py`` script.

This module also covered an MCP stdio client's read timeouts, including the
Windows case where ``select`` does not work on pipes. That client was the
transport for a memory backend decommissioned in issue #5574 and is deleted,
so those three cases went with it rather than being ported to a client that
no longer exists.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.security.run_semgrep import SemgrepScanError, SemgrepScanner
from tests.semgrep_fixtures import (
    stub_pinned_semgrep_executable,  # noqa: F401  (fixture, applied by usefixtures below)
)

pytestmark = pytest.mark.usefixtures("stub_pinned_semgrep_executable")


def test_run_semgrep_timeout_fails_closed() -> None:
    """A timed-out scan must raise a fail-closed scan error, not return [].

    run() maps an empty findings list to PASS/exit 0, so returning [] on
    timeout would silently bypass the security gate.
    """
    scanner = SemgrepScanner()
    timeout = subprocess.TimeoutExpired(cmd="semgrep", timeout=300)
    with patch("subprocess.run", side_effect=timeout):
        with pytest.raises(SemgrepScanError, match="timed out"):
            scanner._run_semgrep([Path("example.py")])


def test_run_semgrep_subprocess_error_fails_closed() -> None:
    scanner = SemgrepScanner()
    err = subprocess.SubprocessError("spawn failed")
    with patch("subprocess.run", side_effect=err):
        findings = scanner._run_semgrep([Path("example.py")])
    assert len(findings) == 1
    assert findings[0].severity == "ERROR"


def test_run_semgrep_nonzero_exit_fails_closed() -> None:
    """semgrep exit codes other than 0/1 (bad config, crash) must yield a
    blocking ERROR finding, not a clean [] that run() maps to PASS."""
    scanner = SemgrepScanner()
    crashed = subprocess.CompletedProcess(
        args=["semgrep"], returncode=2, stdout="", stderr="bad config"
    )
    with patch("subprocess.run", return_value=crashed):
        findings = scanner._run_semgrep([Path("example.py")])
    assert len(findings) == 1
    assert findings[0].severity == "ERROR"
    assert findings[0].check_id == "semgrep-scan-failure"
    assert "exited 2" in findings[0].message


def test_run_semgrep_empty_stdout_fails_closed() -> None:
    """A 0/1 exit with no JSON output means the scan did not really run."""
    scanner = SemgrepScanner()
    silent = subprocess.CompletedProcess(args=["semgrep"], returncode=0, stdout="", stderr="")
    with patch("subprocess.run", return_value=silent):
        findings = scanner._run_semgrep([Path("example.py")])
    assert len(findings) == 1
    assert findings[0].severity == "ERROR"
    assert findings[0].check_id == "semgrep-scan-failure"
