"""Timeout hardening for the security gate and MCP client (issue #2810).

A wedged network call on the pre-commit security path must not hang every
commit, a pathological semgrep run must not hang the scan, and a wedged MCP
server must not block the reader forever (including on Windows, where
``select`` does not work on pipes).
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts.memory_sync.mcp_client import McpClient, McpError
from scripts.security.invoke_precommit_security import PreCommitSecurityCheck
from scripts.security.run_semgrep import SemgrepScanner


def test_ensure_psscriptanalyzer_timeout_returns_false() -> None:
    # Construct before patching so the ctor's git repo-root lookup is real.
    check = PreCommitSecurityCheck(skip_codeql=True)
    timeout = subprocess.TimeoutExpired(cmd="pwsh", timeout=120)
    with patch("subprocess.run", side_effect=timeout):
        assert check._ensure_psscriptanalyzer() is False


def test_run_semgrep_timeout_fails_closed() -> None:
    """A timed-out scan must yield a blocking ERROR finding, not a clean [].

    run() maps an empty findings list to PASS/exit 0, so returning [] on
    timeout would silently bypass the security gate.
    """
    scanner = SemgrepScanner()
    timeout = subprocess.TimeoutExpired(cmd="semgrep", timeout=300)
    with patch("subprocess.run", side_effect=timeout):
        findings = scanner._run_semgrep([Path("example.py")])
    assert len(findings) == 1
    assert findings[0].severity == "ERROR"
    assert findings[0].check_id == "semgrep-scan-failure"


def test_run_semgrep_subprocess_error_fails_closed() -> None:
    scanner = SemgrepScanner()
    err = subprocess.SubprocessError("spawn failed")
    with patch("subprocess.run", side_effect=err):
        findings = scanner._run_semgrep([Path("example.py")])
    assert len(findings) == 1
    assert findings[0].severity == "ERROR"


def test_mcp_win32_read_timeout_raises() -> None:
    client = McpClient(process=MagicMock(stderr=None), timeout=0.1)

    def _blocking_read(_fd: int, _n: int) -> bytes:
        time.sleep(1.0)
        return b"never"

    with patch("os.read", _blocking_read), pytest.raises(McpError, match="Timeout"):
        client._read_fd_with_timeout_win32(0)


def test_mcp_overall_deadline_raises() -> None:
    client = McpClient(process=MagicMock(stderr=None), timeout=0.05)
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
