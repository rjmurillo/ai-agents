"""Test that the analyst agent's resolve_project_toolkit_scripts function
finds the github skill scripts from multiple working directories and
from an installed-plugin layout."""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(subprocess.check_output(
    ["git", "rev-parse", "--show-toplevel"], text=True
).strip())

RESOLVER_SCRIPT = """\
resolve_project_toolkit_scripts() {
  local repo_root
  repo_root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
  for root in \\
    "${COPILOT_PLUGIN_ROOT:-}" \\
    "${CLAUDE_PLUGIN_ROOT:-}" \\
    "$repo_root/.claude" \\
    "${HOME:-}/.copilot/installed-plugins/_direct/project-toolkit" \\
    "${HOME:-}/.copilot/installed-plugins"/*/project-toolkit \\
    "${HOME:-}/.claude/plugins/cache"/*/project-toolkit; do
    if [ -n "$root" ] && [ -d "$root/skills/github/scripts" ]; then
      printf '%s\\n' "$root/skills/github/scripts"
      return 0
    fi
  done
  return 1
}
resolve_project_toolkit_scripts
"""


def _run_resolver(cwd: Path, env_override: dict[str, str] | None = None) -> str:
    """Run the resolver from a given cwd and return stdout (the resolved path)."""
    env = os.environ.copy()
    # Clear plugin-root vars so we test the fallback chain
    env.pop("COPILOT_PLUGIN_ROOT", None)
    env.pop("CLAUDE_PLUGIN_ROOT", None)
    if env_override:
        env.update(env_override)
    result = subprocess.run(
        ["bash", "-c", RESOLVER_SCRIPT],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        env=env,
    )
    return result.stdout.strip(), result.returncode


class TestResolveFromRepoRoot:
    """Resolver finds scripts when cwd is repo root."""

    def test_resolves_from_repo_root(self) -> None:
        path, rc = _run_resolver(REPO_ROOT)
        assert rc == 0
        assert Path(path).is_dir()
        assert (Path(path) / "pr").is_dir()


class TestResolveFromSubdirectory:
    """Resolver finds scripts when cwd is a subdirectory of the repo."""

    def test_resolves_from_subdirectory(self) -> None:
        subdir = REPO_ROOT / "tests"
        path, rc = _run_resolver(subdir)
        assert rc == 0
        assert Path(path).is_dir()
        assert (Path(path) / "pr").is_dir()

    def test_resolves_from_deep_subdirectory(self) -> None:
        subdir = REPO_ROOT / "src" / "claude"
        path, rc = _run_resolver(subdir)
        assert rc == 0
        assert Path(path).is_dir()


class TestResolveViaEnvVar:
    """Resolver prefers env var when set."""

    def test_copilot_plugin_root_takes_precedence(self) -> None:
        path, rc = _run_resolver(
            REPO_ROOT,
            env_override={"COPILOT_PLUGIN_ROOT": str(REPO_ROOT / ".claude")},
        )
        assert rc == 0
        assert path == str(REPO_ROOT / ".claude" / "skills" / "github" / "scripts")

    def test_claude_plugin_root_fallback(self) -> None:
        path, rc = _run_resolver(
            REPO_ROOT,
            env_override={"CLAUDE_PLUGIN_ROOT": str(REPO_ROOT / ".claude")},
        )
        assert rc == 0
        assert path == str(REPO_ROOT / ".claude" / "skills" / "github" / "scripts")


class TestResolveFromInstalledPluginLayout:
    """Resolver finds scripts from a simulated installed-plugin directory."""

    def test_installed_plugin_layout(self, tmp_path: Path) -> None:
        # Simulate ~/.copilot/installed-plugins/_direct/project-toolkit
        fake_home = tmp_path / "home"
        plugin_dir = fake_home / ".copilot" / "installed-plugins" / "_direct" / "project-toolkit"
        scripts_dir = plugin_dir / "skills" / "github" / "scripts" / "pr"
        scripts_dir.mkdir(parents=True)

        # Run from outside any git repo so env var and git-root fail
        non_git_dir = tmp_path / "not-a-repo"
        non_git_dir.mkdir()

        path, rc = _run_resolver(
            non_git_dir,
            env_override={"HOME": str(fake_home)},
        )
        assert rc == 0
        assert path == str(plugin_dir / "skills" / "github" / "scripts")

    def test_fails_when_no_root_found(self, tmp_path: Path) -> None:
        """Resolver returns non-zero when no candidate resolves."""
        non_git_dir = tmp_path / "empty"
        non_git_dir.mkdir()
        fake_home = tmp_path / "no-plugins"
        fake_home.mkdir()

        _, rc = _run_resolver(
            non_git_dir,
            env_override={"HOME": str(fake_home)},
        )
        assert rc == 1
