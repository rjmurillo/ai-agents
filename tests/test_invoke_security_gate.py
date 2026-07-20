"""Tests for invoke_security_gate.py PreToolUse hook."""

from __future__ import annotations

import json
import sys
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_project_root / ".claude" / "hooks" / "PreToolUse"))
sys.path.insert(0, str(_project_root))

from invoke_security_gate import (  # noqa: E402
    extract_patch_paths,
    find_security_evidence,
    gate_paths,
    is_auth_path,
    main,
)

from scripts.security import invoke_precommit_security  # noqa: E402


class TestIsAuthPath:
    @pytest.mark.parametrize(
        "path",
        [
            "src/Auth/LoginController.cs",
            "src/auth/handler.py",
            "lib/Authentication/oauth.ts",
            "lib/authorization/rbac.py",
            "app/middleware/authMiddleware.js",
            "config.auth.ts",
            "server.auth.py",
            "services/auth/tokens.go",
            "/home/user/project/Auth/models.cs",
            "Auth/Login.cs",
            "auth/handler.py",
            "Authentication/oauth.ts",
            "authorization/rbac.py",
            "middleware/authHandler.js",
            "app/Middleware/auth.js",
        ],
    )
    def test_matches_auth_paths(self, path: str) -> None:
        assert is_auth_path(path) is True

    @pytest.mark.parametrize(
        "path",
        [
            "src/AUTH/login.ts",
            "src/AUTHENTICATION/oauth.ts",
            "lib/AUTHORIZATION/rbac.py",
            "config.AUTH.ts",
            "app/MIDDLEWARE/AUTH.js",
            "SRC/Auth/Login.CS",
        ],
    )
    def test_matches_uppercase_auth_paths(self, path: str) -> None:
        # Windows and macOS filesystems are case-insensitive: an upper-cased
        # segment names the same auth file and must still be gated (issue #3203).
        assert is_auth_path(path) is True

    @pytest.mark.parametrize(
        "path",
        [
            "src/controllers/UserController.cs",
            "lib/utils/helpers.py",
            "README.md",
            "src/author/book.py",
            "docs/authentication-guide.md",
            "",
        ],
    )
    def test_rejects_non_auth_paths(self, path: str) -> None:
        assert is_auth_path(path) is False


class TestFindSecurityEvidence:
    def test_finds_security_report(self, tmp_path: Path) -> None:
        security_dir = tmp_path / ".agents" / "security"
        security_dir.mkdir(parents=True)
        from datetime import UTC, datetime

        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        (security_dir / f"{today}-security-review.md").write_text("review")

        assert find_security_evidence(str(tmp_path)) is True

    def test_finds_session_log_evidence(self, tmp_path: Path) -> None:
        sessions_dir = tmp_path / ".agents" / "sessions"
        sessions_dir.mkdir(parents=True)
        from datetime import UTC, datetime

        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        log = sessions_dir / f"{today}-session-01.json"
        log.write_text(json.dumps({"notes": "security agent reviewed auth changes"}))

        assert find_security_evidence(str(tmp_path)) is True

    def test_no_evidence_returns_false(self, tmp_path: Path) -> None:
        assert find_security_evidence(str(tmp_path)) is False

    def test_no_evidence_with_empty_dirs(self, tmp_path: Path) -> None:
        (tmp_path / ".agents" / "security").mkdir(parents=True)
        (tmp_path / ".agents" / "sessions").mkdir(parents=True)
        assert find_security_evidence(str(tmp_path)) is False

    def test_old_security_report_not_found(self, tmp_path: Path) -> None:
        security_dir = tmp_path / ".agents" / "security"
        security_dir.mkdir(parents=True)
        (security_dir / "2020-01-01-security-review.md").write_text("old")
        assert find_security_evidence(str(tmp_path)) is False

    def test_session_log_without_security_markers(self, tmp_path: Path) -> None:
        sessions_dir = tmp_path / ".agents" / "sessions"
        sessions_dir.mkdir(parents=True)
        from datetime import UTC, datetime

        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        log = sessions_dir / f"{today}-session-01.json"
        log.write_text(json.dumps({"notes": "implemented feature"}))

        assert find_security_evidence(str(tmp_path)) is False


class TestPreCommitSecurityCheck:
    def _checker(self, tmp_path: Path) -> invoke_precommit_security.PreCommitSecurityCheck:
        with patch.object(
            invoke_precommit_security.PreCommitSecurityCheck,
            "_find_repo_root",
            return_value=tmp_path,
        ):
            return invoke_precommit_security.PreCommitSecurityCheck(
                skip_codeql=True,
            )

    def test_codeql_timeout_returns_no_alerts(self, tmp_path: Path) -> None:
        checker = self._checker(tmp_path)

        with patch.object(
            checker,
            "_get_github_context",
            return_value=("owner", "repo", "branch"),
        ), patch(
            "scripts.security.invoke_precommit_security.subprocess.run",
            side_effect=invoke_precommit_security.subprocess.TimeoutExpired(
                cmd=["gh", "--version"],
                timeout=invoke_precommit_security.SUBPROCESS_TIMEOUT_SECONDS,
            ),
        ):
            assert checker._fetch_codeql_alerts() == []

    def test_psscriptanalyzer_timeout_fails_setup(self, tmp_path: Path) -> None:
        checker = self._checker(tmp_path)

        with patch(
            "scripts.security.invoke_precommit_security.subprocess.run",
            side_effect=invoke_precommit_security.subprocess.TimeoutExpired(
                cmd=["pwsh"],
                timeout=invoke_precommit_security.SUBPROCESS_TIMEOUT_SECONDS,
            ),
        ):
            assert checker._ensure_psscriptanalyzer() is False

    def test_run_fails_when_security_report_not_staged(self, tmp_path: Path) -> None:
        checker = self._checker(tmp_path)
        report_path = tmp_path / ".agents" / "security" / "SR-test.md"
        report_path.parent.mkdir(parents=True)
        report_path.write_text("x" * 200, encoding="utf-8")

        with patch.object(
            checker,
            "_get_staged_files",
            return_value=[tmp_path / "script.ps1"],
        ), patch.object(
            checker,
            "_get_staged_present_files",
            return_value=[tmp_path / "script.ps1"],
        ), patch.object(
            checker,
            "_get_unmerged_files",
            return_value=[],
        ), patch.object(checker, "_check_critical_patterns", return_value=[]), patch.object(
            checker, "_ensure_psscriptanalyzer", return_value=True
        ), patch.object(
            checker,
            "_run_psscriptanalyzer",
            return_value=invoke_precommit_security.PreCommitResult(
                passed=True,
                findings=[],
                report_path=None,
            ),
        ), patch.object(
            checker, "_generate_security_report", return_value=report_path
        ), patch.object(
            checker, "_stage_security_report", return_value=False
        ):
            assert checker.run() == 1


class TestMainAllowPath:
    @patch("invoke_security_gate.sys.stdin")
    def test_allows_when_stdin_is_tty(self, mock_stdin: MagicMock) -> None:
        mock_stdin.isatty.return_value = True
        assert main() == 0

    @patch("invoke_security_gate.sys.stdin", new_callable=StringIO)
    def test_allows_when_stdin_empty(self, mock_stdin: StringIO) -> None:
        mock_stdin.write("")
        mock_stdin.seek(0)
        with patch.object(mock_stdin, "isatty", return_value=False):
            assert main() == 0

    @patch("invoke_security_gate.sys.stdin", new_callable=StringIO)
    def test_allows_non_auth_file(self, mock_stdin: StringIO) -> None:
        hook_input = {"tool_input": {"file_path": "src/utils/helpers.py"}}
        mock_stdin.write(json.dumps(hook_input))
        mock_stdin.seek(0)
        with patch.object(mock_stdin, "isatty", return_value=False):
            assert main() == 0

    @patch("invoke_security_gate.sys.stdin", new_callable=StringIO)
    def test_allows_missing_file_path_fail_open(self, mock_stdin: StringIO) -> None:
        # No resolvable path: the gate cannot classify an auth file, so it fails
        # open instead of blocking every pathless write (#2610).
        hook_input = {"tool_input": {"command": "echo hello"}}
        mock_stdin.write(json.dumps(hook_input))
        mock_stdin.seek(0)
        with patch.object(mock_stdin, "isatty", return_value=False):
            assert main() == 0

    @patch("invoke_security_gate.sys.stdin", new_callable=StringIO)
    def test_allows_non_auth_file_via_path_key(self, mock_stdin: StringIO) -> None:
        # Copilot CLI create/edit deliver the target as ``path`` (#2610).
        hook_input = {"tool_name": "Write", "tool_input": {"path": "src/utils/helpers.py"}}
        mock_stdin.write(json.dumps(hook_input))
        mock_stdin.seek(0)
        with patch.object(mock_stdin, "isatty", return_value=False):
            assert main() == 0

    @patch("invoke_security_gate.find_security_evidence", return_value=False)
    @patch("invoke_security_gate.get_project_directory", return_value="/project")
    @patch("invoke_security_gate.sys.stdin", new_callable=StringIO)
    def test_blocks_auth_file_via_path_key(
        self,
        mock_stdin: StringIO,
        _mock_project: MagicMock,
        _mock_evidence: MagicMock,
    ) -> None:
        # An auth file created via Copilot's ``path`` key is still gated (#2610).
        hook_input = {"tool_name": "Write", "tool_input": {"path": "src/Auth/Login.cs"}}
        mock_stdin.write(json.dumps(hook_input))
        mock_stdin.seek(0)
        with patch.object(mock_stdin, "isatty", return_value=False):
            assert main() == 2

    @patch("invoke_security_gate.find_security_evidence", return_value=True)
    @patch("invoke_security_gate.get_project_directory", return_value="/project")
    @patch("invoke_security_gate.sys.stdin", new_callable=StringIO)
    def test_allows_auth_file_with_evidence(
        self,
        mock_stdin: StringIO,
        _mock_project: MagicMock,
        _mock_evidence: MagicMock,
    ) -> None:
        hook_input = {"tool_input": {"file_path": "src/Auth/Login.cs"}}
        mock_stdin.write(json.dumps(hook_input))
        mock_stdin.seek(0)
        with patch.object(mock_stdin, "isatty", return_value=False):
            assert main() == 0

    @patch("invoke_security_gate.sys.stdin", new_callable=StringIO)
    def test_blocks_invalid_tool_input(self, mock_stdin: StringIO) -> None:
        hook_input = {"tool_input": "not a dict"}
        mock_stdin.write(json.dumps(hook_input))
        mock_stdin.seek(0)
        with patch.object(mock_stdin, "isatty", return_value=False):
            assert main() == 2


class TestMainBlockPath:
    @patch("invoke_security_gate.find_security_evidence", return_value=False)
    @patch("invoke_security_gate.get_project_directory", return_value="/project")
    @patch("invoke_security_gate.sys.stdin", new_callable=StringIO)
    def test_blocks_auth_file_without_evidence(
        self,
        mock_stdin: StringIO,
        _mock_project: MagicMock,
        _mock_evidence: MagicMock,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        hook_input = {"tool_input": {"file_path": "src/Auth/Login.cs"}}
        mock_stdin.write(json.dumps(hook_input))
        mock_stdin.seek(0)
        with patch.object(mock_stdin, "isatty", return_value=False):
            assert main() == 2
        captured = capsys.readouterr()
        assert "Security Review Required" in captured.out
        assert "src/Auth/Login.cs" in captured.out
        assert "Blocked" in captured.err

    @patch("invoke_security_gate.find_security_evidence", return_value=False)
    @patch("invoke_security_gate.get_project_directory", return_value="/project")
    @patch("invoke_security_gate.sys.stdin", new_callable=StringIO)
    def test_blocks_middleware_auth_file(
        self,
        mock_stdin: StringIO,
        _mock_project: MagicMock,
        _mock_evidence: MagicMock,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        hook_input = {"tool_input": {"file_path": "app/middleware/authHandler.js"}}
        mock_stdin.write(json.dumps(hook_input))
        mock_stdin.seek(0)
        with patch.object(mock_stdin, "isatty", return_value=False):
            assert main() == 2
        captured = capsys.readouterr()
        assert "Security Review Required" in captured.out

    @patch("invoke_security_gate.find_security_evidence", return_value=False)
    @patch("invoke_security_gate.get_project_directory", return_value="/project")
    @patch("invoke_security_gate.sys.stdin", new_callable=StringIO)
    def test_blocks_auth_extension_file(
        self,
        mock_stdin: StringIO,
        _mock_project: MagicMock,
        _mock_evidence: MagicMock,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        hook_input = {"tool_input": {"file_path": "server.auth.ts"}}
        mock_stdin.write(json.dumps(hook_input))
        mock_stdin.seek(0)
        with patch.object(mock_stdin, "isatty", return_value=False):
            assert main() == 2
        captured = capsys.readouterr()
        assert "Security Review Required" in captured.out


class TestMainFailClosed:
    @patch("invoke_security_gate.sys.stdin", new_callable=StringIO)
    def test_fail_closed_on_json_error(self, mock_stdin: StringIO) -> None:
        mock_stdin.write("not json")
        mock_stdin.seek(0)
        with patch.object(mock_stdin, "isatty", return_value=False):
            assert main() == 2

    @patch("invoke_security_gate.get_project_directory", side_effect=RuntimeError("boom"))
    @patch("invoke_security_gate.sys.stdin", new_callable=StringIO)
    def test_fail_closed_on_project_dir_error(
        self,
        mock_stdin: StringIO,
        _mock_project: MagicMock,
    ) -> None:
        hook_input = {"tool_input": {"file_path": "src/Auth/Login.cs"}}
        mock_stdin.write(json.dumps(hook_input))
        mock_stdin.seek(0)
        with patch.object(mock_stdin, "isatty", return_value=False):
            assert main() == 2


class TestExtractPatchPaths:
    """Unit tests for freeform apply_patch header extraction (issue #3203)."""

    def test_extracts_add_file(self) -> None:
        patch = "*** Begin Patch\n*** Add File: probe.txt\n+test\n*** End Patch\n"
        assert extract_patch_paths(patch) == ["probe.txt"]

    def test_extracts_update_and_delete(self) -> None:
        patch = (
            "*** Begin Patch\n"
            "*** Update File: src/app.py\n"
            "@@\n-a\n+b\n"
            "*** Delete File: old/notes.md\n"
            "*** End Patch\n"
        )
        assert extract_patch_paths(patch) == ["src/app.py", "old/notes.md"]

    def test_extracts_move_to_rename_destination(self) -> None:
        patch = (
            "*** Begin Patch\n"
            "*** Update File: src/old.ts\n"
            "*** Move to: src/new.ts\n"
            "*** End Patch\n"
        )
        assert extract_patch_paths(patch) == ["src/old.ts", "src/new.ts"]

    def test_header_is_case_insensitive_and_whitespace_tolerant(self) -> None:
        # Case insensitivity and internal whitespace tolerance (around keywords,
        # colon, and path). Leading whitespace before ``***`` is NOT tolerated
        # because that pattern indicates a context line, not a structural header.
        patch = "***  add  file :   spaced/path.txt  \n"
        assert extract_patch_paths(patch) == ["spaced/path.txt"]

    def test_path_with_spaces_preserved(self) -> None:
        patch = "*** Add File: my dir/file name.txt\n"
        assert extract_patch_paths(patch) == ["my dir/file name.txt"]

    def test_windows_backslash_path(self) -> None:
        patch = "*** Update File: src\\Auth\\Login.cs\n"
        assert extract_patch_paths(patch) == ["src\\Auth\\Login.cs"]

    def test_empty_header_path_skipped(self) -> None:
        patch = "*** Add File: \n*** Add File: real.txt\n"
        assert extract_patch_paths(patch) == ["real.txt"]

    def test_no_headers_returns_empty(self) -> None:
        assert extract_patch_paths("just a random string, not a patch") == []

    def test_empty_string_returns_empty(self) -> None:
        assert extract_patch_paths("") == []

    def test_non_header_star_lines_ignored(self) -> None:
        # Diff body lines that merely start with *** must not be mistaken for
        # file headers (they lack the Add/Update/Delete/Move keyword).
        patch = "*** Begin Patch\n*** End Patch\n+*** not a header: x\n"
        assert extract_patch_paths(patch) == []


class TestGatePaths:
    """Unit tests for the shared multi-path gating helper (issue #3203)."""

    def test_allows_when_no_auth_paths(self) -> None:
        assert gate_paths(["a.txt", "src/utils/helpers.py"]) == 0

    def test_allows_empty_path_list(self) -> None:
        assert gate_paths([]) == 0

    @patch("invoke_security_gate.find_security_evidence", return_value=True)
    @patch("invoke_security_gate.get_project_directory", return_value="/project")
    def test_allows_auth_path_with_evidence(
        self, _mock_project: MagicMock, _mock_evidence: MagicMock
    ) -> None:
        assert gate_paths(["src/auth/login.ts"]) == 0

    @patch("invoke_security_gate.find_security_evidence", return_value=False)
    @patch("invoke_security_gate.get_project_directory", return_value="/project")
    def test_blocks_auth_path_without_evidence(
        self,
        _mock_project: MagicMock,
        _mock_evidence: MagicMock,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        assert gate_paths(["notes.md", "src/auth/login.ts"]) == 2
        captured = capsys.readouterr()
        assert "Security Review Required" in captured.out
        assert "src/auth/login.ts" in captured.out


class TestMainFreeformPatch:
    """End-to-end main() coverage for Copilot CLI apply_patch strings (#3203)."""

    @patch("invoke_security_gate.sys.stdin", new_callable=StringIO)
    def test_allows_non_auth_patch(self, mock_stdin: StringIO) -> None:
        # The exact customer repro: apply_patch creating a trivial file.
        patch_text = "*** Begin Patch\n*** Add File: probe.txt\n+test\n*** End Patch\n"
        hook_input = {"tool_name": "Edit", "tool_input": patch_text}
        mock_stdin.write(json.dumps(hook_input))
        mock_stdin.seek(0)
        with patch.object(mock_stdin, "isatty", return_value=False):
            assert main() == 0

    @patch("invoke_security_gate.find_security_evidence", return_value=False)
    @patch("invoke_security_gate.get_project_directory", return_value="/project")
    @patch("invoke_security_gate.sys.stdin", new_callable=StringIO)
    def test_blocks_auth_patch_without_evidence(
        self,
        mock_stdin: StringIO,
        _mock_project: MagicMock,
        _mock_evidence: MagicMock,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        patch_text = (
            "*** Begin Patch\n"
            "*** Update File: src/auth/login.ts\n"
            "@@\n-a\n+b\n"
            "*** End Patch\n"
        )
        hook_input = {"tool_name": "Edit", "tool_input": patch_text}
        mock_stdin.write(json.dumps(hook_input))
        mock_stdin.seek(0)
        with patch.object(mock_stdin, "isatty", return_value=False):
            assert main() == 2
        assert "Security Review Required" in capsys.readouterr().out

    @patch("invoke_security_gate.find_security_evidence", return_value=True)
    @patch("invoke_security_gate.get_project_directory", return_value="/project")
    @patch("invoke_security_gate.sys.stdin", new_callable=StringIO)
    def test_allows_auth_patch_with_evidence(
        self,
        mock_stdin: StringIO,
        _mock_project: MagicMock,
        _mock_evidence: MagicMock,
    ) -> None:
        patch_text = "*** Begin Patch\n*** Delete File: src/auth/tokens.py\n*** End Patch\n"
        hook_input = {"tool_name": "Edit", "tool_input": patch_text}
        mock_stdin.write(json.dumps(hook_input))
        mock_stdin.seek(0)
        with patch.object(mock_stdin, "isatty", return_value=False):
            assert main() == 0

    @patch("invoke_security_gate.sys.stdin", new_callable=StringIO)
    def test_fails_closed_on_malformed_patch_string(
        self, mock_stdin: StringIO, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # A string with no recognizable patch headers cannot be classified;
        # fail closed rather than let a hidden auth edit through.
        hook_input = {"tool_name": "Edit", "tool_input": "not a patch at all"}
        mock_stdin.write(json.dumps(hook_input))
        mock_stdin.seek(0)
        with patch.object(mock_stdin, "isatty", return_value=False):
            assert main() == 2
        assert "Security Gate Error" in capsys.readouterr().out
