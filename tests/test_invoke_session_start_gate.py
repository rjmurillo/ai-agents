"""Tests for invoke_session_start_gate.py session verification gates."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

from scripts.invoke_session_start_gate import (
    check_branch_gate,
    check_memory_gate,
    check_session_log_gate,
    check_skill_gate,
    main,
)


class TestCheckMemoryGate:
    def test_pass_when_memory_index_exists(self, tmp_path: Path) -> None:
        memories_dir = tmp_path / ".serena" / "memories"
        memories_dir.mkdir(parents=True)
        (memories_dir / "memory-index.md").write_text(
            "[project-overview](project-overview.md)\n",
            encoding="utf-8",
        )
        for name in ("project-overview", "codebase-structure", "usage-mandatory"):
            (memories_dir / f"{name}.md").write_text("content", encoding="utf-8")

        assert check_memory_gate(tmp_path) is True

    def test_fail_when_memory_index_missing(self, tmp_path: Path) -> None:
        assert check_memory_gate(tmp_path) is False


class TestCheckSkillGate:
    def test_pass_when_skills_exist(self, tmp_path: Path) -> None:
        skills_dir = tmp_path / ".claude" / "skills" / "github" / "scripts" / "pr"
        skills_dir.mkdir(parents=True)
        (skills_dir / "get_pr.py").write_text("# skill", encoding="utf-8")
        (tmp_path / ".serena" / "memories").mkdir(parents=True)
        (tmp_path / ".serena" / "memories" / "usage-mandatory.md").write_text(
            "content", encoding="utf-8"
        )
        assert check_skill_gate(tmp_path) is True

    def test_fail_when_skills_dir_missing(self, tmp_path: Path) -> None:
        assert check_skill_gate(tmp_path) is False


class TestCheckSessionLogGate:
    def test_pass_when_session_log_exists(self, tmp_path: Path) -> None:
        sessions = tmp_path / ".agents" / "sessions"
        sessions.mkdir(parents=True)
        today = date.today().isoformat()
        log_file = sessions / f"{today}-session-1.json"
        log_data = {
            "schemaVersion": "2.0",
            "session": {"objective": "test"},
            "protocolCompliance": {},
        }
        log_file.write_text(json.dumps(log_data), encoding="utf-8")

        assert check_session_log_gate(tmp_path) is True

    def test_fail_when_no_sessions_dir(self, tmp_path: Path) -> None:
        assert check_session_log_gate(tmp_path) is False

    def test_fail_when_no_today_sessions(self, tmp_path: Path) -> None:
        sessions = tmp_path / ".agents" / "sessions"
        sessions.mkdir(parents=True)
        # Create a session from yesterday
        (sessions / "2020-01-01-session-1.json").write_text("{}", encoding="utf-8")
        assert check_session_log_gate(tmp_path) is False


class TestCheckBranchGate:
    @patch("scripts.invoke_session_start_gate.run_git")
    def test_pass_on_feature_branch(self, mock_git: MagicMock, tmp_path: Path) -> None:
        mock_git.return_value = MagicMock(returncode=0, stdout="feat/my-branch\n")
        passed, err = check_branch_gate(tmp_path)
        assert passed is True
        assert err == 0

    @patch("scripts.invoke_session_start_gate.run_git")
    def test_fail_on_main_branch(self, mock_git: MagicMock, tmp_path: Path) -> None:
        mock_git.return_value = MagicMock(returncode=0, stdout="main\n")
        passed, err = check_branch_gate(tmp_path)
        assert passed is False

    @patch("scripts.invoke_session_start_gate.run_git")
    def test_fail_on_git_error(self, mock_git: MagicMock, tmp_path: Path) -> None:
        mock_git.return_value = MagicMock(returncode=1, stdout="")
        passed, err = check_branch_gate(tmp_path)
        assert passed is False
        assert err == 3


class TestMain:
    @patch("scripts.invoke_session_start_gate.get_repo_root", return_value=None)
    def test_exits_3_when_no_repo(self, _mock: MagicMock) -> None:
        assert main([]) == 3

    @patch("scripts.invoke_session_start_gate.check_branch_gate", return_value=(True, 0))
    @patch("scripts.invoke_session_start_gate.check_session_log_gate", return_value=True)
    @patch("scripts.invoke_session_start_gate.check_skill_gate", return_value=True)
    @patch("scripts.invoke_session_start_gate.check_memory_gate", return_value=True)
    @patch("scripts.invoke_session_start_gate.get_repo_root")
    def test_all_pass(
        self,
        mock_root: MagicMock,
        _mem: MagicMock,
        _skill: MagicMock,
        _sess: MagicMock,
        _branch: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_root.return_value = tmp_path
        assert main([]) == 0

    @patch("scripts.invoke_session_start_gate.get_repo_root")
    def test_skip_all_gates(self, mock_root: MagicMock, tmp_path: Path) -> None:
        mock_root.return_value = tmp_path
        result = main([
            "--skip-memory-gate",
            "--skip-skill-gate",
            "--skip-session-log-gate",
            "--skip-branch-gate",
        ])
        assert result == 0
