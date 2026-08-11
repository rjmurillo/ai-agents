"""Tests for memory_git_targets.py.

Covers: positive validation, path traversal, absolute path, symlink escape,
untracked target, duplicate target, malformed manifest, and exact-source
restore.  All git operations use isolated temp repos.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

# Make the script importable
SKILL_SCRIPTS = (
    Path(__file__).resolve().parents[3]
    / ".claude" / "skills" / "memory-consolidate" / "scripts"
)
sys.path.insert(0, str(SKILL_SCRIPTS))

import memory_git_targets as mgt


def _run_git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(repo),
        capture_output=True,
        text=True,
        encoding="utf-8",
        shell=False,
    )


def _init_repo(tmp_path: Path) -> Path:
    """Create a git repo with a tracked memory file and return repo root."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _run_git(repo, "init")
    _run_git(repo, "config", "user.email", "test@test.com")
    _run_git(repo, "config", "user.name", "Test")

    mem_dir = repo / ".serena" / "memories"
    mem_dir.mkdir(parents=True)
    target = mem_dir / "test-memory.md"
    target.write_text("original content", encoding="utf-8")
    _run_git(repo, "add", ".")
    _run_git(repo, "commit", "-m", "initial")
    return repo


def _head_sha(repo: Path) -> str:
    result = _run_git(repo, "rev-parse", "HEAD")
    return result.stdout.strip()


def _write_manifest(repo: Path, data: dict[str, object]) -> None:
    git_dir = mgt._git_dir(repo)
    manifest = git_dir / mgt.MANIFEST_NAME
    manifest.write_text(json.dumps(data), encoding="utf-8")


class TestCheckPositive:
    def test_valid_manifest(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        sha = _head_sha(repo)
        _write_manifest(repo, {
            "startingCommit": sha,
            "targets": [".serena/memories/test-memory.md"],
        })
        assert mgt.check(cwd=repo) == mgt.EXIT_OK


class TestPathTraversal:
    def test_dotdot_in_target(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        sha = _head_sha(repo)
        _write_manifest(repo, {
            "startingCommit": sha,
            "targets": [".serena/memories/../../etc/passwd"],
        })
        assert mgt.check(cwd=repo) == mgt.EXIT_LOGIC

    def test_memory_root_directory_rejected(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        _write_manifest(repo, {
            "startingCommit": _head_sha(repo),
            "targets": [".serena/memories"],
        })
        assert mgt.check(cwd=repo) == mgt.EXIT_LOGIC

    def test_wildcard_is_literal_not_a_pattern(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        _write_manifest(repo, {
            "startingCommit": _head_sha(repo),
            "targets": [".serena/memories/*.md"],
        })
        assert mgt.check(cwd=repo) == mgt.EXIT_LOGIC

    def test_dotdot_normalized(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        sha = _head_sha(repo)
        _write_manifest(repo, {
            "startingCommit": sha,
            "targets": [".serena/memories/topic/../../../secrets.md"],
        })
        assert mgt.check(cwd=repo) == mgt.EXIT_LOGIC

    def test_backslash_dotdot_rejected(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        _write_manifest(repo, {
            "startingCommit": _head_sha(repo),
            "targets": [".serena\\memories\\..\\..\\secrets.md"],
        })
        assert mgt.check(cwd=repo) == mgt.EXIT_LOGIC

    def test_non_traversal_backslash_rejected(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        _write_manifest(repo, {
            "startingCommit": _head_sha(repo),
            "targets": [".serena\\memories\\test-memory.md"],
        })
        assert mgt.check(cwd=repo) == mgt.EXIT_LOGIC


class TestAbsolutePath:
    def test_unix_absolute(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        sha = _head_sha(repo)
        _write_manifest(repo, {
            "startingCommit": sha,
            "targets": ["/etc/passwd"],
        })
        assert mgt.check(cwd=repo) == mgt.EXIT_LOGIC

    def test_windows_absolute(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        sha = _head_sha(repo)
        _write_manifest(repo, {
            "startingCommit": sha,
            "targets": ["C:\\Windows\\System32\\config"],
        })
        assert mgt.check(cwd=repo) == mgt.EXIT_LOGIC


class TestSymlinkEscape:
    def test_symlink_escapes_memories_root(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        sha = _head_sha(repo)

        # Create a symlink inside .serena/memories that points outside
        escape_target = tmp_path / "outside.md"
        escape_target.write_text("escaped", encoding="utf-8")
        link = repo / ".serena" / "memories" / "escape-link.md"
        try:
            link.symlink_to(escape_target)
        except OSError:
            pytest.skip("Cannot create symlinks on this platform")

        _write_manifest(repo, {
            "startingCommit": sha,
            "targets": [".serena/memories/escape-link.md"],
        })
        assert mgt.check(cwd=repo) == mgt.EXIT_LOGIC


class TestUntrackedTarget:
    def test_untracked_file_rejected(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        sha = _head_sha(repo)

        # Create an untracked file
        untracked = repo / ".serena" / "memories" / "untracked.md"
        untracked.write_text("not tracked", encoding="utf-8")

        _write_manifest(repo, {
            "startingCommit": sha,
            "targets": [".serena/memories/untracked.md"],
        })
        assert mgt.check(cwd=repo) == mgt.EXIT_LOGIC


class TestDuplicateTarget:
    def test_duplicate_entry_rejected(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        sha = _head_sha(repo)
        _write_manifest(repo, {
            "startingCommit": sha,
            "targets": [
                ".serena/memories/test-memory.md",
                ".serena/memories/test-memory.md",
            ],
        })
        assert mgt.check(cwd=repo) == mgt.EXIT_LOGIC


class TestMalformedManifest:
    def test_manifest_must_be_object(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        manifest = mgt._manifest_path(repo)
        manifest.write_text("[]", encoding="utf-8")
        assert mgt.check(cwd=repo) == mgt.EXIT_LOGIC

    def test_invalid_json(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        git_dir = mgt._git_dir(repo)
        manifest = git_dir / mgt.MANIFEST_NAME
        manifest.write_text("{not valid json", encoding="utf-8")
        assert mgt.check(cwd=repo) == mgt.EXIT_LOGIC

    def test_missing_manifest(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        assert mgt.check(cwd=repo) == mgt.EXIT_CONFIG

    def test_targets_not_a_list(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        sha = _head_sha(repo)
        _write_manifest(repo, {
            "startingCommit": sha,
            "targets": "not-a-list",
        })
        assert mgt.check(cwd=repo) == mgt.EXIT_LOGIC

    def test_empty_targets_rejected(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        _write_manifest(repo, {
            "startingCommit": _head_sha(repo),
            "targets": [],
        })
        assert mgt.check(cwd=repo) == mgt.EXIT_LOGIC

    def test_bad_commit_hash(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        _write_manifest(repo, {
            "startingCommit": "not-a-sha",
            "targets": [".serena/memories/test-memory.md"],
        })
        assert mgt.check(cwd=repo) == mgt.EXIT_LOGIC

    def test_nonexistent_canonical_sha_rejected(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        _write_manifest(repo, {
            "startingCommit": "0" * 40,
            "targets": [".serena/memories/test-memory.md"],
        })
        assert mgt.check(cwd=repo) == mgt.EXIT_LOGIC

    def test_target_not_string(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        sha = _head_sha(repo)
        _write_manifest(repo, {
            "startingCommit": sha,
            "targets": [123],
        })
        assert mgt.check(cwd=repo) == mgt.EXIT_LOGIC

    def test_not_under_memories(self, tmp_path: Path) -> None:
        """Target that is relative but not under .serena/memories."""
        repo = _init_repo(tmp_path)
        sha = _head_sha(repo)
        # Create and track a file outside memories
        other = repo / "README.md"
        other.write_text("readme", encoding="utf-8")
        _run_git(repo, "add", "README.md")
        _run_git(repo, "commit", "-m", "add readme")
        sha = _head_sha(repo)
        _write_manifest(repo, {
            "startingCommit": sha,
            "targets": ["README.md"],
        })
        assert mgt.check(cwd=repo) == mgt.EXIT_LOGIC


class TestRestore:
    def test_restore_uses_exact_starting_commit(self, tmp_path: Path) -> None:
        """Restore must use startingCommit, not HEAD."""
        repo = _init_repo(tmp_path)
        original_sha = _head_sha(repo)

        target_path = repo / ".serena" / "memories" / "test-memory.md"

        # Modify the file and commit (so HEAD differs from startingCommit)
        target_path.write_text("modified content", encoding="utf-8")
        _run_git(repo, "add", ".")
        _run_git(repo, "commit", "-m", "modify")

        # Manifest points to original commit
        _write_manifest(repo, {
            "startingCommit": original_sha,
            "targets": [".serena/memories/test-memory.md"],
        })

        result = mgt.restore(cwd=repo)
        assert result == mgt.EXIT_OK

        # File must contain original content, not the HEAD version
        restored = target_path.read_text(encoding="utf-8")
        assert restored == "original content"

    def test_restore_fails_on_invalid_manifest(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        _write_manifest(repo, {
            "startingCommit": "bad",
            "targets": [".serena/memories/test-memory.md"],
        })
        assert mgt.restore(cwd=repo) == mgt.EXIT_LOGIC

    def test_restore_uses_one_call_for_multiple_targets(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo = _init_repo(tmp_path)
        second = repo / ".serena" / "memories" / "second.md"
        second.write_text("second original", encoding="utf-8")
        _run_git(repo, "add", ".")
        _run_git(repo, "commit", "-m", "add second")
        starting_commit = _head_sha(repo)

        targets = [
            ".serena/memories/test-memory.md",
            ".serena/memories/second.md",
        ]
        for target in targets:
            (repo / target).write_text("changed", encoding="utf-8")
        _write_manifest(repo, {
            "startingCommit": starting_commit,
            "targets": targets,
        })

        real_run = subprocess.run
        restore_calls: list[list[str]] = []

        def spy_run(*args, **kwargs):
            command = args[0]
            if command[:3] == ["git", "--literal-pathspecs", "restore"]:
                restore_calls.append(command)
            return real_run(*args, **kwargs)

        monkeypatch.setattr(mgt.subprocess, "run", spy_run)
        assert mgt.restore(cwd=repo) == mgt.EXIT_OK
        assert restore_calls == [[
            "git",
            "--literal-pathspecs",
            "restore",
            f"--source={starting_commit}",
            "--worktree",
            "--",
            *targets,
        ]]
        assert (repo / targets[0]).read_text(encoding="utf-8") == "original content"
        assert (repo / targets[1]).read_text(encoding="utf-8") == "second original"


class TestCleanup:
    def test_cleanup_removes_manifest(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        sha = _head_sha(repo)
        _write_manifest(repo, {
            "startingCommit": sha,
            "targets": [".serena/memories/test-memory.md"],
        })
        manifest = mgt._manifest_path(repo)
        assert manifest.is_file()
        assert mgt.cleanup(cwd=repo) == mgt.EXIT_OK
        assert not manifest.is_file()

    def test_cleanup_idempotent(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        assert mgt.cleanup(cwd=repo) == mgt.EXIT_OK


class TestMain:
    def test_path_command_prints_fixed_manifest(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        repo = _init_repo(tmp_path)
        assert mgt.show_manifest_path(repo) == mgt.EXIT_OK
        assert capsys.readouterr().out.strip() == str(mgt._manifest_path(repo))

    def test_no_args(self) -> None:
        assert mgt.main([]) == mgt.EXIT_CONFIG

    def test_unknown_command(self) -> None:
        assert mgt.main(["bogus"]) == mgt.EXIT_CONFIG
