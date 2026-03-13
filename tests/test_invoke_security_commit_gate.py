"""Tests for invoke_security_commit_gate.py PreToolUse hook."""

from __future__ import annotations

import json
import sys
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_project_root / ".claude" / "hooks" / "PreToolUse"))

from invoke_security_commit_gate import (  # noqa: E402
    find_security_evidence,
    get_staged_files,
    main,
    match_security_paths,
)


class TestGetStagedFiles:
    def test_returns_files_on_success(self) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "src/Auth/login.py\nREADME.md\n"
        with patch("invoke_security_commit_gate.subprocess.run", return_value=mock_result):
            assert get_staged_files() == ["src/Auth/login.py", "README.md"]

    def test_raises_on_nonzero_exit(self) -> None:
        import subprocess
        with patch(
            "invoke_security_commit_gate.subprocess.run",
            side_effect=subprocess.CalledProcessError(1, "git"),
        ):
            with pytest.raises(subprocess.CalledProcessError):
                get_staged_files()

    def test_raises_on_os_error(self) -> None:
        with patch("invoke_security_commit_gate.subprocess.run", side_effect=OSError):
            with pytest.raises(OSError):
                get_staged_files()


class TestMatchSecurityPaths:
    def test_matches_auth_directory(self) -> None:
        assert match_security_paths(["src/Auth/login.py"]) == ["src/Auth/login.py"]

    def test_matches_security_directory(self) -> None:
        assert match_security_paths(["src/Security/validator.py"]) == [
            "src/Security/validator.py"
        ]

    def test_matches_env_file(self) -> None:
        assert match_security_paths([".env.local"]) == [".env.local"]

    def test_matches_password_file(self) -> None:
        assert match_security_paths(["config/password_config.json"]) == [
            "config/password_config.json"
        ]

    def test_no_match_for_normal_files(self) -> None:
        assert match_security_paths(["src/main.py", "README.md", "tests/test_app.py"]) == []

    def test_returns_only_matched_files(self) -> None:
        files = ["src/Auth/login.py", "README.md", "src/util.py"]
        assert match_security_paths(files) == ["src/Auth/login.py"]


class TestFindSecurityEvidence:
    def test_returns_false_when_no_evidence(self, tmp_path: Path) -> None:
        (tmp_path / ".agents" / "sessions").mkdir(parents=True)
        assert find_security_evidence(str(tmp_path)) is False

    def test_returns_true_with_security_report(self, tmp_path: Path) -> None:
        from datetime import UTC, datetime

        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        security_dir = tmp_path / ".agents" / "security"
        security_dir.mkdir(parents=True)
        (security_dir / f"{today}-report.md").write_text("Security review done")
        assert find_security_evidence(str(tmp_path)) is True

    def test_returns_true_with_session_log_evidence(self, tmp_path: Path) -> None:
        from datetime import UTC, datetime

        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        sessions_dir = tmp_path / ".agents" / "sessions"
        sessions_dir.mkdir(parents=True)
        (sessions_dir / f"{today}-session-01.json").write_text(
            '{"security review": "completed"}'
        )
        assert find_security_evidence(str(tmp_path)) is True


class TestMain:
    def test_allows_when_tty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SKIP_SECURITY_GATE", "false")
        with patch("invoke_security_commit_gate.sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            assert main() == 0

    def test_allows_when_skip_env_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SKIP_SECURITY_GATE", "true")
        assert main() == 0

    def test_allows_non_commit_command(
        self,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("SKIP_SECURITY_GATE", raising=False)
        mock_stdin = StringIO(json.dumps({"tool_input": {"command": "git push"}}))
        with patch("invoke_security_commit_gate.sys.stdin", mock_stdin):
            with patch.object(mock_stdin, "isatty", return_value=False):
                assert main() == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == ""

    def test_allows_commit_with_no_staged_security_files(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("SKIP_SECURITY_GATE", raising=False)
        mock_stdin = StringIO(json.dumps({"tool_input": {"command": "git commit -m 'fix'"}}))
        with patch("invoke_security_commit_gate.sys.stdin", mock_stdin):
            with patch.object(mock_stdin, "isatty", return_value=False):
                with patch(
                    "invoke_security_commit_gate.get_staged_files",
                    return_value=["README.md"],
                ):
                    assert main() == 0

    def test_denies_commit_with_security_files_and_no_evidence(
        self,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("SKIP_SECURITY_GATE", raising=False)
        mock_stdin = StringIO(json.dumps({"tool_input": {"command": "git commit -m 'add auth'"}}))
        with patch("invoke_security_commit_gate.sys.stdin", mock_stdin):
            with patch.object(mock_stdin, "isatty", return_value=False):
                with patch(
                    "invoke_security_commit_gate.get_staged_files",
                    return_value=["src/Auth/login.py"],
                ):
                    with patch(
                        "invoke_security_commit_gate.find_security_evidence",
                        return_value=False,
                    ):
                        with patch(
                            "invoke_security_commit_gate.get_project_directory",
                            return_value="/fake",
                        ):
                            assert main() == 0
                            captured = capsys.readouterr()
                            output = json.loads(captured.out.strip())
                            assert output["decision"] == "deny"
                            assert "SECURITY COMMIT GATE" in output["reason"]

    def test_allows_commit_with_security_files_and_evidence(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("SKIP_SECURITY_GATE", raising=False)
        mock_stdin = StringIO(json.dumps({"tool_input": {"command": "git commit -m 'add auth'"}}))
        with patch("invoke_security_commit_gate.sys.stdin", mock_stdin):
            with patch.object(mock_stdin, "isatty", return_value=False):
                with patch(
                    "invoke_security_commit_gate.get_staged_files",
                    return_value=["src/Auth/login.py"],
                ):
                    with patch(
                        "invoke_security_commit_gate.find_security_evidence",
                        return_value=True,
                    ):
                        with patch(
                            "invoke_security_commit_gate.get_project_directory",
                            return_value="/fake",
                        ):
                            assert main() == 0

    def test_denies_commit_on_infrastructure_error(
        self,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Fail-closed: infrastructure errors block the commit."""
        monkeypatch.delenv("SKIP_SECURITY_GATE", raising=False)
        mock_stdin = StringIO(json.dumps({"tool_input": {"command": "git commit -m 'add auth'"}}))
        with patch("invoke_security_commit_gate.sys.stdin", mock_stdin):
            with patch.object(mock_stdin, "isatty", return_value=False):
                with patch(
                    "invoke_security_commit_gate.get_staged_files",
                    side_effect=OSError("git not found"),
                ):
                    assert main() == 0
                    captured = capsys.readouterr()
                    output = json.loads(captured.out.strip())
                    assert output["decision"] == "deny"
                    assert "SECURITY COMMIT GATE FAILED" in output["reason"]
