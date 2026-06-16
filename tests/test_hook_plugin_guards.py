"""Tests for plugin-mode hook guards.

Verifies that project-specific hooks skip gracefully in consumer repos
(repos without .agents/ directory).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.hook_utilities import guards
from scripts.hook_utilities.guards import is_project_repo, skip_if_consumer_repo

# Hook scripts that should skip in consumer repos (no .agents/ dir).
PROJECT_SPECIFIC_HOOKS = [
    ".claude/hooks/SessionStart/invoke_session_initialization_enforcer.py",
    ".claude/hooks/SessionStart/invoke_memory_first_enforcer.py",
    ".claude/hooks/invoke_session_start_memory_first.py",
    ".claude/hooks/PreToolUse/invoke_session_log_guard.py",
    ".claude/hooks/PreToolUse/invoke_adr_review_guard.py",
    ".claude/hooks/PreToolUse/invoke_skill_first_guard.py",
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
    """is_project_repo resolves identity from the env override or git remote (#2610)."""

    def test_env_override_true(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AI_AGENTS_PROJECT_REPO", "1")
        assert is_project_repo() is True

    def test_env_override_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AI_AGENTS_PROJECT_REPO", "0")
        assert is_project_repo() is False

    def test_remote_ai_agents_is_project(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("AI_AGENTS_PROJECT_REPO", raising=False)
        guards._origin_repo_cache.clear()
        monkeypatch.setattr(guards, "_remote_repo_name", lambda _root: "ai-agents")
        assert is_project_repo() is True

    def test_remote_other_repo_is_consumer(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # A consumer repo with its own .agents/ (e.g. a vendored install) must
        # not be mistaken for the project repo just because that dir exists.
        monkeypatch.delenv("AI_AGENTS_PROJECT_REPO", raising=False)
        guards._origin_repo_cache.clear()
        monkeypatch.setattr(
            guards, "_remote_repo_name", lambda _root: "Wcd.Infra.ConfigurationGeneration2"
        )
        assert is_project_repo() is False

    def test_no_remote_is_not_project(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("AI_AGENTS_PROJECT_REPO", raising=False)
        guards._origin_repo_cache.clear()
        monkeypatch.setattr(guards, "_remote_repo_name", lambda _root: None)
        assert is_project_repo() is False


class TestRemoteRepoName:
    """_remote_repo_name parses the origin URL across HTTPS and SSH forms."""

    @pytest.mark.parametrize(
        "url,expected",
        [
            ("https://github.com/rjmurillo/ai-agents.git", "ai-agents"),
            ("https://github.com/rjmurillo/ai-agents", "ai-agents"),
            ("git@github.com:rjmurillo/ai-agents.git", "ai-agents"),
            (
                "git@github.com:org/Wcd.Infra.ConfigurationGeneration2.git",
                "Wcd.Infra.ConfigurationGeneration2",
            ),
        ],
    )
    def test_parses_remote_url(
        self, url: str, expected: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(guards.shutil, "which", lambda _name: "git")
        monkeypatch.setattr(
            guards.subprocess,
            "run",
            lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout=url + "\n", stderr=""),
        )
        assert guards._remote_repo_name("/repo") == expected

    def test_no_origin_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(guards.shutil, "which", lambda _name: "git")

        def raise_no_origin(*a, **k):
            raise subprocess.CalledProcessError(2, a, stderr="no origin")

        monkeypatch.setattr(guards.subprocess, "run", raise_no_origin)
        assert guards._remote_repo_name("/repo") is None

    def test_origin_lookup_uses_utf8_and_check_true(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured_kwargs: dict[str, object] = {}

        def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
            captured_kwargs.update(kwargs)
            return subprocess.CompletedProcess(
                ["git", "-C", "/repo", "remote", "get-url", "origin"],
                0,
                stdout="ai-agents\n",
                stderr="",
            )

        monkeypatch.setattr(guards.shutil, "which", lambda _name: "git")
        monkeypatch.setattr(guards.subprocess, "run", fake_run)

        assert guards._remote_repo_name("/repo") == "ai-agents"
        assert captured_kwargs["encoding"] == "utf-8"
        assert captured_kwargs["errors"] == "replace"
        assert captured_kwargs["check"] is True

    def test_git_missing_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(guards.shutil, "which", lambda _name: None)
        assert guards._remote_repo_name("/repo") is None


class TestSkipIfConsumerRepo:
    def test_returns_false_in_project(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AI_AGENTS_PROJECT_REPO", "1")
        assert skip_if_consumer_repo("test-hook") is False

    def test_returns_true_in_consumer(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setenv("AI_AGENTS_PROJECT_REPO", "0")
        assert skip_if_consumer_repo("test-hook") is True
        captured = capsys.readouterr()
        assert "[SKIP] test-hook" in captured.err
        assert "consumer repo" in captured.err

    def test_skips_when_repo_identity_unknown(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.delenv("AI_AGENTS_PROJECT_REPO", raising=False)
        guards._origin_repo_cache.clear()
        monkeypatch.setattr(guards, "get_project_directory", lambda: "/repo")
        monkeypatch.setattr(guards, "_remote_repo_name", lambda _root: None)

        assert skip_if_consumer_repo("test-hook") is True
        captured = capsys.readouterr()
        assert "[SKIP] test-hook" in captured.err
        assert "cannot verify ai-agents project repo identity" in captured.err


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

        # Force consumer-repo identity for the spawned hook. The suite-wide
        # autouse default sets AI_AGENTS_PROJECT_REPO=1; override to "0" so the
        # subprocess takes the skip path (#2610).
        env = {**os.environ, "AI_AGENTS_PROJECT_REPO": "0"}

        result = subprocess.run(
            [sys.executable, str(full_path)],
            capture_output=True,
            text=True,
            cwd=str(consumer_dir),
            input=hook_input,
            timeout=10,
            env=env,
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
