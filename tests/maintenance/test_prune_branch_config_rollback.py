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
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
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


_real_copy2 = shutil.copy2


def _copy_fails_for_live_config(src: Path, dst: Path) -> Path:
    """Copy the backup normally; fail only the copy back onto the live config."""
    if Path(dst).name == "config":
        raise OSError("disk full")
    return Path(_real_copy2(src, dst))


def _corrupt_live_config(repo: Path, error: str) -> mock.Mock:
    """Return a ``_verify_config`` stand-in that breaks the live config, then fails."""
    config = resolve_config_path(repo)

    def corrupt_then_fail(_repo: Path) -> None:
        with config.open("a", encoding="utf-8") as handle:
            handle.write("[broken\n")
        raise GitError(error)

    return mock.Mock(side_effect=corrupt_then_fail)


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
            mock.patch.object(mod, "_verify_config", _corrupt_live_config(repo, "boom")),
            mock.patch.object(mod.shutil, "copy2", side_effect=_copy_fails_for_live_config),
        ):
            with pytest.raises(GitError, match=r"rollback failed; the original config is saved at"):
                prune_branch_config(repo, apply=True)


class TestRollbackFallbackAndBooleans:
    def test_corrupt_live_config_is_repaired_from_the_backup(self, repo: Path) -> None:
        _add_section(repo, "gone")
        config = resolve_config_path(repo)
        original = config.read_bytes()

        def corrupt_then_verify(_repo: Path) -> None:
            with config.open("a", encoding="utf-8") as handle:
                handle.write("[broken\n")
            raise GitError("verify failed")

        with mock.patch.object(mod, "_verify_config", side_effect=corrupt_then_verify):
            with pytest.raises(GitError, match="verify failed"):
                prune_branch_config(repo, apply=True)

        assert config.read_bytes() == original
        assert _git(repo, "config", "--local", "--list")
        assert _sections(repo) == ("gone",)

    def test_section_restore_error_on_a_readable_config_keeps_the_live_file(
        self, repo: Path
    ) -> None:
        _add_section(repo, "gone")
        config = resolve_config_path(repo)

        def concurrent_then_fail(_repo: Path) -> None:
            _git(repo, "config", "--local", "user.name", "New Name")
            raise GitError("boom")

        with (
            mock.patch.object(mod, "_verify_config", side_effect=concurrent_then_fail),
            mock.patch.object(mod, "_restore_sections", side_effect=GitError("restore broke")),
        ):
            with pytest.raises(GitError) as info:
                prune_branch_config(repo, apply=True)

        assert _git(repo, "config", "--local", "user.name") == "New Name\n"
        assert "restore broke" in str(info.value)
        assert "config.before-prune" in str(info.value)
        assert list(config.parent.glob("config.before-prune*"))

    def test_section_restore_error_on_a_corrupt_config_copies_the_backup(self, repo: Path) -> None:
        _add_section(repo, "gone")
        config = resolve_config_path(repo)
        original = config.read_bytes()

        with (
            mock.patch.object(mod, "_verify_config", _corrupt_live_config(repo, "boom")),
            mock.patch.object(mod, "_restore_sections", side_effect=GitError("restore broke")),
        ):
            with pytest.raises(GitError, match="boom"):
                prune_branch_config(repo, apply=True)

        assert config.read_bytes() == original

    def test_failed_copy_names_both_errors_and_the_backup(self, repo: Path) -> None:
        _add_section(repo, "gone")

        with (
            mock.patch.object(mod, "_verify_config", _corrupt_live_config(repo, "boom")),
            mock.patch.object(mod, "_restore_sections", side_effect=GitError("restore broke")),
            mock.patch.object(mod.shutil, "copy2", side_effect=_copy_fails_for_live_config),
        ):
            with pytest.raises(GitError) as info:
                prune_branch_config(repo, apply=True)

        message = str(info.value)
        assert "restore broke" in message
        assert "disk full" in message
        assert "config.before-prune" in message

    def test_valueless_boolean_key_stays_true_after_rollback(self, repo: Path) -> None:
        _add_section(repo, "gone")
        with resolve_config_path(repo).open("a", encoding="utf-8") as handle:
            handle.write('[branch "gone"]\n\trebase\n')
        assert _git(repo, "config", "--local", "--get", "--bool", "branch.gone.rebase") == "true\n"

        with mock.patch.object(mod, "_verify_config", side_effect=GitError("boom")):
            with pytest.raises(GitError):
                prune_branch_config(repo, apply=True)

        assert _git(repo, "config", "--local", "--get", "--bool", "branch.gone.rebase") == "true\n"

    def test_explicit_empty_value_stays_empty_after_rollback(self, repo: Path) -> None:
        _add_section(repo, "gone")
        _git(repo, "config", "--local", "branch.gone.description", "")

        with mock.patch.object(mod, "_verify_config", side_effect=GitError("boom")):
            with pytest.raises(GitError):
                prune_branch_config(repo, apply=True)

        assert _git(repo, "config", "--local", "--get", "branch.gone.description") == "\n"

    def test_valueless_nonboolean_key_reads_the_same_after_rollback(self, repo: Path) -> None:
        _add_section(repo, "gone")
        with resolve_config_path(repo).open("a", encoding="utf-8") as handle:
            handle.write('[branch "gone"]\n\tdescription\n')
        before = _git(repo, "config", "--local", "--get", "branch.gone.description")

        with mock.patch.object(mod, "_verify_config", side_effect=GitError("boom")):
            with pytest.raises(GitError):
                prune_branch_config(repo, apply=True)

        assert before == "\n"
        assert _git(repo, "config", "--local", "--get", "branch.gone.description") == before


class TestRestoreSections:
    def test_skips_a_section_that_is_still_present(self, repo: Path) -> None:
        _add_section(repo, "kept")
        backup = repo / "backup-config"
        shutil.copy2(resolve_config_path(repo), backup)

        mod._restore_sections(repo, backup, ["kept"])

        assert _git(repo, "config", "--local", "--get-all", "branch.kept.remote") == "origin\n"

    def test_same_section_write_keeps_the_new_key_and_restores_the_old_ones(
        self, repo: Path
    ) -> None:
        _add_section(repo, "gone")
        backup = repo / "backup-config"
        shutil.copy2(resolve_config_path(repo), backup)
        _git(repo, "config", "--local", "--remove-section", "branch.gone")
        _git(repo, "config", "--local", "branch.gone.description", "updated")

        mod._restore_sections(repo, backup, ["gone"])

        assert _git(repo, "config", "--local", "--get-all", "branch.gone.remote") == "origin\n"
        assert _git(repo, "config", "--local", "--get-all", "branch.gone.merge") == (
            "refs/heads/gone\n"
        )
        assert _git(repo, "config", "--local", "--get-all", "branch.gone.description") == (
            "updated\n"
        )

    def test_partly_present_multivalued_key_is_not_duplicated(self, repo: Path) -> None:
        _add_section(repo, "gone")
        _git(repo, "config", "--local", "--add", "branch.gone.pushremote", "one")
        _git(repo, "config", "--local", "--add", "branch.gone.pushremote", "two")
        backup = repo / "backup-config"
        shutil.copy2(resolve_config_path(repo), backup)
        _git(repo, "config", "--local", "--unset", "branch.gone.pushremote", "two")

        mod._restore_sections(repo, backup, ["gone"])

        values = _git(repo, "config", "--local", "--get-all", "branch.gone.pushremote")
        assert sorted(values.split()) == ["one", "two"]

    def test_no_names_is_a_no_op(self, repo: Path) -> None:
        mod._restore_sections(repo, repo / "missing-backup", [])

    def test_unreadable_backup_raises(self, repo: Path) -> None:
        with pytest.raises(GitError):
            mod._restore_sections(repo, repo / "missing-backup", ["gone"])


class TestParseConfigEntries:
    def test_splits_key_and_value(self) -> None:
        assert mod._parse_config_entries("a.b\nv1\0c.d\nv2\0") == [("a.b", "v1"), ("c.d", "v2")]

    def test_valueless_key_is_none_not_empty(self) -> None:
        assert mod._parse_config_entries("a.b\0") == [("a.b", None)]

    def test_empty_value_stays_empty_string(self) -> None:
        assert mod._parse_config_entries("a.b\n\0") == [("a.b", "")]

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
