"""Timeout hardening for the security gate (issue #2810).

A wedged network call on the pre-commit security path must not hang every
commit, and a pathological semgrep run must not hang the scan.

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

from scripts.security.invoke_precommit_security import PreCommitSecurityCheck
from scripts.security.run_semgrep import SemgrepScanError, SemgrepScanner


@pytest.fixture(autouse=True)
def _stub_pinned_executable():
    """Stub semgrep executable resolution for every test in this module.

    ``_resolve_semgrep_executable`` verifies the resolved binary against the
    pyproject.toml pin, which costs a ``semgrep --version`` subprocess. The
    tests below mock ``subprocess.run`` to script the *scan* call, so an
    unstubbed probe consumes that mock and the scan never runs. Resolution has
    its own coverage in ``tests/test_run_semgrep_pinning.py``; here it is an
    external boundary and is stubbed like one.
    """
    with patch(
        "scripts.security.run_semgrep._resolve_semgrep_executable",
        return_value="/pinned/semgrep",
    ):
        yield


def test_ensure_psscriptanalyzer_timeout_returns_false() -> None:
    # Construct before patching so the ctor's git repo-root lookup is real.
    check = PreCommitSecurityCheck(skip_codeql=True)
    timeout = subprocess.TimeoutExpired(cmd="pwsh", timeout=120)
    with patch("subprocess.run", side_effect=timeout):
        assert check._ensure_psscriptanalyzer() is False


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
    silent = subprocess.CompletedProcess(
        args=["semgrep"], returncode=0, stdout="", stderr=""
    )
    with patch("subprocess.run", return_value=silent):
        findings = scanner._run_semgrep([Path("example.py")])
    assert len(findings) == 1
    assert findings[0].severity == "ERROR"
    assert findings[0].check_id == "semgrep-scan-failure"
