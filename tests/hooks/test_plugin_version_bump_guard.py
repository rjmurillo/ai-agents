"""Tests for invoke_plugin_version_bump_guard.

Covers: clean source change passes, not-bumped blocks with the fix hint,
non-plugin changes short-circuit before the validator, config errors fail-open
(do not block), and the resolved base ref is forwarded to find_violations.
"""

from __future__ import annotations

import io
import json
import subprocess
import sys
import types
from pathlib import Path
from unittest.mock import patch

import pytest

HOOK_DIR = Path(__file__).resolve().parents[2] / ".claude" / "hooks" / "PreToolUse"
sys.path.insert(0, str(HOOK_DIR))

import invoke_plugin_version_bump_guard as guard  # noqa: E402


def _stdin(command: str) -> str:
    return json.dumps({"tool_input": {"command": command}})


def _ok(stdout: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=["git"], returncode=0, stdout=stdout, stderr="")


def _violation(**kw):
    """A duck-typed Violation; the guard reads attributes, not the class."""
    return types.SimpleNamespace(
        plugin=kw.get("plugin", "project-toolkit (claude)"),
        manifest=kw.get("manifest", ".claude/.claude-plugin/plugin.json"),
        old_version=kw.get("old_version", "0.3.0"),
        new_version=kw.get("new_version", "0.3.0"),
        reason=kw.get("reason", "not-bumped"),
        touched=kw.get("touched", (".claude/skills/foo/SKILL.md",)),
    )


@pytest.fixture(autouse=True)
def _no_consumer_repo_skip():
    with patch("push_guard_base.skip_if_consumer_repo", return_value=False):
        yield


@pytest.fixture
def push_command(monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO(_stdin("git push origin HEAD")))


def _run(diff_stdout, find_violations_fake, tmp_path):
    """Drive guard.main() with a faked validator module and resolvable base.

    ``push_guard_base`` and the guard both ``import subprocess``, so
    ``subprocess.run`` is one shared object. A single args-aware side effect
    serves every git call: ``diff`` returns the changed-files stdout, while
    ``rev-parse``/``merge-base`` return rc 0 so ``@{push}`` resolves and
    ``_resolve_base`` yields ``"@{push}"``.

    ``validate_plugin_version_bump`` is faked in sys.modules so
    ``_import_validator`` returns it; build/scripts must exist on disk for the
    ``is_dir()`` gate.
    """
    (tmp_path / "build" / "scripts").mkdir(parents=True, exist_ok=True)

    fake = type(sys)("validate_plugin_version_bump")
    fake.find_violations = find_violations_fake

    def _git_side_effect(*args, **_kwargs):
        cmd = args[0] if args else []
        tokens = cmd if isinstance(cmd, list) else []
        if "diff" in tokens:
            return _ok(diff_stdout)
        # rev-parse @{push} -> rc 0 so the guard picks "@{push}" as the base.
        return _ok("")

    with patch("subprocess.run", side_effect=_git_side_effect), \
         patch("push_guard_base.get_project_directory", return_value=str(tmp_path)), \
         patch("invoke_plugin_version_bump_guard.get_project_directory", return_value=str(tmp_path)), \
         patch.dict(sys.modules, {"validate_plugin_version_bump": fake}):
        return guard.main()


class TestClean:
    def test_source_changed_with_bump_passes(self, push_command, tmp_path, capsys):
        def find_violations(changed, *, base_ref, repo_root):
            return [], []

        rc = _run(".claude/skills/foo/SKILL.md\n", find_violations, tmp_path)
        assert rc == 0
        assert "BLOCKED" not in capsys.readouterr().out


class TestNotBumped:
    def test_not_bumped_blocks_with_hint(self, push_command, tmp_path, capsys):
        def find_violations(changed, *, base_ref, repo_root):
            return [_violation()], []

        rc = _run(".claude/skills/foo/SKILL.md\n", find_violations, tmp_path)
        assert rc == 2
        out = capsys.readouterr().out
        assert "## BLOCKED [E_PLUGIN_VERSION_BUMP]" in out
        assert "without a version bump" in out
        assert ".claude/.claude-plugin/plugin.json" in out
        assert "strictly greater" in out


class TestShortCircuit:
    def test_non_plugin_change_skips_validator(self, push_command, tmp_path):
        invoked = {"called": False}

        def find_violations(changed, *, base_ref, repo_root):
            invoked["called"] = True
            return [], []

        rc = _run("README.md\ndocs/x.md\n", find_violations, tmp_path)
        assert rc == 0
        assert invoked["called"] is False


class TestConfigErrorFailsOpen:
    def test_config_error_does_not_block(self, push_command, tmp_path):
        def find_violations(changed, *, base_ref, repo_root):
            return [], [".claude/.claude-plugin/plugin.json: bad version"]

        rc = _run(".claude/skills/foo/SKILL.md\n", find_violations, tmp_path)
        assert rc == 0  # config errors fail-open; CI is authoritative


class TestBaseForwarded:
    def test_resolved_base_forwarded(self, push_command, tmp_path):
        seen = {"base_ref": None}

        def find_violations(changed, *, base_ref, repo_root):
            seen["base_ref"] = base_ref
            return [], []

        _run(".claude/skills/foo/SKILL.md\n", find_violations, tmp_path)
        assert seen["base_ref"] == "@{push}"


class TestImportFailOpen:
    """Import-time failures other than ImportError must fail-open, not crash."""

    def test_non_import_error_during_import_fails_open(self, tmp_path, capsys):
        (tmp_path / "build" / "scripts").mkdir(parents=True, exist_ok=True)

        real_import = __import__

        def boom(name, *args, **kwargs):
            if name == "validate_plugin_version_bump":
                raise RuntimeError("module body blew up at import time")
            return real_import(name, *args, **kwargs)

        # Force the validator import to raise a non-ImportError. The broadened
        # except clause must fail-open rather than let it crash the push.
        with patch("builtins.__import__", side_effect=boom):
            result = guard._import_validator(tmp_path)

        assert result is None
        # An EVENT line on stderr marks the degraded state for telemetry.
        err = capsys.readouterr().err
        assert "import_failed" in err
        assert "RuntimeError" in err


class TestHooksJsonRegistration:
    """The guard must be wired into the push surface or it never runs."""

    _ROOT = Path(__file__).resolve().parents[2]
    _GUARD = "invoke_plugin_version_bump_guard.py"

    def _push_block(self, path: Path) -> list[str]:
        data = json.loads(path.read_text(encoding="utf-8"))
        block = next(
            b
            for b in data["hooks"]["PreToolUse"]
            if b.get("matcher") == "Bash(git push*)"
        )
        return [hook.get("command", "") for hook in block["hooks"]]

    def test_settings_json_registers_guard(self):
        commands = self._push_block(self._ROOT / ".claude" / "settings.json")
        assert any(self._GUARD in cmd for cmd in commands)

    def test_hooks_json_registers_guard(self):
        commands = self._push_block(self._ROOT / ".claude" / "hooks" / "hooks.json")
        assert any(self._GUARD in cmd for cmd in commands)
