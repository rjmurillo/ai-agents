"""Rollback, lock, and last-moment re-listing for ``prune_branch_config --apply``.

Issue #6506. A failed or interrupted prune writes back only the sections it
removed, so a concurrent ``git config`` write survives. A lock file keeps two
``--apply`` runs apart, and the stale set is computed again under that lock.
Tests build real temporary repositories, so section parsing runs against git.
"""

from __future__ import annotations

import contextlib
import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path
from unittest import mock

import pytest

from scripts.maintenance import prune_branch_config as mod
from scripts.maintenance.prune_branch_config import (
    GitError,
    list_configured_branches,
    main,
    prune_branch_config,
    resolve_config_path,
)


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True)
    return result.stdout


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "t")
    _git(root, "config", "commit.gpgsign", "false")
    (root / "f.txt").write_text("x", encoding="utf-8")
    _git(root, "add", "f.txt")
    _git(root, "commit", "-q", "-m", "init")
    return root


def _add_section(repo: Path, name: str) -> None:
    _git(repo, "config", f"branch.{name}.remote", "origin")
    _git(repo, "config", f"branch.{name}.merge", f"refs/heads/{name}")


def _sections(repo: Path) -> tuple[str, ...]:
    return list_configured_branches(repo)


class TestRollbackAndLock:
    def test_interrupt_restores_removed_sections(self, repo: Path) -> None:
        _add_section(repo, "gone")
        _add_section(repo, "also-gone")
        config = resolve_config_path(repo)
        original = config.read_bytes()

        with mock.patch.object(mod, "_verify_config", side_effect=KeyboardInterrupt):
            with pytest.raises(KeyboardInterrupt):
                prune_branch_config(repo, apply=True)

        assert config.read_bytes() == original
        assert not config.with_name("config.prune-lock").exists()

    def test_removal_failure_midway_restores_only_touched_sections(self, repo: Path) -> None:
        _add_section(repo, "aaa")
        _add_section(repo, "zzz")
        real = mod._git_ok
        calls = {"remove": 0}

        def flaky(repo_arg: Path, *args: str) -> str:
            if "--remove-section" in args:
                calls["remove"] += 1
                if calls["remove"] == 2:
                    raise GitError("second removal failed")
            return real(repo_arg, *args)

        with mock.patch.object(mod, "_git_ok", side_effect=flaky):
            with pytest.raises(GitError, match="second removal failed"):
                prune_branch_config(repo, apply=True)

        assert _sections(repo) == ("aaa", "zzz")
        assert _git(repo, "config", "--local", "--get-all", "branch.aaa.remote") == "origin\n"

    def test_rollback_keeps_a_concurrent_write(self, repo: Path) -> None:
        _add_section(repo, "gone")

        def concurrent_then_fail(_repo: Path) -> None:
            _git(repo, "config", "--local", "teammate.setting", "kept")
            raise GitError("boom")

        with mock.patch.object(mod, "_verify_config", side_effect=concurrent_then_fail):
            with pytest.raises(GitError, match="boom"):
                prune_branch_config(repo, apply=True)

        assert _git(repo, "config", "--local", "teammate.setting") == "kept\n"
        assert _sections(repo) == ("gone",)

    def test_rollback_restores_dotted_slashed_and_multivalued_sections(self, repo: Path) -> None:
        _add_section(repo, "feature/a.b")
        _git(repo, "config", "--local", "--add", "branch.feature/a.b.pushremote", "one")
        _git(repo, "config", "--local", "--add", "branch.feature/a.b.pushremote", "two")
        original = resolve_config_path(repo).read_bytes()

        with mock.patch.object(mod, "_verify_config", side_effect=GitError("boom")):
            with pytest.raises(GitError):
                prune_branch_config(repo, apply=True)

        assert resolve_config_path(repo).read_bytes() == original

    def test_branch_created_after_first_look_is_kept(self, repo: Path) -> None:
        _add_section(repo, "late")
        _add_section(repo, "gone")
        real_lock = mod._prune_lock

        @contextlib.contextmanager
        def lock_then_create_branch(config_path: Path) -> Iterator[None]:
            with real_lock(config_path):
                _git(repo, "branch", "late")
                yield

        with mock.patch.object(mod, "_prune_lock", lock_then_create_branch):
            result = prune_branch_config(repo, apply=True)

        assert result.stale == ("gone",)
        assert _sections(repo) == ("late",)

    def test_held_lock_refuses_apply_and_leaves_config(self, repo: Path) -> None:
        _add_section(repo, "gone")
        config = resolve_config_path(repo)
        lock = config.with_name("config.prune-lock")
        lock.write_text("999\n", encoding="utf-8")
        original = config.read_bytes()

        with pytest.raises(GitError, match="another prune holds"):
            prune_branch_config(repo, apply=True)

        assert config.read_bytes() == original
        assert lock.exists()
        assert not list(config.parent.glob("config.before-prune*"))

    def test_dry_run_ignores_a_held_lock(self, repo: Path) -> None:
        _add_section(repo, "gone")
        resolve_config_path(repo).with_name("config.prune-lock").write_text("1\n", encoding="utf-8")

        result = prune_branch_config(repo)

        assert result.stale == ("gone",)

    def test_lock_is_released_after_success_and_after_nothing_stale(self, repo: Path) -> None:
        lock = resolve_config_path(repo).with_name("config.prune-lock")
        _add_section(repo, "gone")

        prune_branch_config(repo, apply=True)
        assert not lock.exists()

        prune_branch_config(repo, apply=True)
        assert not lock.exists()

    def test_unwritable_lock_location_raises(self, repo: Path) -> None:
        _add_section(repo, "gone")
        with mock.patch.object(mod.os, "open", side_effect=PermissionError("denied")):
            with pytest.raises(GitError, match="could not create prune lock"):
                prune_branch_config(repo, apply=True)

    def test_rollback_failure_names_the_backup(self, repo: Path) -> None:
        _add_section(repo, "gone")

        with (
            mock.patch.object(mod, "_verify_config", side_effect=GitError("boom")),
            mock.patch.object(mod, "_restore_sections", side_effect=GitError("no lock")),
        ):
            with pytest.raises(GitError, match=r"rollback failed; the original config is saved at"):
                prune_branch_config(repo, apply=True)


class TestRestoreSections:
    def test_skips_a_section_that_is_still_present(self, repo: Path) -> None:
        _add_section(repo, "kept")
        backup = repo / "backup-config"
        shutil.copy2(resolve_config_path(repo), backup)

        mod._restore_sections(repo, backup, ["kept"])

        assert _git(repo, "config", "--local", "--get-all", "branch.kept.remote") == "origin\n"

    def test_no_names_is_a_no_op(self, repo: Path) -> None:
        mod._restore_sections(repo, repo / "missing-backup", [])

    def test_unreadable_backup_raises(self, repo: Path) -> None:
        with pytest.raises(GitError):
            mod._restore_sections(repo, repo / "missing-backup", ["gone"])


class TestParseConfigEntries:
    def test_splits_key_and_value(self) -> None:
        assert mod._parse_config_entries("a.b\nv1\0c.d\nv2\0") == [("a.b", "v1"), ("c.d", "v2")]

    def test_valueless_key_gets_empty_value(self) -> None:
        assert mod._parse_config_entries("a.b\0") == [("a.b", "")]

    def test_value_may_contain_newline(self) -> None:
        assert mod._parse_config_entries("a.b\nline1\nline2\0") == [("a.b", "line1\nline2")]

    def test_empty_listing(self) -> None:
        assert mod._parse_config_entries("") == []


class TestMainLock:
    def test_main_held_lock_exits_3(self, repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
        _add_section(repo, "gone")
        resolve_config_path(repo).with_name("config.prune-lock").write_text("1\n", encoding="utf-8")

        code = main(["--path", str(repo), "--apply"])

        assert code == 3
        assert "another prune holds" in capsys.readouterr().err
