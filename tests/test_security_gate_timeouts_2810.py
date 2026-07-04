"""Timeout hardening for the security gate and MCP client (issue #2810).

A wedged network call on the pre-commit security path must not hang every
commit, a pathological semgrep run must not hang the scan, and a wedged MCP
server must not block the reader forever (including on Windows, where
``select`` does not work on pipes).
"""

from __future__ import annotations

import collections
import queue
import subprocess
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts.memory_sync.mcp_client import McpClient, McpError
from scripts.security.invoke_precommit_security import PreCommitSecurityCheck
from scripts.security.run_semgrep import SemgrepScanError, SemgrepScanner


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


def test_mcp_stdout_reader_eof_raises() -> None:
    """A closed stdout sentinel must raise McpError, not look like timeout."""
    client = McpClient.__new__(McpClient)
    client._timeout = 1
    client._read_queue = queue.Queue()
    client._stderr_lines = collections.deque()
    client._read_queue.put(None)
    with pytest.raises(McpError, match="closed stdout"):
        client._read_bytes(1)


def test_mcp_stdout_read_timeout_raises() -> None:
    client = McpClient.__new__(McpClient)
    client._timeout = 0.1
    client._read_queue = queue.Queue()
    with pytest.raises(McpError, match="Timeout"):
        client._read_bytes(0.01)


def test_mcp_overall_deadline_raises() -> None:
    client = McpClient(process=MagicMock(stdout=None, stderr=None), timeout=0.05)
    body = b'{"jsonrpc":"2.0","method":"notify"}'
    frame = f"Content-Length: {len(body)}\r\n\r\n".encode() + body

    def _slow_notification(_fd: int) -> bytes:
        time.sleep(0.03)
        return frame

    with (
        patch.object(client, "_read_bytes", side_effect=_slow_notification),
        pytest.raises(McpError, match="deadline"),
    ):
        client._read_response(expected_id=1)
