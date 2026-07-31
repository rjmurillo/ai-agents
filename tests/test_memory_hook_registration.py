"""The three memory hooks are registered and run under the real contract.

Issue #4011: the hooks existed and were tested, but nothing invoked them, so
no confidence score was ever written outside pytest. These tests pin both
halves: the registration in .claude/settings.json, and the exit code each
invoker returns when Claude Code pipes it a real payload.

The invokers run as subprocesses with a real stdin payload, which is the only
way to catch a wrong exit code: an in-process call cannot see the launcher.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
HOOKS_DIR = REPO_ROOT / ".claude" / "hooks"
SETTINGS = json.loads((REPO_ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))

# (event, invoker path relative to .claude/hooks/)
REGISTERED_HOOKS = (
    ("UserPromptSubmit", "UserPromptSubmit/invoke_memory_recall.py"),
    ("PostToolUse", "PostToolUse/invoke_memory_capture.py"),
    ("SessionEnd", "SessionEnd/invoke_memory_reflection.py"),
)


def _commands(event: str) -> list[str]:
    return [
        hook.get("command", "")
        for group in SETTINGS["hooks"].get(event, [])
        for hook in group.get("hooks", [])
    ]


def _fake_repo(tmp_path: Path) -> Path:
    """A throwaway checkout the hooks can walk up to.

    The reflection hook writes confidence scores back into the memory files
    it loads, so it must never run against the real .serena/memories tree.
    """
    (tmp_path / ".git").mkdir(exist_ok=True)
    memories = tmp_path / ".serena" / "memories" / "workflows"
    memories.mkdir(parents=True, exist_ok=True)
    (memories / "dispatch-groups.md").write_text(
        "# Dispatch Groups (2026-01-01)\n\nHow dispatch group registration works.\n",
        encoding="utf-8",
    )
    return tmp_path


def _run(invoker: str, payload: dict, cwd: Path) -> subprocess.CompletedProcess:
    """Run one invoker the way the harness does: from an arbitrary cwd."""
    env = dict(os.environ)
    env["CLAUDE_PROJECT_DIR"] = str(REPO_ROOT)
    return subprocess.run(
        [sys.executable, "-u", str(HOOKS_DIR / invoker)],
        input=json.dumps(payload),
        capture_output=True,
        encoding="utf-8",
        cwd=str(cwd),
        env=env,
        timeout=60,
        check=False,
    )


class TestRegistration:
    """Every hook is wired into settings.json and its invoker exists."""

    @pytest.mark.unit
    @pytest.mark.parametrize(("event", "invoker"), REGISTERED_HOOKS)
    def test_invoker_exists_inside_hooks_dir(self, event, invoker):
        path = (HOOKS_DIR / invoker).resolve()

        assert path.is_file()
        assert path.is_relative_to(HOOKS_DIR.resolve())

    @pytest.mark.unit
    @pytest.mark.parametrize(("event", "invoker"), REGISTERED_HOOKS)
    def test_settings_registers_the_invoker(self, event, invoker):
        assert any(invoker in command for command in _commands(event))

    @pytest.mark.unit
    def test_no_registration_names_a_missing_script(self):
        missing = [
            command
            for commands in (_commands(event) for event in SETTINGS["hooks"])
            for command in commands
            for token in command.split()
            if token.endswith(".py") and not (REPO_ROOT / token).is_file()
        ]

        assert missing == []


class TestInvokerExitCodes:
    """CLI contract: the exit code each event actually needs."""

    @pytest.mark.unit
    def test_recall_never_returns_two_when_a_memory_matches(self, tmp_path):
        result = _run(
            "UserPromptSubmit/invoke_memory_recall.py",
            {"prompt": "how does dispatch group registration work"},
            _fake_repo(tmp_path),
        )

        assert result.returncode == 0, result.stderr
        assert "<memory-context>" in result.stdout
        assert "<memory-context>" not in result.stderr

    @pytest.mark.unit
    def test_capture_returns_two_for_an_error_payload(self, tmp_path):
        result = _run(
            "PostToolUse/invoke_memory_capture.py",
            {
                "tool_name": "Bash",
                "tool_response": {"stdout": "ERROR: ModuleNotFoundError: No module named foo"},
            },
            tmp_path,
        )

        assert result.returncode == 2, result.stderr
        assert "<memory-suggestion>" in result.stderr

    @pytest.mark.unit
    def test_capture_returns_zero_for_a_benign_payload(self, tmp_path):
        result = _run(
            "PostToolUse/invoke_memory_capture.py",
            {"tool_name": "Bash", "tool_response": {"stdout": "ok"}},
            tmp_path,
        )

        assert result.returncode == 0, result.stderr

    @pytest.mark.unit
    def test_reflection_returns_zero_and_persists_confidence(self, tmp_path):
        repo = _fake_repo(tmp_path)
        memory = repo / ".serena" / "memories" / "workflows" / "dispatch-groups.md"

        result = _run("SessionEnd/invoke_memory_reflection.py", {"reason": "clear"}, repo)

        assert result.returncode == 0, result.stderr
        assert "<session-reflection>" in result.stderr
        assert "confidence:" in memory.read_text(encoding="utf-8")


class TestFailOpenWithoutTheScriptsTree:
    """A consumer install has no scripts/, so every invoker no-ops silently."""

    @pytest.mark.unit
    @pytest.mark.parametrize(("event", "invoker"), REGISTERED_HOOKS)
    def test_missing_package_returns_zero(self, event, invoker, tmp_path):
        env = dict(os.environ)
        env["CLAUDE_PROJECT_DIR"] = str(tmp_path)
        env["PYTHONPATH"] = ""

        result = subprocess.run(
            [sys.executable, "-u", str(HOOKS_DIR / invoker)],
            input="{}",
            capture_output=True,
            encoding="utf-8",
            cwd=str(tmp_path),
            env=env,
            timeout=60,
            check=False,
        )

        assert result.returncode == 0, result.stderr
