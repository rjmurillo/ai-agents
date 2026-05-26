"""Tests for invoke_manifest_count_guard.

Covers acceptance criteria from issue #1884 TASK-015-3: counts agree pass,
mismatch blocks with hint, config error blocks, empty changeset short-
circuits, and the explicit ``repo_root`` parameter is forwarded to the
validator (pre-mortem R-F mitigation).
"""

from __future__ import annotations

import io
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

HOOK_DIR = Path(__file__).resolve().parents[2] / ".claude" / "hooks" / "PreToolUse"
sys.path.insert(0, str(HOOK_DIR))

import invoke_manifest_count_guard as guard  # noqa: E402


def _stdin(command: str) -> str:
    return json.dumps({"tool_input": {"command": command}})


def _diff(stdout: str) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["git"], returncode=0, stdout=stdout, stderr=""
    )


@pytest.fixture(autouse=True)
def _no_consumer_repo_skip():
    with patch("push_guard_base.skip_if_consumer_repo", return_value=False):
        yield


@pytest.fixture
def push_command(monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO(_stdin("git push origin HEAD")))


def _run(diff_stdout, validator_fake, tmp_path):
    """Patch git diff and the imported validator function.

    The validator lives on the guard module after the lazy import inside
    ``_validate``. Patch it via ``patch.dict(sys.modules)`` so each test sees
    a fresh fake without leaking into other tests.
    """
    fake_module = type(sys)("validate_marketplace_counts")
    fake_module.validate_known_marketplaces = validator_fake

    with patch("push_guard_base.subprocess.run", return_value=_diff(diff_stdout)), \
         patch("push_guard_base.get_project_directory", return_value=str(tmp_path)), \
         patch("invoke_manifest_count_guard.get_project_directory", return_value=str(tmp_path)), \
         patch.dict(sys.modules, {"validate_marketplace_counts": fake_module}):
        return guard.main()


class TestCountsMatch:
    def test_counts_match_returns_zero(self, push_command, tmp_path, capsys):
        def validator(repo_root, **_kw):
            print("counts are up to date.")
            return 0

        rc = _run(".claude-plugin/marketplace.json\n", validator, tmp_path)
        assert rc == 0
        assert "BLOCKED" not in capsys.readouterr().out


class TestMismatch:
    def test_mismatch_blocks_with_hint(self, push_command, tmp_path, capsys):
        def validator(repo_root, **_kw):
            print("Stale counts detected:")
            print(
                "  project-toolkit: 'lifecycle hook' declared=29, actual=30"
            )
            return 1

        rc = _run(".claude-plugin/marketplace.json\n", validator, tmp_path)
        assert rc == 2
        out = capsys.readouterr().out
        assert "## BLOCKED [E_MANIFEST_COUNT]" in out
        assert "Stale counts detected:" in out
        assert "lifecycle hook" in out
        assert "validate_marketplace_counts.py --fix" in out

    def test_mismatch_on_skill_change(self, push_command, tmp_path):
        def validator(repo_root, **_kw):
            print("  project-toolkit: 'reusable skill' declared=68, actual=69")
            return 1

        rc = _run(".claude/skills/foo/SKILL.md\n", validator, tmp_path)
        assert rc == 2


class TestConfigError:
    def test_config_error_blocks(self, push_command, tmp_path, capsys):
        def validator(repo_root, **_kw):
            print("Error: unknown strategy 'xyz'", file=sys.stderr)
            print("Error: unknown strategy 'xyz'")
            return 2

        rc = _run(".claude/commands/foo.md\n", validator, tmp_path)
        assert rc == 2
        out = capsys.readouterr().out
        assert "config error" in out


class TestEmptyChangeset:
    def test_no_manifest_files_skips_validator(self, push_command, tmp_path):
        invoked = {"validator": False}

        def validator(repo_root, **_kw):
            invoked["validator"] = True
            return 0

        rc = _run("src/foo.py\nREADME.md\n", validator, tmp_path)
        assert rc == 0
        assert invoked["validator"] is False


class TestRepoRootForwarded:
    def test_repo_root_passed_explicitly(self, push_command, tmp_path):
        """Pre-mortem R-F: hook MUST forward project_dir as repo_root."""
        seen = {"repo_root": None, "kwargs": None}

        def validator(repo_root=None, **kwargs):
            seen["repo_root"] = repo_root
            seen["kwargs"] = kwargs
            return 0

        _run(".claude-plugin/marketplace.json\n", validator, tmp_path)
        assert seen["repo_root"] == tmp_path
        assert isinstance(seen["repo_root"], Path)


class TestHooksJsonRegistration:
    def test_hooks_json_includes_manifest_count_guard(self):
        hooks_path = (
            Path(__file__).resolve().parents[2]
            / ".claude"
            / "hooks"
            / "hooks.json"
        )
        data = json.loads(hooks_path.read_text(encoding="utf-8"))
        push_block = next(
            block
            for block in data["hooks"]["PreToolUse"]
            if block.get("matcher") == "Bash(git push*)"
        )
        commands = [hook.get("command", "") for hook in push_block["hooks"]]
        assert any("invoke_manifest_count_guard.py" in cmd for cmd in commands)

    def test_settings_json_includes_manifest_count_guard(self):
        """Source-of-truth check; see test_pr_description_guard for rationale."""
        settings_path = (
            Path(__file__).resolve().parents[2] / ".claude" / "settings.json"
        )
        data = json.loads(settings_path.read_text(encoding="utf-8"))
        push_block = next(
            block
            for block in data["hooks"]["PreToolUse"]
            if block.get("matcher") == "Bash(git push*)"
        )
        commands = [hook.get("command", "") for hook in push_block["hooks"]]
        assert any("invoke_manifest_count_guard.py" in cmd for cmd in commands)
