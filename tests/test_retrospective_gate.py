"""Tests for invoke_retrospective_gate.py hook.

Tests the retrospective enforcement gate per ADR-033 (Issue #618).
"""

from __future__ import annotations

import importlib.util
import json
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest


def load_retrospective_gate_module() -> object:
    """Load the retrospective gate module from the hooks directory."""
    hook_path = (
        Path(__file__).parent.parent
        / ".claude"
        / "hooks"
        / "PreToolUse"
        / "invoke_retrospective_gate.py"
    )
    spec = importlib.util.spec_from_file_location("invoke_retrospective_gate", hook_path)
    if spec is None or spec.loader is None:
        pytest.skip("Could not load retrospective gate module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestIsGitPushCommand:
    def test_returns_true_for_git_push(self) -> None:
        mod = load_retrospective_gate_module()
        assert mod.is_git_push_command("git push") is True

    def test_returns_true_for_git_push_with_remote(self) -> None:
        mod = load_retrospective_gate_module()
        assert mod.is_git_push_command("git push origin main") is True

    def test_returns_true_for_git_push_with_flags(self) -> None:
        mod = load_retrospective_gate_module()
        assert mod.is_git_push_command("git push -u origin feature/test") is True

    def test_returns_false_for_git_status(self) -> None:
        mod = load_retrospective_gate_module()
        assert mod.is_git_push_command("git status") is False

    def test_returns_false_for_git_commit(self) -> None:
        mod = load_retrospective_gate_module()
        assert mod.is_git_push_command("git commit -m 'test'") is False

    def test_returns_false_for_empty_string(self) -> None:
        mod = load_retrospective_gate_module()
        assert mod.is_git_push_command("") is False

    def test_returns_false_for_none(self) -> None:
        mod = load_retrospective_gate_module()
        assert mod.is_git_push_command(None) is False


class TestCheckRetrospectiveInSessionLog:
    def test_finds_retrospective_section(self, tmp_path: Path) -> None:
        mod = load_retrospective_gate_module()
        session_log = tmp_path / "session.json"
        session_log.write_text('{"notes": "## Retrospective\\nLearnings captured"}')
        assert mod.check_retrospective_in_session_log(session_log) is True

    def test_finds_retrospective_file_reference(self, tmp_path: Path) -> None:
        mod = load_retrospective_gate_module()
        session_log = tmp_path / "session.json"
        session_log.write_text('{"notes": "See .agents/retrospective/2026-02-20-analysis.md"}')
        assert mod.check_retrospective_in_session_log(session_log) is True

    def test_returns_false_when_no_retrospective(self, tmp_path: Path) -> None:
        mod = load_retrospective_gate_module()
        session_log = tmp_path / "session.json"
        session_log.write_text('{"notes": "Just some work done"}')
        assert mod.check_retrospective_in_session_log(session_log) is False

    def test_returns_false_for_nonexistent_file(self, tmp_path: Path) -> None:
        mod = load_retrospective_gate_module()
        session_log = tmp_path / "nonexistent.json"
        assert mod.check_retrospective_in_session_log(session_log) is False


class TestCheckRetrospectiveFileExists:
    def test_finds_today_retrospective(self, tmp_path: Path) -> None:
        mod = load_retrospective_gate_module()
        retro_dir = tmp_path / ".agents" / "retrospective"
        retro_dir.mkdir(parents=True)
        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        (retro_dir / f"{today}-analysis.md").write_text("# Retrospective")

        assert mod.check_retrospective_file_exists(str(tmp_path)) is True

    def test_returns_false_for_old_retrospective(self, tmp_path: Path) -> None:
        mod = load_retrospective_gate_module()
        retro_dir = tmp_path / ".agents" / "retrospective"
        retro_dir.mkdir(parents=True)
        (retro_dir / "2020-01-01-old.md").write_text("# Old Retrospective")

        assert mod.check_retrospective_file_exists(str(tmp_path)) is False

    def test_returns_false_for_missing_directory(self, tmp_path: Path) -> None:
        mod = load_retrospective_gate_module()
        assert mod.check_retrospective_file_exists(str(tmp_path)) is False


class TestMainFunction:
    def test_allows_non_push_commands(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mod = load_retrospective_gate_module()
        input_data = {"tool_input": {"command": "git status"}}
        monkeypatch.setattr("sys.stdin", StringIO(json.dumps(input_data)))
        monkeypatch.setattr("sys.stdin.isatty", lambda: False)
        result = mod.main()
        assert result == 0

    def test_allows_push_with_retrospective_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mod = load_retrospective_gate_module()
        sessions_dir = tmp_path / ".agents" / "sessions"
        sessions_dir.mkdir(parents=True)
        retro_dir = tmp_path / ".agents" / "retrospective"
        retro_dir.mkdir(parents=True)
        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        (retro_dir / f"{today}-test.md").write_text("# Retrospective")
        (sessions_dir / f"{today}-session-001.json").write_text('{"session": "test"}')

        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
        input_data = {"tool_input": {"command": "git push origin main"}}
        monkeypatch.setattr("sys.stdin", StringIO(json.dumps(input_data)))
        monkeypatch.setattr("sys.stdin.isatty", lambda: False)
        result = mod.main()
        assert result == 0

    def test_allows_push_with_skip_env_var(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mod = load_retrospective_gate_module()
        sessions_dir = tmp_path / ".agents" / "sessions"
        sessions_dir.mkdir(parents=True)

        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
        monkeypatch.setenv("SKIP_RETROSPECTIVE_GATE", "true")
        input_data = {"tool_input": {"command": "git push origin main"}}
        monkeypatch.setattr("sys.stdin", StringIO(json.dumps(input_data)))
        monkeypatch.setattr("sys.stdin.isatty", lambda: False)
        result = mod.main()
        assert result == 0

    def test_skips_consumer_repos(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mod = load_retrospective_gate_module()
        # No .agents/sessions directory exists

        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
        input_data = {"tool_input": {"command": "git push origin main"}}
        monkeypatch.setattr("sys.stdin", StringIO(json.dumps(input_data)))
        monkeypatch.setattr("sys.stdin.isatty", lambda: False)
        result = mod.main()
        assert result == 0

    def test_blocks_push_without_retrospective(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        mod = load_retrospective_gate_module()
        sessions_dir = tmp_path / ".agents" / "sessions"
        sessions_dir.mkdir(parents=True)
        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        session_content = '{"session": "test", "notes": "no retro"}'
        (sessions_dir / f"{today}-session-001.json").write_text(session_content)

        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
        monkeypatch.delenv("SKIP_RETROSPECTIVE_GATE", raising=False)
        input_data = {"tool_input": {"command": "git push origin main"}}
        monkeypatch.setattr("sys.stdin", StringIO(json.dumps(input_data)))
        monkeypatch.setattr("sys.stdin.isatty", lambda: False)

        # Mock check_documentation_only and check_trivial_session to return False
        with patch.object(mod, "check_documentation_only", return_value=False):
            with patch.object(mod, "check_trivial_session", return_value=False):
                result = mod.main()

        assert result == 2
        captured = capsys.readouterr()
        assert "BLOCKED" in captured.out
        assert "Retrospective" in captured.out

    def test_allows_tty_input(self, monkeypatch: pytest.MonkeyPatch) -> None:
        mod = load_retrospective_gate_module()
        monkeypatch.setattr("sys.stdin.isatty", lambda: True)
        result = mod.main()
        assert result == 0
