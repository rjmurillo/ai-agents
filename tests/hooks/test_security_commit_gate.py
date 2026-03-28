#!/usr/bin/env python3
"""Tests for the invoke_security_commit_gate PreToolUse hook.

Covers: staged file detection, security path matching, evidence checking,
JSON decision output, exit code (always 0, uses JSON deny/allow).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

if TYPE_CHECKING:
    from collections.abc import Callable

HOOK_DIR = str(Path(__file__).resolve().parents[2] / ".claude" / "hooks" / "PreToolUse")
sys.path.insert(0, HOOK_DIR)

import invoke_security_commit_gate  # noqa: E402

# ---------------------------------------------------------------------------
# Unit tests for match_security_paths
# ---------------------------------------------------------------------------


class TestMatchSecurityPaths:
    def test_matches_auth_dir(self):
        result = invoke_security_commit_gate.match_security_paths(
            ["src/Auth/handler.py"]
        )
        assert result == ["src/Auth/handler.py"]

    def test_matches_env_file(self):
        result = invoke_security_commit_gate.match_security_paths([".env"])
        assert result == [".env"]

    def test_matches_secrets_dir(self):
        result = invoke_security_commit_gate.match_security_paths(
            ["config/secrets/db.json"]
        )
        assert result == ["config/secrets/db.json"]

    def test_matches_password_file(self):
        result = invoke_security_commit_gate.match_security_paths(
            ["utils/password_utils.py"]
        )
        assert result == ["utils/password_utils.py"]

    def test_ignores_non_security(self):
        result = invoke_security_commit_gate.match_security_paths(
            ["src/utils/helper.py", "README.md"]
        )
        assert result == []

    def test_empty_input(self):
        result = invoke_security_commit_gate.match_security_paths([])
        assert result == []


# ---------------------------------------------------------------------------
# Unit tests for find_security_evidence
# ---------------------------------------------------------------------------


class TestFindSecurityEvidence:
    def test_finds_security_report(self, tmp_path):
        security_dir = tmp_path / ".agents" / "security"
        security_dir.mkdir(parents=True)
        from datetime import UTC, datetime

        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        (security_dir / f"{today}-review.md").write_text("review")
        assert invoke_security_commit_gate.find_security_evidence(str(tmp_path))

    def test_returns_false_when_no_evidence(self, tmp_path):
        assert not invoke_security_commit_gate.find_security_evidence(str(tmp_path))


# ---------------------------------------------------------------------------
# Unit tests for main
# ---------------------------------------------------------------------------


class TestMain:
    @patch("invoke_security_commit_gate.skip_if_consumer_repo", return_value=True)
    def test_exits_0_when_consumer_repo(
        self, _mock, mock_stdin: Callable[[str], None]
    ):
        mock_stdin("{}")
        result = invoke_security_commit_gate.main()
        assert result == 0

    def test_exits_0_on_tty(self, monkeypatch):
        monkeypatch.setattr("sys.stdin", MagicMock(isatty=lambda: True))
        with patch(
            "invoke_security_commit_gate.skip_if_consumer_repo",
            return_value=False,
        ):
            result = invoke_security_commit_gate.main()
        assert result == 0

    def test_exits_0_on_empty_input(self, mock_stdin: Callable[[str], None]):
        mock_stdin("")
        with patch(
            "invoke_security_commit_gate.skip_if_consumer_repo",
            return_value=False,
        ):
            result = invoke_security_commit_gate.main()
        assert result == 0

    def test_exits_0_for_non_commit(self, mock_stdin: Callable[[str], None]):
        mock_stdin(
            json.dumps({"tool_input": {"command": "git push"}})
        )
        with patch(
            "invoke_security_commit_gate.skip_if_consumer_repo",
            return_value=False,
        ):
            result = invoke_security_commit_gate.main()
        assert result == 0

    @patch("invoke_security_commit_gate.get_staged_files", return_value=[])
    def test_exits_0_when_no_staged_files(
        self, _staged, mock_stdin: Callable[[str], None]
    ):
        mock_stdin(
            json.dumps({"tool_input": {"command": "git commit -m test"}})
        )
        with patch(
            "invoke_security_commit_gate.skip_if_consumer_repo",
            return_value=False,
        ):
            result = invoke_security_commit_gate.main()
        assert result == 0

    @patch("invoke_security_commit_gate.get_staged_files", return_value=["README.md"])
    def test_exits_0_when_no_security_files(
        self, _staged, mock_stdin: Callable[[str], None]
    ):
        mock_stdin(
            json.dumps({"tool_input": {"command": "git commit -m test"}})
        )
        with patch(
            "invoke_security_commit_gate.skip_if_consumer_repo",
            return_value=False,
        ):
            result = invoke_security_commit_gate.main()
        assert result == 0

    @patch("invoke_security_commit_gate.find_security_evidence", return_value=False)
    @patch("invoke_security_commit_gate.get_project_directory", return_value="/project")
    @patch(
        "invoke_security_commit_gate.get_staged_files",
        return_value=["src/Auth/login.py"],
    )
    def test_outputs_deny_when_security_files_without_evidence(
        self,
        _staged,
        _dir,
        _evidence,
        mock_stdin: Callable[[str], None],
        capsys,
    ):
        mock_stdin(
            json.dumps({"tool_input": {"command": "git commit -m test"}})
        )
        with patch(
            "invoke_security_commit_gate.skip_if_consumer_repo",
            return_value=False,
        ):
            result = invoke_security_commit_gate.main()
        assert result == 0  # Always exits 0, uses JSON for deny
        captured = capsys.readouterr()
        data = json.loads(captured.out.strip())
        assert data["decision"] == "deny"
        assert "Auth/login.py" in data["reason"]

    @patch("invoke_security_commit_gate.find_security_evidence", return_value=True)
    @patch("invoke_security_commit_gate.get_project_directory", return_value="/project")
    @patch(
        "invoke_security_commit_gate.get_staged_files",
        return_value=["src/Auth/login.py"],
    )
    def test_exits_0_when_evidence_exists(
        self,
        _staged,
        _dir,
        _evidence,
        mock_stdin: Callable[[str], None],
    ):
        mock_stdin(
            json.dumps({"tool_input": {"command": "git commit -m test"}})
        )
        with patch(
            "invoke_security_commit_gate.skip_if_consumer_repo",
            return_value=False,
        ):
            result = invoke_security_commit_gate.main()
        assert result == 0

    def test_exits_0_with_env_bypass(
        self, mock_stdin: Callable[[str], None], monkeypatch
    ):
        monkeypatch.setenv("SKIP_SECURITY_GATE", "true")
        mock_stdin(
            json.dumps({"tool_input": {"command": "git commit -m test"}})
        )
        with patch(
            "invoke_security_commit_gate.skip_if_consumer_repo",
            return_value=False,
        ):
            result = invoke_security_commit_gate.main()
        assert result == 0

    @patch("invoke_security_commit_gate.get_staged_files")
    def test_outputs_deny_on_infrastructure_error(
        self,
        mock_staged,
        mock_stdin: Callable[[str], None],
        capsys,
    ):
        """Security gate fails closed on errors."""
        mock_staged.side_effect = RuntimeError("git broken")
        mock_stdin(
            json.dumps({"tool_input": {"command": "git commit -m test"}})
        )
        with patch(
            "invoke_security_commit_gate.skip_if_consumer_repo",
            return_value=False,
        ):
            result = invoke_security_commit_gate.main()
        assert result == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out.strip())
        assert data["decision"] == "deny"
