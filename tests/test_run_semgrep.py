"""Tests for the semgrep scanner timeout and fail-closed behavior (issue #2810).

Scope: the subprocess timeout added to ``SemgrepScanner._run_semgrep`` and the
fail-closed mapping to exit code 3 in ``run()``. A wedged semgrep process must
not hang the pre-push hook forever, and a timeout must NOT be reported as a
clean "no findings" pass. Any semgrep execution failure is a blocking finding.

External boundary (the semgrep subprocess) is mocked; no real semgrep runs.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts.security.run_semgrep import (
    SemgrepScanError,
    SemgrepScanner,
)


@pytest.fixture
def scanner() -> SemgrepScanner:
    """A scanner instance with a stubbed repo root (no git call)."""
    with patch.object(
        SemgrepScanner, "_find_repo_root", return_value=Path("/repo")
    ):
        return SemgrepScanner()


def _completed(returncode: int, stdout: str = "", stderr: str = "") -> MagicMock:
    result = MagicMock()
    result.returncode = returncode
    result.stdout = stdout
    result.stderr = stderr
    return result


class TestRunSemgrepTimeout:
    """Timeout path: fail closed, never a silent clean pass."""

    def test_timeout_raises_scan_error(self, scanner: SemgrepScanner) -> None:
        with patch(
            "scripts.security.run_semgrep.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd=["semgrep"], timeout=300),
        ):
            with pytest.raises(SemgrepScanError, match="timed out"):
                scanner._run_semgrep([Path("/repo/a.py")])

    def test_subprocess_called_with_timeout(self, scanner: SemgrepScanner) -> None:
        with patch(
            "scripts.security.run_semgrep.subprocess.run",
            return_value=_completed(0, stdout='{"results": []}'),
        ) as run_mock:
            scanner._run_semgrep([Path("/repo/a.py")])
        assert run_mock.call_args.kwargs["timeout"] == (
            SemgrepScanner.SCAN_TIMEOUT_SECONDS
        )

    def test_run_maps_timeout_to_exit_3(self, scanner: SemgrepScanner) -> None:
        with (
            patch.object(scanner, "_check_semgrep_installed", return_value=True),
            patch.object(
                scanner, "_get_changed_files", return_value=[Path("/repo/a.py")]
            ),
            patch.object(
                scanner,
                "_run_semgrep",
                side_effect=SemgrepScanError("Semgrep timed out after 300s"),
            ),
        ):
            assert scanner.run() == 3


class TestRunSemgrepHappyPath:
    """Positive: findings are parsed from semgrep JSON output."""

    def test_parses_findings(self, scanner: SemgrepScanner) -> None:
        payload = {
            "results": [
                {
                    "check_id": "python.lang.security.audit.dangerous-exec",
                    "path": "a.py",
                    "start": {"line": 12},
                    "extra": {
                        "severity": "ERROR",
                        "message": "dangerous exec",
                        "metadata": {"cwe": ["CWE-78"], "owasp": ["A03"]},
                    },
                }
            ]
        }
        with patch(
            "scripts.security.run_semgrep.subprocess.run",
            return_value=_completed(1, stdout=json.dumps(payload)),
        ):
            findings = scanner._run_semgrep([Path("/repo/a.py")])
        assert len(findings) == 1
        assert findings[0].check_id.endswith("dangerous-exec")
        assert findings[0].severity == "ERROR"
        assert findings[0].cwe == ["CWE-78"]


class TestRunSemgrepFailClosed:
    """Negative / edge: non-timeout error paths also block the scan."""

    def test_empty_file_list_returns_empty(self, scanner: SemgrepScanner) -> None:
        with patch("scripts.security.run_semgrep.subprocess.run") as run_mock:
            assert scanner._run_semgrep([]) == []
        run_mock.assert_not_called()

    def test_execution_error_returncode_returns_scan_failure(
        self, scanner: SemgrepScanner
    ) -> None:
        with patch(
            "scripts.security.run_semgrep.subprocess.run",
            return_value=_completed(2, stderr="boom"),
        ):
            findings = scanner._run_semgrep([Path("/repo/a.py")])
        assert len(findings) == 1
        assert findings[0].check_id == "semgrep-scan-failure"
        assert findings[0].severity == "ERROR"
        assert "Semgrep exited 2: boom" in findings[0].message

    def test_generic_subprocess_error_returns_scan_failure(
        self, scanner: SemgrepScanner
    ) -> None:
        with patch(
            "scripts.security.run_semgrep.subprocess.run",
            side_effect=subprocess.SubprocessError("generic failure"),
        ):
            findings = scanner._run_semgrep([Path("/repo/a.py")])
        assert len(findings) == 1
        assert findings[0].check_id == "semgrep-scan-failure"
        assert findings[0].severity == "ERROR"
        assert "generic failure" in findings[0].message

    def test_invalid_json_returns_scan_failure(self, scanner: SemgrepScanner) -> None:
        with patch(
            "scripts.security.run_semgrep.subprocess.run",
            return_value=_completed(0, stdout="not json"),
        ):
            findings = scanner._run_semgrep([Path("/repo/a.py")])
        assert len(findings) == 1
        assert findings[0].check_id == "semgrep-scan-failure"
        assert findings[0].severity == "ERROR"
        assert "Semgrep scan failed" in findings[0].message
