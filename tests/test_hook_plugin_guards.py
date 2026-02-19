"""Tests for plugin-mode hook guards.

Verifies that project-specific hooks skip gracefully in consumer repos
(repos without .agents/ directory).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from scripts.hook_utilities.guards import is_project_repo, skip_if_consumer_repo

# Hook scripts that should skip in consumer repos (no .agents/ dir).
PROJECT_SPECIFIC_HOOKS = [
    ".claude/hooks/SessionStart/invoke_session_initialization_enforcer.py",
    ".claude/hooks/SessionStart/invoke_memory_first_enforcer.py",
    ".claude/hooks/invoke_session_start_memory_first.py",
    ".claude/hooks/PreToolUse/invoke_session_log_guard.py",
    ".claude/hooks/PreToolUse/invoke_adr_review_guard.py",
    ".claude/hooks/invoke_adr_change_detection.py",
    ".claude/hooks/PostToolUse/invoke_adr_lifecycle_hook.py",
    ".claude/hooks/invoke_routing_gates.py",
    ".claude/hooks/Stop/invoke_session_validator.py",
    ".claude/hooks/Stop/invoke_skill_learning.py",
    ".claude/hooks/SubagentStop/invoke_qa_agent_validator.py",
    ".claude/hooks/UserPromptSubmit/invoke_autonomous_execution_detector.py",
    ".claude/hooks/invoke_user_prompt_memory_check.py",
]

REPO_ROOT = Path(__file__).resolve().parent.parent


class TestIsProjectRepo:
    def test_returns_true_in_project(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(REPO_ROOT)
        assert is_project_repo() is True

    def test_returns_false_in_consumer(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        assert is_project_repo() is False

    def test_returns_false_when_agents_is_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A .agents file (not directory) should be treated as consumer repo with warning."""
        (tmp_path / ".agents").write_text("not a directory")
        monkeypatch.chdir(tmp_path)
        assert is_project_repo() is False
        captured = capsys.readouterr()
        assert "[WARNING]" in captured.err
        assert "not a directory" in captured.err


class TestSkipIfConsumerRepo:
    def test_returns_false_in_project(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(REPO_ROOT)
        assert skip_if_consumer_repo("test-hook") is False

    def test_returns_true_in_consumer(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.chdir(tmp_path)
        assert skip_if_consumer_repo("test-hook") is True
        captured = capsys.readouterr()
        assert "[SKIP] test-hook" in captured.err
        assert "consumer repo" in captured.err


class TestHookSkipsInConsumerRepo:
    """Run each project-specific hook in a temp dir and verify it exits 0."""

    @pytest.fixture
    def consumer_dir(self, tmp_path: Path) -> Path:
        """Create a minimal consumer repo directory (no .agents/)."""
        (tmp_path / ".claude" / "lib" / "hook_utilities").mkdir(parents=True)
        (tmp_path / ".claude" / "lib" / "github_core").mkdir(parents=True)
        return tmp_path

    @pytest.mark.parametrize("hook_path", PROJECT_SPECIFIC_HOOKS, ids=lambda p: Path(p).stem)
    def test_hook_exits_zero_in_consumer_repo(
        self, hook_path: str, consumer_dir: Path
    ) -> None:
        full_path = REPO_ROOT / hook_path
        if not full_path.exists():
            pytest.skip(f"Hook not found: {hook_path}")

        # Some hooks read stdin for hook input JSON
        hook_input = '{"tool_name": "Bash", "tool_input": {"command": "echo hi"}}'

        result = subprocess.run(
            [sys.executable, str(full_path)],
            capture_output=True,
            text=True,
            cwd=str(consumer_dir),
            input=hook_input,
            timeout=10,
        )

        assert result.returncode == 0, (
            f"{hook_path} exited {result.returncode} in consumer repo.\n"
            f"stdout: {result.stdout[:500]}\n"
            f"stderr: {result.stderr[:500]}"
        )
        # Verify skip message appears (either stdout or stderr)
        combined = result.stdout + result.stderr
        assert "[SKIP]" in combined, (
            f"{hook_path} did not print [SKIP] message in consumer repo.\n"
            f"stdout: {result.stdout[:500]}\n"
            f"stderr: {result.stderr[:500]}"
        )


class TestSyncPluginLib:
    """Test the sync_plugin_lib.py script."""

    def test_check_passes_when_in_sync(self) -> None:
        result = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "sync_plugin_lib.py"), "--check"],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
            timeout=10,
        )
        assert result.returncode == 0, (
            f"Sync check failed (files out of sync):\n{result.stdout}\n{result.stderr}"
        )

    def test_check_detects_drift(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Create mismatched src/dst files and verify --check returns 1."""
        import scripts.sync_plugin_lib as sync_mod

        # Build a minimal src package with one Python file
        src_dir = tmp_path / "src_pkg"
        src_dir.mkdir()
        (src_dir / "__init__.py").write_text('"""Original source."""\n', encoding="utf-8")

        # Build a dst directory with stale content (drift)
        dst_dir = tmp_path / "dst_pkg"
        dst_dir.mkdir()
        (dst_dir / "__init__.py").write_text('"""Stale copy."""\n', encoding="utf-8")

        # Patch module-level config to use our temp directories
        monkeypatch.setattr(sync_mod, "REPO_ROOT", tmp_path)
        monkeypatch.setattr(sync_mod, "SYNC_PAIRS", [("src_pkg", "dst_pkg")])
        monkeypatch.setattr(sync_mod, "IMPORT_CONVERSIONS", [])

        result = sync_mod.main(["--check"])
        assert result == 1
