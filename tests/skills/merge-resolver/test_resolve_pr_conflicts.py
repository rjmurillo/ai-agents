#!/usr/bin/env python3
"""Tests for resolve_pr_conflicts module."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
if TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, TESTS_SKILLS_DIR)

from claude_skills_import import import_skill_script

mod = import_skill_script(".claude/skills/merge-resolver/scripts/resolve_pr_conflicts.py")
is_safe_branch_name = mod.is_safe_branch_name
get_safe_worktree_path = mod.get_safe_worktree_path
is_auto_resolvable = mod.is_auto_resolvable
is_github_runner = mod.is_github_runner
get_repo_info = mod.get_repo_info
resolve_pr_conflicts = mod.resolve_pr_conflicts
AUTO_RESOLVABLE_PATTERNS = mod.AUTO_RESOLVABLE_PATTERNS


class TestIsSafeBranchName:
    """Tests for branch name validation (ADR-015)."""

    def test_valid_branch_names(self) -> None:
        assert is_safe_branch_name("feature/my-branch") is True
        assert is_safe_branch_name("fix/123-bug") is True
        assert is_safe_branch_name("main") is True

    def test_rejects_empty(self) -> None:
        assert is_safe_branch_name("") is False
        assert is_safe_branch_name("   ") is False

    def test_rejects_hyphen_prefix(self) -> None:
        assert is_safe_branch_name("-bad-branch") is False

    def test_rejects_path_traversal(self) -> None:
        assert is_safe_branch_name("../evil") is False
        assert is_safe_branch_name("a/../b") is False

    def test_rejects_control_characters(self) -> None:
        assert is_safe_branch_name("branch\x00name") is False
        assert is_safe_branch_name("branch\x1fname") is False

    def test_rejects_git_special_chars(self) -> None:
        assert is_safe_branch_name("branch~1") is False
        assert is_safe_branch_name("branch^2") is False
        assert is_safe_branch_name("branch:ref") is False
        assert is_safe_branch_name("branch*glob") is False

    def test_rejects_shell_metacharacters(self) -> None:
        assert is_safe_branch_name("branch;rm -rf") is False
        assert is_safe_branch_name("branch|pipe") is False
        assert is_safe_branch_name("branch$(cmd)") is False
        assert is_safe_branch_name("branch`cmd`") is False


class TestGetSafeWorktreePath:
    """Tests for worktree path validation (ADR-015)."""

    def test_constructs_valid_path(self, tmp_path: Path) -> None:
        # Hermetic: derive the repo name from a stubbed remote, not from
        # whatever origin URL the host checkout happens to have.
        repo_info = mod.RepoInfo(owner="rjmurillo", repo="ai-agents")
        with patch.object(mod, "get_repo_info", return_value=repo_info):
            result = get_safe_worktree_path(str(tmp_path), 123)
        assert "ai-agents-pr-123" in result
        assert str(tmp_path) in result

    def test_rejects_negative_pr_number(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="Invalid PR number"):
            get_safe_worktree_path(str(tmp_path), -1)

    def test_rejects_zero_pr_number(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="Invalid PR number"):
            get_safe_worktree_path(str(tmp_path), 0)


class TestIsAutoResolvable:
    """Tests for auto-resolvable file detection."""

    def test_handoff_is_resolvable(self) -> None:
        assert is_auto_resolvable(".agents/HANDOFF.md") is True

    def test_session_files_resolvable(self) -> None:
        assert is_auto_resolvable(".agents/sessions/2025-01-01.json") is True

    def test_serena_memories_resolvable(self) -> None:
        assert is_auto_resolvable(".serena/memories/test.md") is True

    def test_lock_files_resolvable(self) -> None:
        assert is_auto_resolvable("package-lock.json") is True
        assert is_auto_resolvable("pnpm-lock.yaml") is True
        assert is_auto_resolvable("yarn.lock") is True

    def test_source_code_not_resolvable(self) -> None:
        assert is_auto_resolvable("src/main.py") is False
        assert is_auto_resolvable("app/controllers/main.rb") is False

    def test_skill_files_resolvable(self) -> None:
        assert is_auto_resolvable(".claude/skills/test/SKILL.md") is True


class TestIsGithubRunner:
    """Tests for GitHub Actions detection."""

    def test_detects_github_actions(self) -> None:
        with patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}):
            assert is_github_runner() is True

    def test_returns_false_locally(self) -> None:
        env = os.environ.copy()
        env.pop("GITHUB_ACTIONS", None)
        with patch.dict(os.environ, env, clear=True):
            assert is_github_runner() is False


class TestResolvePrConflicts:
    """Tests for resolve_pr_conflicts function."""

    def test_rejects_unsafe_branch_name(self) -> None:
        result = resolve_pr_conflicts(
            pr_number=1,
            branch_name="-evil-branch",
            target_branch="main",
        )
        assert result["success"] is False
        assert "unsafe branch name" in result["message"]

    def test_rejects_unsafe_target_branch(self) -> None:
        result = resolve_pr_conflicts(
            pr_number=1,
            branch_name="good-branch",
            target_branch="main;rm -rf /",
        )
        assert result["success"] is False
        assert "unsafe target branch" in result["message"]

    def test_result_structure(self) -> None:
        result = resolve_pr_conflicts(
            pr_number=1,
            branch_name="-evil-branch",
            target_branch="main",
        )
        assert "success" in result
        assert "message" in result
        assert "files_resolved" in result
        assert "files_blocked" in result


class TestGetRepoInfo:
    """Tests for get_repo_info function."""

    def _make_proc(self, stdout: str = "", returncode: int = 0) -> MagicMock:
        proc = MagicMock()
        proc.returncode = returncode
        proc.stdout = stdout
        proc.stderr = ""
        return proc

    def test_parses_https_remote(self) -> None:
        with patch("subprocess.run", return_value=self._make_proc("https://github.com/owner/repo.git")):
            result = get_repo_info()
        assert result.owner == "owner"
        assert result.repo == "repo"

    def test_parses_ssh_remote(self) -> None:
        with patch("subprocess.run", return_value=self._make_proc("git@github.com:owner/repo.git")):
            result = get_repo_info()
        assert result.owner == "owner"
        assert result.repo == "repo"

    def test_raises_for_non_github(self) -> None:
        with patch("subprocess.run", return_value=self._make_proc("https://gitlab.com/owner/repo.git")):
            with pytest.raises(RuntimeError, match="Could not parse"):
                get_repo_info()

    def test_raises_for_no_remote(self) -> None:
        with patch(
            "subprocess.run",
            side_effect=subprocess.CalledProcessError(1, "git"),
        ):
            with pytest.raises(RuntimeError, match="Could not determine git remote origin"):
                get_repo_info()


is_plugin_manifest = mod.is_plugin_manifest
resolve_plugin_manifest_conflict = mod.resolve_plugin_manifest_conflict
_resolve_conflicted_file = mod._resolve_conflicted_file
_parse_plain_semver = mod._parse_plain_semver


class TestIsPluginManifest:
    """Detection of packaged plugin manifests (issue #2543)."""

    def test_claude_plugin_manifest(self) -> None:
        assert is_plugin_manifest(".claude/.claude-plugin/plugin.json")

    def test_copilot_plugin_manifest(self) -> None:
        assert is_plugin_manifest("src/copilot-cli/.claude-plugin/plugin.json")

    def test_backslash_path_normalized(self) -> None:
        assert is_plugin_manifest(r".claude\.claude-plugin\plugin.json")

    def test_root_plugin_json_is_not_manifest(self) -> None:
        assert not is_plugin_manifest("plugin.json")

    def test_other_skill_files_are_not_manifests(self) -> None:
        assert not is_plugin_manifest(".claude/skills/github/SKILL.md")


class TestParsePlainSemver:
    """Strict MAJOR.MINOR.PATCH parsing; anything else falls back to manual."""

    def test_plain_version(self) -> None:
        assert _parse_plain_semver("0.5.168") == (0, 5, 168)

    def test_prerelease_rejected(self) -> None:
        assert _parse_plain_semver("0.6.0-rc.1") is None

    def test_build_metadata_rejected(self) -> None:
        assert _parse_plain_semver("0.6.0+build.5") is None

    def test_malformed_rejected(self) -> None:
        assert _parse_plain_semver("not-a-version") is None


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


MANIFEST = ".claude-plugin/plugin.json"


def _make_manifest_conflict(
    repo: Path,
    base: str,
    ours: str,
    theirs: str,
) -> None:
    """Create a real merge conflict on the plugin manifest in a tmp repo.

    ``ours`` is the PR-branch content (checked out), ``theirs`` is the
    target-branch content being merged in, matching the resolver's merge
    direction (merge main into the PR branch).
    """
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    # Hermetic: a host-level commit.gpgsign with an unreachable signer would
    # fail every fixture commit and dissolve the conflict under test.
    _git(repo, "config", "commit.gpgsign", "false")
    manifest = repo / MANIFEST
    manifest.parent.mkdir(parents=True)
    manifest.write_text(base, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "base")
    _git(repo, "checkout", "-b", "pr")
    manifest.write_text(ours, encoding="utf-8")
    _git(repo, "commit", "-am", "ours")
    _git(repo, "checkout", "main")
    manifest.write_text(theirs, encoding="utf-8")
    _git(repo, "commit", "-am", "theirs")
    _git(repo, "checkout", "pr")
    merge = _git(repo, "merge", "main")
    assert merge.returncode != 0, "expected a merge conflict"


def _manifest_json(version: str, description: str = "toolkit") -> str:
    return (
        '{\n  "name": "project-toolkit",\n'
        f'  "description": "{description}",\n'
        f'  "version": "{version}"\n}}\n'
    )


class TestResolvePluginManifestConflict:
    """Version-only conflicts resolve to one patch bump above the higher side."""

    def test_version_only_conflict_resolves_to_bumped_max(self, tmp_path: Path) -> None:
        _make_manifest_conflict(
            tmp_path,
            base=_manifest_json("0.5.1"),
            ours=_manifest_json("0.5.2"),
            theirs=_manifest_json("0.5.3"),
        )
        assert resolve_plugin_manifest_conflict(MANIFEST, cwd=str(tmp_path)) is True
        content = (tmp_path / MANIFEST).read_text(encoding="utf-8")
        assert '"version": "0.5.4"' in content
        assert "<<<<<<<" not in content
        staged = _git(tmp_path, "diff", "--name-only", "--cached").stdout
        assert MANIFEST in staged
        unmerged = _git(tmp_path, "diff", "--name-only", "--diff-filter=U").stdout
        assert MANIFEST not in unmerged

    def test_resolves_above_ours_when_ours_higher(self, tmp_path: Path) -> None:
        _make_manifest_conflict(
            tmp_path,
            base=_manifest_json("0.5.1"),
            ours=_manifest_json("0.5.9"),
            theirs=_manifest_json("0.5.3"),
        )
        assert resolve_plugin_manifest_conflict(MANIFEST, cwd=str(tmp_path)) is True
        content = (tmp_path / MANIFEST).read_text(encoding="utf-8")
        assert '"version": "0.5.10"' in content

    def test_non_version_difference_blocks(self, tmp_path: Path) -> None:
        _make_manifest_conflict(
            tmp_path,
            base=_manifest_json("0.5.1"),
            ours=_manifest_json("0.5.2", description="changed on pr"),
            theirs=_manifest_json("0.5.3"),
        )
        assert resolve_plugin_manifest_conflict(MANIFEST, cwd=str(tmp_path)) is False
        unmerged = _git(tmp_path, "diff", "--name-only", "--diff-filter=U").stdout
        assert MANIFEST in unmerged

    def test_prerelease_version_blocks(self, tmp_path: Path) -> None:
        _make_manifest_conflict(
            tmp_path,
            base=_manifest_json("0.5.1"),
            ours=_manifest_json("0.5.2"),
            theirs=_manifest_json("0.6.0-rc.1"),
        )
        assert resolve_plugin_manifest_conflict(MANIFEST, cwd=str(tmp_path)) is False

    def test_malformed_json_blocks(self, tmp_path: Path) -> None:
        _make_manifest_conflict(
            tmp_path,
            base=_manifest_json("0.5.1"),
            ours='{"name": "broken",\n',
            theirs=_manifest_json("0.5.3"),
        )
        assert resolve_plugin_manifest_conflict(MANIFEST, cwd=str(tmp_path)) is False

    def test_no_conflict_stages_returns_false(self, tmp_path: Path) -> None:
        _git(tmp_path, "init", "-b", "main")
        assert resolve_plugin_manifest_conflict(MANIFEST, cwd=str(tmp_path)) is False


class TestResolveConflictedFileDispatch:
    """_resolve_conflicted_file routes manifests, patterns, and failures."""

    def _result(self) -> dict[str, Any]:
        return {"success": False, "message": "", "files_resolved": [], "files_blocked": []}

    def test_plugin_manifest_resolved(self) -> None:
        result = self._result()
        with patch.object(mod, "resolve_plugin_manifest_conflict", return_value=True):
            status = _resolve_conflicted_file(".claude/.claude-plugin/plugin.json", result)
        assert status == "resolved"
        assert result["files_resolved"] == [".claude/.claude-plugin/plugin.json"]

    def test_plugin_manifest_unresolvable_blocks(self) -> None:
        result = self._result()
        with patch.object(mod, "resolve_plugin_manifest_conflict", return_value=False):
            status = _resolve_conflicted_file(".claude/.claude-plugin/plugin.json", result)
        assert status == "blocked"
        assert result["files_blocked"] == [".claude/.claude-plugin/plugin.json"]

    def test_auto_resolvable_takes_theirs(self) -> None:
        result = self._result()
        ok = MagicMock(returncode=0)
        with patch.object(mod, "_run_git", return_value=ok) as run_git:
            status = _resolve_conflicted_file(".agents/HANDOFF.md", result)
        assert status == "resolved"
        assert result["files_resolved"] == [".agents/HANDOFF.md"]
        assert run_git.call_args_list[0].args[:2] == ("checkout", "--theirs")

    def test_unknown_file_blocks(self) -> None:
        result = self._result()
        status = _resolve_conflicted_file("src/main.py", result)
        assert status == "blocked"
        assert result["files_blocked"] == ["src/main.py"]

    def test_checkout_failure_is_error(self) -> None:
        result = self._result()
        fail = MagicMock(returncode=1)
        with patch.object(mod, "_run_git", return_value=fail):
            status = _resolve_conflicted_file(".agents/HANDOFF.md", result)
        assert status == "error"
        assert "checkout --theirs" in result["message"]
