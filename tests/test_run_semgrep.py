"""Tests for the semgrep scanner timeout and fail-closed behavior (issue #2810).

Scope: the subprocess timeout added to ``SemgrepScanner._run_semgrep`` and
fail-closed error mapping. A wedged semgrep process must not hang the pre-push
hook forever. A timeout exits 3, while other semgrep execution failures return a
blocking finding that makes ``run()`` exit 1.

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
        assert "Semgrep exited 2: stderr=boom; stdout=no stdout" in findings[0].message

    def test_execution_error_returncode_truncates_stderr(
        self, scanner: SemgrepScanner
    ) -> None:
        stderr = "x" * 600
        with patch(
            "scripts.security.run_semgrep.subprocess.run",
            return_value=_completed(2, stderr=stderr),
        ):
            findings = scanner._run_semgrep([Path("/repo/a.py")])
        assert len(findings[0].message) < len(stderr)
        assert "[truncated]" in findings[0].message
        assert "x" * 600 not in findings[0].message

    def test_execution_error_returncode_does_not_scan_past_prefix(
        self, scanner: SemgrepScanner
    ) -> None:
        stderr = (" " * 600) + "boom"
        with patch(
            "scripts.security.run_semgrep.subprocess.run",
            return_value=_completed(2, stderr=stderr),
        ):
            findings = scanner._run_semgrep([Path("/repo/a.py")])
        assert "[output begins with whitespace; truncated]" in findings[0].message
        assert "boom" not in findings[0].message

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
            return_value=_completed(0, stdout="not json", stderr="semgrep warning"),
        ):
            findings = scanner._run_semgrep([Path("/repo/a.py")])
        assert len(findings) == 1
        assert findings[0].check_id == "semgrep-scan-failure"
        assert findings[0].severity == "ERROR"
        assert "Semgrep JSON parse failed" in findings[0].message
        assert "stderr=semgrep warning" in findings[0].message
        assert "stdout=not json" in findings[0].message


class TestCompatibilityRuleExclusion:
    """The python36 and python37 compatibility rules must be excluded.

    requires-python = ">=3.14" (pyproject.toml). Those families produce
    guaranteed false positives on every compliant subprocess call in this repo
    and block pushes that satisfy tests/test_subprocess_text_encoding.py
    (issue #4223).
    """

    def test_cmd_excludes_python36_compatibility_family(
        self, scanner: SemgrepScanner
    ) -> None:
        with patch(
            "scripts.security.run_semgrep.subprocess.run",
            return_value=_completed(0, stdout='{"results": []}'),
        ) as run_mock:
            scanner._run_semgrep([Path("/repo/a.py")])

        cmd = run_mock.call_args.args[0]
        assert "--exclude-rule" in cmd, "semgrep command must carry --exclude-rule"
        # There may be multiple --exclude-rule flags; gather all values.
        exclusions = [
            cmd[i + 1]
            for i, flag in enumerate(cmd)
            if flag == "--exclude-rule" and i + 1 < len(cmd)
        ]
        assert any(
            e.startswith("python.lang.compatibility.python36") for e in exclusions
        ), (
            f"python36 compatibility family not excluded. Got exclusions: {exclusions}. "
            "The family produces guaranteed false positives on a 3.14+ floor (issue #4223)."
        )

    def test_cmd_excludes_python37_compatibility_family(
        self, scanner: SemgrepScanner
    ) -> None:
        with patch(
            "scripts.security.run_semgrep.subprocess.run",
            return_value=_completed(0, stdout='{"results": []}'),
        ) as run_mock:
            scanner._run_semgrep([Path("/repo/a.py")])

        cmd = run_mock.call_args.args[0]
        exclusions = [
            cmd[i + 1]
            for i, flag in enumerate(cmd)
            if flag == "--exclude-rule" and i + 1 < len(cmd)
        ]
        assert any(
            e.startswith("python.lang.compatibility.python37") for e in exclusions
        ), (
            f"python37 compatibility family not excluded. Got exclusions: {exclusions}. "
            "The family produces guaranteed false positives on a 3.14+ floor (issue #4223)."
        )

    def test_exclusions_do_not_remove_security_config(
        self, scanner: SemgrepScanner
    ) -> None:
        """Excluding compatibility rules must not remove the security config."""
        with patch(
            "scripts.security.run_semgrep.subprocess.run",
            return_value=_completed(0, stdout='{"results": []}'),
        ) as run_mock:
            scanner._run_semgrep([Path("/repo/a.py")])

        cmd = run_mock.call_args.args[0]
        assert "--config" in cmd, "semgrep command must still carry --config"
