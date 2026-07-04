"""Tests for pre-commit security gate timeout + fail-closed staging (issue #2810).

Scope (behavior changed by the fix):

1. ``_ensure_psscriptanalyzer`` now passes ``timeout=`` to both pwsh calls and
   returns False on ``subprocess.TimeoutExpired`` instead of hanging.
2. ``_fetch_codeql_alerts`` now passes ``timeout=`` to the ``gh api`` call; a
   timeout degrades to skip-with-warning (returns []) via the existing
   ``SubprocessError`` handler.
3. ``run()`` now blocks the commit (exit 1) when ``_stage_security_report``
   fails, closing the fail-open gap where the on-disk report satisfied
   ``_verify_security_report`` even though ``git add`` failed.

The git/gh/pwsh subprocesses and the report I/O are mocked; nothing external
runs.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts.security.invoke_precommit_security import (
    PSSCRIPTANALYZER_INSTALL_TIMEOUT_SECONDS,
    SUBPROCESS_TIMEOUT_SECONDS,
    PreCommitResult,
    PreCommitSecurityCheck,
    _powershell_single_quoted_literal,
)


@pytest.fixture
def check() -> PreCommitSecurityCheck:
    """A check instance with a stubbed repo root (no git call at init)."""
    with patch.object(
        PreCommitSecurityCheck, "_find_repo_root", return_value=Path("/repo")
    ):
        return PreCommitSecurityCheck(skip_codeql=True)


def _completed(returncode: int, stdout: str = "", stderr: str = "") -> MagicMock:
    result = MagicMock()
    result.returncode = returncode
    result.stdout = stdout
    result.stderr = stderr
    return result


class TestEnsurePsscriptanalyzerTimeout:
    """pwsh calls must time out rather than hang the commit forever."""

    def test_get_module_check_passes_timeout(
        self, check: PreCommitSecurityCheck
    ) -> None:
        with patch(
            "scripts.security.invoke_precommit_security.subprocess.run",
            return_value=_completed(0, stdout="PSScriptAnalyzer 1.0"),
        ) as run_mock:
            assert check._ensure_psscriptanalyzer() is True
        assert run_mock.call_args.kwargs["timeout"] == SUBPROCESS_TIMEOUT_SECONDS

    def test_get_module_timeout_returns_false(
        self, check: PreCommitSecurityCheck
    ) -> None:
        with patch(
            "scripts.security.invoke_precommit_security.subprocess.run",
            side_effect=subprocess.TimeoutExpired(
                cmd=["pwsh"],
                timeout=SUBPROCESS_TIMEOUT_SECONDS,
            ),
        ):
            assert check._ensure_psscriptanalyzer() is False

    def test_install_timeout_returns_false(
        self, check: PreCommitSecurityCheck
    ) -> None:
        # First call (Get-Module) succeeds but reports module absent; second
        # call (Install-Module) times out.
        side_effects = [
            _completed(0, stdout="no module here"),
            subprocess.TimeoutExpired(
                cmd=["pwsh"],
                timeout=PSSCRIPTANALYZER_INSTALL_TIMEOUT_SECONDS,
            ),
        ]
        with patch(
            "scripts.security.invoke_precommit_security.subprocess.run",
            side_effect=side_effects,
        ) as run_mock:
            assert check._ensure_psscriptanalyzer() is False

        assert (
            run_mock.call_args_list[1].kwargs["timeout"]
            == PSSCRIPTANALYZER_INSTALL_TIMEOUT_SECONDS
        )

    def test_pwsh_not_found_returns_false(
        self, check: PreCommitSecurityCheck
    ) -> None:
        with patch(
            "scripts.security.invoke_precommit_security.subprocess.run",
            side_effect=FileNotFoundError("pwsh"),
        ):
            assert check._ensure_psscriptanalyzer() is False


class TestFetchCodeqlAlertsTimeout:
    """The gh api network call must be time-bounded and degrade gracefully."""

    def test_gh_api_timeout_returns_empty(
        self, check: PreCommitSecurityCheck
    ) -> None:
        side_effects = [
            _completed(0, stdout="gh version 2.60"),  # gh --version probe
            subprocess.TimeoutExpired(cmd=["gh", "api"], timeout=30),  # gh api
        ]
        with (
            patch.object(
                check, "_get_github_context", return_value=("o", "r", "main")
            ),
            patch(
                "scripts.security.invoke_precommit_security.subprocess.run",
                side_effect=side_effects,
            ) as run_mock,
        ):
            assert check._fetch_codeql_alerts() == []
        # The gh api call (second invocation) carries an explicit timeout.
        assert run_mock.call_args_list[1].kwargs["timeout"] == 30


class TestRunPsscriptAnalyzer:
    """PowerShell file paths must be passed as literal paths."""

    def test_powershell_single_quoted_literal_escapes_quotes(self) -> None:
        assert _powershell_single_quoted_literal("O'Brien[1].ps1") == (
            "'O''Brien[1].ps1'"
        )

    def test_uses_literal_path_with_escaped_file_path(
        self, check: PreCommitSecurityCheck
    ) -> None:
        file_path = Path("/repo/O'Brien[1].ps1")
        with patch(
            "scripts.security.invoke_precommit_security.subprocess.run",
            return_value=_completed(0, stdout="null"),
        ) as run_mock:
            result = check._run_psscriptanalyzer([file_path])

        command = run_mock.call_args.args[0][3]
        assert result.passed is True
        assert "Invoke-ScriptAnalyzer -LiteralPath '/repo/O''Brien[1].ps1'" in command
        assert "Invoke-ScriptAnalyzer -Path" not in command


class TestRunStagingFailClosed:
    """A staging failure must block the commit, not pass on the on-disk file."""

    def _wire_common(self, check: PreCommitSecurityCheck) -> None:
        check.__dict__["_get_staged_powershell_files"] = MagicMock(
            return_value=[Path("/repo/a.ps1")]
        )
        check.__dict__["_check_critical_patterns"] = MagicMock(return_value=[])
        check.__dict__["_ensure_psscriptanalyzer"] = MagicMock(return_value=True)
        check.__dict__["_run_psscriptanalyzer"] = MagicMock(
            return_value=PreCommitResult(
                passed=True, findings=[], report_path=None
            )
        )
        check.__dict__["_generate_security_report"] = MagicMock(
            return_value=Path("/repo/.agents/security/SR-x.md")
        )

    def test_staging_failure_blocks_commit(
        self, check: PreCommitSecurityCheck
    ) -> None:
        self._wire_common(check)
        check.__dict__["_stage_security_report"] = MagicMock(return_value=False)
        assert check.run() == 1

    def test_staging_success_passes(
        self, check: PreCommitSecurityCheck
    ) -> None:
        self._wire_common(check)
        check.__dict__["_stage_security_report"] = MagicMock(return_value=True)
        check.__dict__["_verify_security_report"] = MagicMock(return_value=True)
        assert check.run() == 0


class TestStageSecurityReport:
    """Direct coverage of the staging helper's success/failure contract."""

    def test_returns_true_on_success(
        self, check: PreCommitSecurityCheck
    ) -> None:
        with patch(
            "scripts.security.invoke_precommit_security.subprocess.run",
            return_value=_completed(0),
        ):
            assert check._stage_security_report(Path("/repo/x.md")) is True

    def test_returns_false_on_git_add_failure(
        self, check: PreCommitSecurityCheck
    ) -> None:
        with patch(
            "scripts.security.invoke_precommit_security.subprocess.run",
            side_effect=subprocess.CalledProcessError(1, "git add"),
        ):
            assert check._stage_security_report(Path("/repo/x.md")) is False
