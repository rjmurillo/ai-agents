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

import json
import re
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts.security.invoke_precommit_security import (
    PSSCRIPTANALYZER_INSTALL_TIMEOUT_SECONDS,
    SUBPROCESS_TIMEOUT_SECONDS,
    PreCommitResult,
    PreCommitSecurityCheck,
    SecurityFinding,
    _git_environment,
    _powershell_extension,
    _powershell_single_quoted_literal,
)


@pytest.fixture
def check() -> PreCommitSecurityCheck:
    """A check instance with a stubbed repo root (no git call at init)."""
    with patch.object(
        PreCommitSecurityCheck, "_find_repo_root", return_value=Path("/repo")
    ):
        return PreCommitSecurityCheck(skip_codeql=True)


def _completed(
    returncode: int,
    stdout: str | bytes = "",
    stderr: str = "",
) -> MagicMock:
    result = MagicMock()
    result.returncode = returncode
    result.stdout = stdout
    result.stderr = stderr
    return result


def test_generated_report_uses_project_toolkit_root(tmp_path: Path) -> None:
    """Generated security work products never recreate the legacy root."""
    with patch.object(PreCommitSecurityCheck, "_find_repo_root", return_value=tmp_path):
        security_check = PreCommitSecurityCheck(skip_codeql=True)
    with patch(
        "scripts.security.invoke_precommit_security.subprocess.run",
        return_value=_completed(0, stdout="feature/test\n"),
    ):
        report = security_check._generate_security_report([], [])

    assert report is not None
    assert report.parent == tmp_path / ".project-toolkit" / "security"
    assert report.is_file()
    assert not (tmp_path / ".agents").exists()


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

    def test_git_environment_disables_replacement_refs(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("TEST_MARKER", "present")

        environment = _git_environment()

        assert environment["GIT_NO_REPLACE_OBJECTS"] == "1"
        assert environment["TEST_MARKER"] == "present"

    @pytest.mark.parametrize(
        ("file_name", "expected"),
        [
            ("script.ps1", ".ps1"),
            ("MODULE.PSM1", ".psm1"),
            (".psd1", ".psd1"),
            ("script.py", None),
        ],
    )
    def test_powershell_extension_matches_exact_dot_and_mixed_case_names(
        self, file_name: str, expected: str | None
    ) -> None:
        assert _powershell_extension(Path(file_name)) == expected

    def test_powershell_single_quoted_literal_escapes_quotes(self) -> None:
        assert _powershell_single_quoted_literal("O'Brien[1].ps1") == (
            "'O''Brien[1].ps1'"
        )

    def test_uses_literal_path_with_escaped_file_path(
        self, check: PreCommitSecurityCheck
    ) -> None:
        file_path = Path("/repo/O'Brien[1].ps1")
        staged_content = b"Write-Host 'staged'"
        analyzed_content: list[bytes] = []

        def run_analyzer(command: list[str], **_: object) -> MagicMock:
            analyzer_command = command[3]
            match = re.search(r"-LiteralPath '([^']+)'", analyzer_command)
            assert match is not None
            analyzed_content.append(Path(match.group(1)).read_bytes())
            return _completed(0, stdout="null")

        with (
            patch.object(check, "_read_staged_blob", return_value=staged_content),
            patch(
                "scripts.security.invoke_precommit_security.subprocess.run",
                side_effect=run_analyzer,
            ) as run_mock,
        ):
            result = check._run_psscriptanalyzer([file_path])

        command = run_mock.call_args.args[0][3]
        assert result.passed is True
        assert "Invoke-ScriptAnalyzer -LiteralPath" in command
        assert str(file_path) not in command
        assert "Invoke-ScriptAnalyzer -Path" not in command
        assert "$ErrorActionPreference = 'Stop'" in command
        assert "-ErrorAction Stop" in command
        assert analyzed_content == [staged_content]

    def test_analyzer_failure_blocks_commit(
        self, check: PreCommitSecurityCheck
    ) -> None:
        file_path = Path("/repo/script.ps1")

        with (
            patch.object(check, "_read_staged_blob", return_value=b"Write-Host test"),
            patch(
                "scripts.security.invoke_precommit_security.subprocess.run",
                return_value=_completed(1, stderr="analyzer failed"),
            ),
        ):
            result = check._run_psscriptanalyzer([file_path])

        assert result.passed is False
        assert "PSScriptAnalyzer failed" in (result.error_message or "")

    def test_analyzer_stderr_blocks_commit_even_with_zero_exit(
        self, check: PreCommitSecurityCheck
    ) -> None:
        file_path = Path("/repo/script.ps1")

        with (
            patch.object(check, "_read_staged_blob", return_value=b"Write-Host test"),
            patch(
                "scripts.security.invoke_precommit_security.subprocess.run",
                return_value=_completed(0, stdout="null", stderr="non-terminating error"),
            ),
        ):
            result = check._run_psscriptanalyzer([file_path])

        assert result.passed is False
        assert "PSScriptAnalyzer failed" in (result.error_message or "")

    def test_missing_staged_blobs_fail_with_bounded_error_message(
        self, check: PreCommitSecurityCheck
    ) -> None:
        files = [Path(f"/repo/script-{index}.ps1") for index in range(6)]

        with patch.object(check, "_read_staged_blob", return_value=None):
            result = check._run_psscriptanalyzer(files)

        assert result.passed is False
        assert "(and 1 more)" in (result.error_message or "")

    def test_non_powershell_input_fails_closed(
        self, check: PreCommitSecurityCheck
    ) -> None:
        with patch.object(check, "_read_staged_blob", return_value=b"text"):
            result = check._run_psscriptanalyzer([Path("/repo/README.md")])

        assert result.passed is False

    def test_invalid_analyzer_json_fails_closed(
        self, check: PreCommitSecurityCheck
    ) -> None:
        with (
            patch.object(check, "_read_staged_blob", return_value=b"Write-Host test"),
            patch(
                "scripts.security.invoke_precommit_security.subprocess.run",
                return_value=_completed(0, stdout="{"),
            ),
        ):
            result = check._run_psscriptanalyzer([Path("/repo/script.ps1")])

        assert result.passed is False

    def test_analyzer_timeout_fails_closed(
        self, check: PreCommitSecurityCheck
    ) -> None:
        with (
            patch.object(check, "_read_staged_blob", return_value=b"Write-Host test"),
            patch(
                "scripts.security.invoke_precommit_security.subprocess.run",
                side_effect=subprocess.TimeoutExpired(["pwsh"], 60),
            ),
        ):
            result = check._run_psscriptanalyzer([Path("/repo/script.ps1")])

        assert result.passed is False

    def test_staged_copy_write_failure_fails_closed(
        self, check: PreCommitSecurityCheck
    ) -> None:
        with (
            patch.object(check, "_read_staged_blob", return_value=b"Write-Host test"),
            patch.object(Path, "write_bytes", side_effect=OSError("disk full")),
        ):
            result = check._run_psscriptanalyzer([Path("/repo/script.ps1")])

        assert result.passed is False

    @pytest.mark.parametrize("as_list", [False, True])
    def test_analyzer_findings_keep_original_path_and_block(
        self, check: PreCommitSecurityCheck, as_list: bool
    ) -> None:
        finding = {
            "RuleName": "PSAvoidUsingInvokeExpression",
            "Severity": "Error",
            "Message": "unsafe",
            "Line": 7,
        }
        stdout = json.dumps([finding] if as_list else finding)

        with (
            patch.object(check, "_read_staged_blob", return_value=b"Invoke-Expression x"),
            patch(
                "scripts.security.invoke_precommit_security.subprocess.run",
                return_value=_completed(0, stdout=stdout),
            ),
        ):
            result = check._run_psscriptanalyzer([Path("/repo/script.ps1")])

        assert result.passed is False
        assert result.findings[0].file_path == "script.ps1"
        assert result.findings[0].cwe_id == "CWE-94"


class TestRunStagingFailClosed:
    """A staging failure must block the commit, not pass on the on-disk file."""

    def _wire_common(self, check: PreCommitSecurityCheck) -> None:
        check.__dict__["_get_staged_files"] = MagicMock(
            return_value=[Path("/repo/a.ps1")]
        )
        check.__dict__["_get_staged_present_files"] = MagicMock(
            return_value=[Path("/repo/a.ps1")]
        )
        check.__dict__["_get_unmerged_files"] = MagicMock(return_value=[])
        check.__dict__["_check_critical_patterns"] = MagicMock(return_value=[])
        check.__dict__["_ensure_psscriptanalyzer"] = MagicMock(return_value=True)
        check.__dict__["_run_psscriptanalyzer"] = MagicMock(
            return_value=PreCommitResult(
                passed=True, findings=[], report_path=None
            )
        )
        check.__dict__["_generate_security_report"] = MagicMock(
            return_value=Path("/repo/.project-toolkit/security/SR-x.md")
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

    @pytest.mark.parametrize(
        "missing_getter",
        ["_get_staged_files", "_get_staged_present_files", "_get_unmerged_files"],
    )
    def test_staged_file_lookup_failure_blocks(
        self, check: PreCommitSecurityCheck, missing_getter: str
    ) -> None:
        getters: dict[str, list[Path] | None] = {
            "_get_staged_files": [Path("/repo/a.ps1")],
            "_get_staged_present_files": [Path("/repo/a.ps1")],
            "_get_unmerged_files": [],
        }
        getters[missing_getter] = None
        for name, value in getters.items():
            check.__dict__[name] = MagicMock(return_value=value)

        assert check.run() == 1

    def test_no_staged_files_passes(self, check: PreCommitSecurityCheck) -> None:
        check.__dict__["_get_staged_files"] = MagicMock(return_value=[])
        check.__dict__["_get_staged_present_files"] = MagicMock(return_value=[])
        check.__dict__["_get_unmerged_files"] = MagicMock(return_value=[])

        assert check.run() == 0

    def test_noncritical_non_powershell_files_pass(
        self, check: PreCommitSecurityCheck
    ) -> None:
        readme = Path("/repo/README.md")
        check.__dict__["_get_staged_files"] = MagicMock(return_value=[readme])
        check.__dict__["_get_staged_present_files"] = MagicMock(return_value=[readme])
        check.__dict__["_get_unmerged_files"] = MagicMock(return_value=[])
        check.__dict__["_check_critical_patterns"] = MagicMock(return_value=[])

        assert check.run() == 0

    def test_missing_psscriptanalyzer_blocks(
        self, check: PreCommitSecurityCheck
    ) -> None:
        self._wire_common(check)
        check.__dict__["_ensure_psscriptanalyzer"] = MagicMock(return_value=False)

        assert check.run() == 1

    def test_exact_dot_powershell_filename_is_analyzed(
        self, check: PreCommitSecurityCheck
    ) -> None:
        script = Path("/repo/.ps1")
        self._wire_common(check)
        check.__dict__["_get_staged_files"] = MagicMock(return_value=[script])
        check.__dict__["_get_staged_present_files"] = MagicMock(return_value=[script])
        analyzer = MagicMock(
            return_value=PreCommitResult(
                passed=True,
                findings=[],
                report_path=None,
            )
        )
        check.__dict__["_run_psscriptanalyzer"] = analyzer
        check.__dict__["_stage_security_report"] = MagicMock(return_value=True)
        check.__dict__["_verify_security_report"] = MagicMock(return_value=True)

        assert check.run() == 0
        analyzer.assert_called_once_with([script])

    def test_analyzer_findings_block_and_are_logged(
        self, check: PreCommitSecurityCheck
    ) -> None:
        self._wire_common(check)
        finding = SecurityFinding(
            rule_name="Rule",
            severity="HIGH",
            message="unsafe",
            file_path="a.ps1",
            line_number=7,
        )
        check.__dict__["_run_psscriptanalyzer"] = MagicMock(
            return_value=PreCommitResult(
                passed=False,
                findings=[finding],
                report_path=None,
            )
        )

        assert check.run() == 1

    def test_dry_run_continues_after_analyzer_findings(
        self, check: PreCommitSecurityCheck
    ) -> None:
        check.dry_run = True
        self._wire_common(check)
        check.__dict__["_run_psscriptanalyzer"] = MagicMock(
            return_value=PreCommitResult(
                passed=False,
                findings=[],
                report_path=None,
            )
        )
        check.__dict__["_generate_security_report"] = MagicMock(return_value=None)
        check.__dict__["_verify_security_report"] = MagicMock(return_value=False)

        assert check.run() == 0

    def test_missing_security_report_blocks(
        self, check: PreCommitSecurityCheck
    ) -> None:
        self._wire_common(check)
        check.__dict__["_generate_security_report"] = MagicMock(return_value=None)
        check.__dict__["_verify_security_report"] = MagicMock(return_value=False)

        assert check.run() == 1


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


class TestCriticalHookPaths:
    @staticmethod
    def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            check=True,
            encoding="utf-8",
        )

    def test_staged_path_timeout_returns_none(
        self, check: PreCommitSecurityCheck
    ) -> None:
        with patch(
            "scripts.security.invoke_precommit_security.subprocess.run",
            side_effect=subprocess.TimeoutExpired(["git", "diff"], 60),
        ):
            assert check._get_staged_files() is None

    def test_staged_path_process_error_returns_none(
        self, check: PreCommitSecurityCheck
    ) -> None:
        with patch(
            "scripts.security.invoke_precommit_security.subprocess.run",
            side_effect=OSError("git unavailable"),
        ):
            assert check._get_staged_files() is None

    def test_staged_paths_include_rename_sources_and_deletions(
        self, tmp_path: Path
    ) -> None:
        self._git(tmp_path, "init", "--quiet")
        self._git(tmp_path, "config", "user.email", "test@example.com")
        self._git(tmp_path, "config", "user.name", "Test")
        self._git(tmp_path, "config", "core.hooksPath", ".git/no-hooks")
        (tmp_path / "lefthook.yml").write_text("pre-commit: {}\n", encoding="utf-8")
        (tmp_path / "script.ps1").write_text("Write-Host test\n", encoding="utf-8")
        self._git(tmp_path, "add", ".")
        self._git(tmp_path, "commit", "--quiet", "-m", "initial")

        (tmp_path / "lefthook.yml").rename(tmp_path / "renamed.yml")
        (tmp_path / "script.ps1").unlink()
        self._git(tmp_path, "add", "--all")

        with patch.object(
            PreCommitSecurityCheck,
            "_find_repo_root",
            return_value=tmp_path,
        ):
            check = PreCommitSecurityCheck(skip_codeql=True)

        assert set(check._get_staged_files() or []) == {
            tmp_path / "lefthook.yml",
            tmp_path / "renamed.yml",
            tmp_path / "script.ps1",
        }
        assert check._get_staged_present_files() == [tmp_path / "renamed.yml"]

    def test_staged_paths_ignore_replaced_head_tree(self, tmp_path: Path) -> None:
        self._git(tmp_path, "init", "--quiet")
        self._git(tmp_path, "config", "user.email", "test@example.com")
        self._git(tmp_path, "config", "user.name", "Test")
        self._git(tmp_path, "config", "core.hooksPath", ".git/no-hooks")
        script = tmp_path / "script.ps1"
        script.write_text("Write-Host benign\n", encoding="utf-8")
        self._git(tmp_path, "add", "script.ps1")
        self._git(tmp_path, "commit", "--quiet", "-m", "initial")
        original_head = self._git(tmp_path, "rev-parse", "HEAD").stdout.strip()

        script.write_text("Invoke-Expression malicious\n", encoding="utf-8")
        self._git(tmp_path, "add", "script.ps1")
        staged_tree = self._git(tmp_path, "write-tree").stdout.strip()
        replacement_commit = self._git(
            tmp_path,
            "commit-tree",
            staged_tree,
            "-m",
            "replacement",
        ).stdout.strip()
        self._git(tmp_path, "replace", original_head, replacement_commit)

        assert self._git(tmp_path, "diff", "--cached", "--name-only").stdout == ""

        with patch.object(
            PreCommitSecurityCheck,
            "_find_repo_root",
            return_value=tmp_path,
        ):
            check = PreCommitSecurityCheck(skip_codeql=True)

        assert check._get_staged_present_files() == [script]

    def test_run_fails_closed_on_unmerged_powershell_index_entry(
        self, tmp_path: Path
    ) -> None:
        self._git(tmp_path, "init", "--quiet")
        object_ids = []
        for index, content in enumerate(("base", "ours", "theirs"), start=1):
            blob = tmp_path / f"blob-{index}"
            blob.write_text(content, encoding="utf-8")
            object_ids.append(
                self._git(tmp_path, "hash-object", "-w", blob.name).stdout.strip()
            )

        index_info = "".join(
            f"100644 {object_id} {stage}\tconflict.ps1\n"
            for stage, object_id in enumerate(object_ids, start=1)
        )
        subprocess.run(
            ["git", "-C", str(tmp_path), "update-index", "--index-info"],
            input=index_info,
            check=True,
            encoding="utf-8",
        )

        with patch.object(
            PreCommitSecurityCheck,
            "_find_repo_root",
            return_value=tmp_path,
        ):
            check = PreCommitSecurityCheck(skip_codeql=True)

        assert check.run() == 1

    def test_read_staged_blob_ignores_unstaged_worktree_replacement(
        self, tmp_path: Path
    ) -> None:
        self._git(tmp_path, "init", "--quiet")
        script = tmp_path / "script.ps1"
        script.write_bytes(b"Write-Host 'staged'\n")
        self._git(tmp_path, "add", "script.ps1")
        script.write_bytes(b"Write-Host 'working tree'\n")

        with patch.object(
            PreCommitSecurityCheck,
            "_find_repo_root",
            return_value=tmp_path,
        ):
            check = PreCommitSecurityCheck(skip_codeql=True)

        assert check._read_staged_blob(script) == b"Write-Host 'staged'\n"

    def test_read_staged_blob_treats_stage_like_filename_literally(
        self, tmp_path: Path
    ) -> None:
        self._git(tmp_path, "init", "--quiet")
        script = tmp_path / "0:script.ps1"
        script.write_bytes(b"Write-Host 'staged'\n")
        self._git(tmp_path, "add", "0:script.ps1")
        script.write_bytes(b"Write-Host 'working tree'\n")

        with patch.object(
            PreCommitSecurityCheck,
            "_find_repo_root",
            return_value=tmp_path,
        ):
            check = PreCommitSecurityCheck(skip_codeql=True)

        assert check._read_staged_blob(script) == b"Write-Host 'staged'\n"

    def test_read_staged_blob_ignores_replacement_refs(
        self, tmp_path: Path
    ) -> None:
        self._git(tmp_path, "init", "--quiet")
        script = tmp_path / "script.ps1"
        script.write_bytes(b"Write-Host 'indexed'\n")
        self._git(tmp_path, "add", "script.ps1")
        indexed_object = self._git(
            tmp_path,
            "rev-parse",
            ":script.ps1",
        ).stdout.strip()

        replacement = tmp_path / "replacement"
        replacement.write_bytes(b"Write-Host 'replacement'\n")
        replacement_object = self._git(
            tmp_path,
            "hash-object",
            "-w",
            "replacement",
        ).stdout.strip()
        self._git(tmp_path, "replace", indexed_object, replacement_object)

        with patch.object(
            PreCommitSecurityCheck,
            "_find_repo_root",
            return_value=tmp_path,
        ):
            check = PreCommitSecurityCheck(skip_codeql=True)

        assert check._read_staged_blob(script) == b"Write-Host 'indexed'\n"

    def test_read_staged_blob_rejects_powershell_symlink(
        self, tmp_path: Path
    ) -> None:
        self._git(tmp_path, "init", "--quiet")
        link_target = tmp_path / "link-target"
        link_target.write_text("target.ps1", encoding="utf-8")
        object_id = self._git(tmp_path, "hash-object", "-w", "link-target").stdout.strip()
        self._git(
            tmp_path,
            "update-index",
            "--add",
            "--cacheinfo",
            f"120000,{object_id},link.ps1",
        )

        with patch.object(
            PreCommitSecurityCheck,
            "_find_repo_root",
            return_value=tmp_path,
        ):
            check = PreCommitSecurityCheck(skip_codeql=True)

        assert check._read_staged_blob(tmp_path / "link.ps1") is None

    @pytest.mark.parametrize(
        "entry_output",
        [
            b"",
            b"100644 object 0 script.ps1\0",
            b"100644 object\tfile.ps1\0",
            b"100644 object 1\tscript.ps1\0",
        ],
    )
    def test_read_staged_blob_rejects_invalid_index_entries(
        self,
        check: PreCommitSecurityCheck,
        entry_output: bytes,
    ) -> None:
        with patch(
            "scripts.security.invoke_precommit_security.subprocess.run",
            return_value=_completed(0, stdout=entry_output),
        ):
            assert check._read_staged_blob(Path("/repo/script.ps1")) is None

    def test_read_staged_blob_fails_when_cat_file_fails(
        self, check: PreCommitSecurityCheck
    ) -> None:
        with patch(
            "scripts.security.invoke_precommit_security.subprocess.run",
            side_effect=[
                _completed(
                    0,
                    stdout=b"100644 deadbeef 0\tscript.ps1\0",
                ),
                subprocess.CalledProcessError(1, ["git", "cat-file"]),
            ],
        ):
            assert check._read_staged_blob(Path("/repo/script.ps1")) is None

    def test_get_staged_files_keeps_non_powershell_security_paths(
        self, check: PreCommitSecurityCheck
    ) -> None:
        with patch(
            "scripts.security.invoke_precommit_security.subprocess.run",
            return_value=_completed(
                0,
                stdout=b"Lefthook.yml\0script.ps1\0README.md\0",
            ),
        ) as run_mock:
            assert check._get_staged_files() == [
                Path("/repo/Lefthook.yml"),
                Path("/repo/script.ps1"),
                Path("/repo/README.md"),
            ]

        assert "--diff-filter=ACMDRT" in run_mock.call_args.args[0]
        assert "--no-renames" in run_mock.call_args.args[0]

    def test_relocated_hook_payload_is_critical(
        self, check: PreCommitSecurityCheck
    ) -> None:
        payload = Path("/repo/scripts/hooks/pre-push")

        assert check._check_critical_patterns([payload]) == [payload]

    @pytest.mark.parametrize(
        "config_path",
        [
            f"{base}{suffix}{extension}"
            for base in ("lefthook", ".lefthook", ".config/lefthook")
            for suffix in ("", "-local")
            for extension in (".yml", ".yaml", ".json", ".jsonc", ".toml")
        ],
    )
    def test_auto_discovered_lefthook_configs_are_critical(
        self, check: PreCommitSecurityCheck, config_path: str
    ) -> None:
        config = Path("/repo") / config_path

        assert check._check_critical_patterns([config]) == [config]

    @pytest.mark.parametrize(
        "config_path",
        [
            "Lefthook.yml",
            ".LEFTHOOK-LOCAL.JSONC",
            ".Config/LeftHook-Local.Toml",
        ],
    )
    def test_auto_discovered_lefthook_configs_are_case_insensitive(
        self, check: PreCommitSecurityCheck, config_path: str
    ) -> None:
        config = Path("/repo") / config_path

        assert check._check_critical_patterns([config]) == [config]

    def test_run_reports_mixed_case_lefthook_config_without_powershell_analysis(
        self, check: PreCommitSecurityCheck
    ) -> None:
        config = Path("/repo/Lefthook.yml")
        report = Path("/repo/.project-toolkit/security/SR-test.md")

        with (
            patch.object(check, "_get_staged_files", return_value=[config]),
            patch.object(check, "_get_staged_present_files", return_value=[config]),
            patch.object(check, "_get_unmerged_files", return_value=[]),
            patch.object(check, "_ensure_psscriptanalyzer") as ensure_analyzer,
            patch.object(
                check,
                "_generate_security_report",
                return_value=report,
            ) as generate_report,
            patch.object(check, "_stage_security_report", return_value=True),
            patch.object(check, "_verify_security_report", return_value=True),
        ):
            assert check.run() == 0

        ensure_analyzer.assert_not_called()
        generate_report.assert_called_once_with([config], [config])

    @pytest.mark.parametrize(
        "config_path",
        [
            "config/lefthook.yml",
            "nested/lefthook.yml",
            "nested/.config/lefthook-local.jsonc",
        ],
    )
    def test_non_discovered_lefthook_lookalikes_are_not_critical(
        self, check: PreCommitSecurityCheck, config_path: str
    ) -> None:
        config = Path("/repo") / config_path

        assert check._check_critical_patterns([config]) == []

    def test_removed_githooks_path_is_not_critical(
        self, check: PreCommitSecurityCheck
    ) -> None:
        payload = Path("/repo/.githooks/pre-push")

        assert check._check_critical_patterns([payload]) == []
