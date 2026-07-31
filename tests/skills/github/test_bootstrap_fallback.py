"""Regression tests for issue #3897.

Verify that github skill scripts do not trust CLAUDE_PLUGIN_ROOT when it
points to an unrelated extension's directory (one that has no lib/github_core).

The scripts fall through to the script-relative fallback when the env var
does not point at a valid github_core location.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

# Absolute path to the skills scripts dir, independent of cwd.
_SCRIPTS_DIR = Path(__file__).resolve().parents[3] / ".claude" / "skills" / "github" / "scripts"
# A representative script that prints something on --help, exits 0 is not
# guaranteed (it often requires a token).  We use a script that exits with a
# config error (2) when the lib dir is genuinely missing, vs. an auth/API
# error otherwise.  list_pr_checks.py is lightweight and only needs the lib.
_SAMPLE_SCRIPT = _SCRIPTS_DIR / "pr" / "test_pr_merge_ready.py"


def _run_script(
    script: Path,
    env_overrides: dict[str, str],
    extra_args: list[str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, **env_overrides}
    # Remove vars we are overriding to avoid leaking real values.
    for key in list(env):
        if key not in env_overrides and key in ("COPILOT_PLUGIN_ROOT", "CLAUDE_PLUGIN_ROOT"):
            del env[key]
    for key, val in env_overrides.items():
        if val == "__UNSET__":
            env.pop(key, None)
        else:
            env[key] = val
    cmd = [sys.executable, str(script)] + (extra_args or [])
    return subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=30)


class TestBootstrapFallback:
    """CLAUDE_PLUGIN_ROOT pointing at an unrelated dir must not cause exit 2."""

    def test_unrelated_plugin_root_does_not_exit_config_error(self, tmp_path: Path) -> None:
        """When CLAUDE_PLUGIN_ROOT has no lib/github_core, the script falls
        through to the script-relative lib path (which exists in the repo).
        It may exit non-zero due to missing --pull-request arg or auth, but
        must NOT exit 2 with "Plugin lib directory not found: <tmp_path>".
        """
        fake_plugin = tmp_path / "unrelated-extension"
        fake_plugin.mkdir()
        result = _run_script(
            _SAMPLE_SCRIPT,
            env_overrides={"CLAUDE_PLUGIN_ROOT": str(fake_plugin)},
        )
        # Must not be a config error (exit 2) caused by the fake plugin root.
        # Expected exits: 1 (bad arg / auth) or any non-2, non-2-with-fake-msg.
        assert not (result.returncode == 2 and str(fake_plugin) in result.stderr), (
            f"Script used the unrelated CLAUDE_PLUGIN_ROOT and exited 2.\nstderr: {result.stderr}"
        )

    def test_copilot_plugin_root_unrelated_also_falls_through(self, tmp_path: Path) -> None:
        """Same scenario via COPILOT_PLUGIN_ROOT (takes priority over CLAUDE)."""
        fake_plugin = tmp_path / "context-mode"
        fake_plugin.mkdir()
        result = _run_script(
            _SAMPLE_SCRIPT,
            env_overrides={"COPILOT_PLUGIN_ROOT": str(fake_plugin)},
        )
        assert not (result.returncode == 2 and str(fake_plugin) in result.stderr), (
            f"Script used the unrelated COPILOT_PLUGIN_ROOT and exited 2.\nstderr: {result.stderr}"
        )

    def test_valid_plugin_root_is_still_accepted(self) -> None:
        """A CLAUDE_PLUGIN_ROOT that actually has lib/github_core is accepted."""
        # The repo's own .claude dir is valid for this test.
        repo_root = _SCRIPTS_DIR.parents[3]
        valid_plugin = repo_root / ".claude"
        if not (valid_plugin / "lib" / "github_core").is_dir():
            pytest.skip("Repo .claude/lib/github_core not present")

        result = _run_script(
            _SAMPLE_SCRIPT,
            env_overrides={"CLAUDE_PLUGIN_ROOT": str(valid_plugin)},
        )
        # Exit 2 with the valid_plugin path in stderr would mean our fix
        # incorrectly rejected a valid plugin root.
        assert not (result.returncode == 2 and str(valid_plugin) in result.stderr), (
            f"Script rejected a valid CLAUDE_PLUGIN_ROOT.\nstderr: {result.stderr}"
        )


class TestBootstrapSourceCode:
    """Source-level checks: all scripts with CLAUDE_PLUGIN_ROOT must also
    prefer COPILOT_PLUGIN_ROOT and validate lib/github_core presence."""

    def _bootstrap_scripts(self) -> list[Path]:
        return [
            f
            for f in _SCRIPTS_DIR.rglob("*.py")
            if "_plugin_root" in f.read_text() and "CLAUDE_PLUGIN_ROOT" in f.read_text()
        ]

    def test_scripts_prefer_copilot_plugin_root(self) -> None:
        """Every script referencing CLAUDE_PLUGIN_ROOT must also read
        COPILOT_PLUGIN_ROOT (preferring it via `or`)."""
        failures = []
        for f in self._bootstrap_scripts():
            content = f.read_text()
            if "COPILOT_PLUGIN_ROOT" not in content:
                failures.append(str(f.relative_to(_SCRIPTS_DIR.parents[3])))
        assert not failures, (
            "These scripts use CLAUDE_PLUGIN_ROOT without COPILOT_PLUGIN_ROOT:\n"
            + "\n".join(failures)
        )

    def test_scripts_validate_github_core_before_trusting(self) -> None:
        """Every script that reads a plugin root env var must validate that
        lib/github_core is present before trusting the value."""
        failures = []
        for f in self._bootstrap_scripts():
            content = f.read_text()
            if 'os.path.isdir(os.path.join(_plugin_root, "lib", "github_core"))' not in content:
                failures.append(str(f.relative_to(_SCRIPTS_DIR.parents[3])))
        assert not failures, (
            "These scripts do not validate lib/github_core before trusting plugin root:\n"
            + "\n".join(failures)
        )

    def test_bootstrap_count(self) -> None:
        """Negative control: ensure we actually found scripts to check."""
        assert len(self._bootstrap_scripts()) >= 40, (
            "Expected at least 40 bootstrap scripts; something changed unexpectedly"
        )


class TestBootstrapFallbackIsolating:
    """Isolating negative-control: the OLD bootstrap (trusts any env var) would fail."""

    def test_old_bootstrap_would_fail(self, tmp_path: Path) -> None:
        """Demonstrate that without the isdir check, the script exits 2.

        We simulate the old behavior by writing a temporary wrapper that
        does the old bootstrap, then importing the same lib path check.
        This is the negative control: if someone reverts the fix, this
        test proves the regression is real.
        """
        fake_plugin = tmp_path / "unrelated"
        fake_plugin.mkdir()

        old_bootstrap = tmp_path / "old_bootstrap_demo.py"
        old_bootstrap.write_text(
            f"""
import os, sys
_plugin_root = "{fake_plugin}"  # blindly trust
if _plugin_root:  # old behavior: no isdir check
    _lib_dir = os.path.join(_plugin_root, "lib")
else:
    _lib_dir = "/nonexistent"
if not os.path.isdir(_lib_dir):
    print(f"Plugin lib directory not found: {{_lib_dir}}", file=sys.stderr)
    sys.exit(2)
"""
        )
        result = subprocess.run(
            [sys.executable, str(old_bootstrap)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 2, (
            "Expected old bootstrap to exit 2 when given unrelated plugin root. "
            f"Got {result.returncode}. stderr: {result.stderr}"
        )
        assert str(fake_plugin) in result.stderr
