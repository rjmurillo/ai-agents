"""Tests for prune_branch_config.

Issue #5360: deleted branches leave ``[branch "<name>"]`` sections behind in
the shared ``.git/config``. Tests build real temporary repositories so section
parsing, dotted and slashed names, packed refs, and linked worktrees run
against actual git, not a mock of it.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest import mock

import pytest

from scripts.maintenance import prune_branch_config as mod
from scripts.maintenance.prune_branch_config import (
    GitError,
    NotARepositoryError,
    branch_name_from_key,
    find_stale_branches,
    format_result,
    list_checked_out_branches,
    list_configured_branches,
    list_local_branches,
    main,
    prune_branch_config,
    resolve_config_path,
    run_git,
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


class TestBranchNameFromKey:
    @pytest.mark.parametrize(
        ("key", "expected"),
        [
            ("branch.feature.remote", "feature"),
            ("branch.feat/x.merge", "feat/x"),
            ("branch.release.1.2.remote", "release.1.2"),
            ("branch.a.b.c.d.vscode-merge-base", "a.b.c.d"),
            ("BRANCH.Mixed/Case.remote", "Mixed/Case"),
        ],
    )
    def test_extracts_subsection(self, key: str, expected: str) -> None:
        assert branch_name_from_key(key) == expected

    @pytest.mark.parametrize(
        "key",
        ["branch.autosetupmerge", "core.bare", "branch", "branch..remote", "branch.x."],
    )
    def test_returns_none_without_subsection(self, key: str) -> None:
        assert branch_name_from_key(key) is None


class TestFindStale:
    def test_keeps_local_and_checked_out(self) -> None:
        stale = find_stale_branches(["a", "b", "c", "d"], frozenset({"a"}), frozenset({"b"}))

        assert stale == ("c", "d")

    def test_empty_when_all_live(self) -> None:
        assert find_stale_branches(["a"], frozenset({"a"}), frozenset()) == ()


class TestPrune:
    def test_removes_only_orphan_sections(self, repo: Path) -> None:
        _git(repo, "branch", "live")
        _add_section(repo, "live")
        _add_section(repo, "gone")

        result = prune_branch_config(repo, apply=True)

        assert result.stale == ("gone",)
        assert result.removed == 1
        assert _sections(repo) == ("live",)
        assert result.backup_path is not None
        assert result.backup_path.exists()

    def test_dry_run_changes_nothing(self, repo: Path) -> None:
        _add_section(repo, "gone")
        config = resolve_config_path(repo)
        before = config.read_bytes()

        result = prune_branch_config(repo)

        assert result.stale == ("gone",)
        assert result.removed == 0
        assert result.backup_path is None
        assert config.read_bytes() == before
        assert not list(config.parent.glob("config.before-prune*"))

    def test_nothing_stale_writes_no_backup(self, repo: Path) -> None:
        _git(repo, "branch", "live")
        _add_section(repo, "live")

        result = prune_branch_config(repo, apply=True)

        assert result.stale == ()
        assert result.backup_path is None

    def test_no_branch_sections_at_all(self, repo: Path) -> None:
        result = prune_branch_config(repo, apply=True)

        assert result.configured == ()
        assert result.stale == ()

    def test_slashed_and_dotted_names(self, repo: Path) -> None:
        for name in ("feat/x", "release.1.2", "fix/a.b/c"):
            _git(repo, "branch", name)
            _add_section(repo, name)
        for name in ("old/y", "v2.0.1", "deep/er.x/z"):
            _add_section(repo, name)

        result = prune_branch_config(repo, apply=True)

        assert set(result.stale) == {"old/y", "v2.0.1", "deep/er.x/z"}
        assert _sections(repo) == ("feat/x", "fix/a.b/c", "release.1.2")

    def test_prefix_sibling_is_not_removed(self, repo: Path) -> None:
        _git(repo, "branch", "feat.x")
        _add_section(repo, "feat.x")
        _add_section(repo, "feat")

        prune_branch_config(repo, apply=True)

        assert _sections(repo) == ("feat.x",)

    def test_global_branch_settings_survive(self, repo: Path) -> None:
        _git(repo, "config", "branch.autoSetupMerge", "always")
        _add_section(repo, "gone")

        prune_branch_config(repo, apply=True)

        assert _git(repo, "config", "--local", "branch.autoSetupMerge").strip() == "always"

    def test_packed_ref_branch_is_kept(self, repo: Path) -> None:
        _git(repo, "branch", "packed")
        _add_section(repo, "packed")
        _git(repo, "pack-refs", "--all")

        result = prune_branch_config(repo, apply=True)

        assert result.stale == ()
        assert _sections(repo) == ("packed",)

    def test_unborn_head_branch_is_kept(self, tmp_path: Path) -> None:
        fresh = tmp_path / "fresh"
        fresh.mkdir()
        _git(fresh, "init", "-q", "-b", "trunk")
        _add_section(fresh, "trunk")
        _add_section(fresh, "gone")

        result = prune_branch_config(fresh, apply=True)

        assert result.stale == ("gone",)
        assert _sections(fresh) == ("trunk",)

    def test_linked_worktree_branch_is_kept(self, repo: Path, tmp_path: Path) -> None:
        worktree = tmp_path / "wt"
        _git(repo, "worktree", "add", "-q", str(worktree), "-b", "wt/live")
        _add_section(repo, "wt/live")
        _add_section(repo, "wt/gone")

        result = prune_branch_config(worktree, apply=True)

        assert result.stale == ("wt/gone",)
        assert _sections(repo) == ("wt/live",)
        assert resolve_config_path(worktree) == resolve_config_path(repo)

    def test_second_apply_is_idempotent(self, repo: Path) -> None:
        _add_section(repo, "gone")
        prune_branch_config(repo, apply=True)

        again = prune_branch_config(repo, apply=True)

        assert again.stale == ()

    def test_backup_names_do_not_collide(self, repo: Path) -> None:
        _add_section(repo, "gone1")
        first = prune_branch_config(repo, apply=True)
        _add_section(repo, "gone2")
        second = prune_branch_config(repo, apply=True)

        assert first.backup_path != second.backup_path
        assert second.backup_path is not None
        assert second.backup_path.name.endswith(".1")

    def test_backup_holds_original_content(self, repo: Path) -> None:
        _add_section(repo, "gone")
        original = resolve_config_path(repo).read_bytes()

        result = prune_branch_config(repo, apply=True)

        assert result.backup_path is not None
        assert result.backup_path.read_bytes() == original

    def test_verification_failure_restores_backup(self, repo: Path) -> None:
        _add_section(repo, "gone")
        config = resolve_config_path(repo)
        original = config.read_bytes()

        with mock.patch.object(mod, "_verify_config", side_effect=GitError("boom")):
            with pytest.raises(GitError, match="boom"):
                prune_branch_config(repo, apply=True)

        assert config.read_bytes() == original

    def test_backup_collision_exhaustion_raises(self, repo: Path) -> None:
        config = resolve_config_path(repo)
        with mock.patch.object(Path, "exists", return_value=True):
            with pytest.raises(GitError, match="backup path"):
                mod._backup_config(config)


class TestListers:
    def test_configured_empty_when_no_match(self, repo: Path) -> None:
        assert list_configured_branches(repo) == ()

    def test_configured_failure_raises(self, repo: Path) -> None:
        failed = subprocess.CompletedProcess([], 128, "", "bad")
        with mock.patch.object(mod, "run_git", return_value=failed):
            with pytest.raises(GitError, match="get-regexp"):
                list_configured_branches(repo)

    def test_local_branches(self, repo: Path) -> None:
        _git(repo, "branch", "a/b")

        assert list_local_branches(repo) == frozenset({"main", "a/b"})

    def test_checked_out_includes_head(self, repo: Path) -> None:
        assert list_checked_out_branches(repo) == frozenset({"main"})

    def test_detached_head_adds_nothing(self, repo: Path) -> None:
        _git(repo, "checkout", "-q", "--detach")

        assert list_checked_out_branches(repo) == frozenset()

    def test_git_failure_raises(self, repo: Path) -> None:
        failed = subprocess.CompletedProcess([], 128, "", "fatal: nope")
        with mock.patch.object(mod, "run_git", return_value=failed):
            with pytest.raises(GitError, match="nope"):
                list_local_branches(repo)

    def test_git_failure_without_stderr_uses_stdout(self, repo: Path) -> None:
        failed = subprocess.CompletedProcess([], 1, "stdout msg", "")
        with mock.patch.object(mod, "run_git", return_value=failed):
            with pytest.raises(GitError, match="stdout msg"):
                list_local_branches(repo)


class TestRunGit:
    def test_timeout_becomes_git_error(self, repo: Path) -> None:
        err = subprocess.TimeoutExpired(cmd="git", timeout=1)
        with mock.patch.object(subprocess, "run", side_effect=err):
            with pytest.raises(GitError, match="failed"):
                run_git(repo, "status")

    def test_missing_binary_becomes_git_error(self, repo: Path) -> None:
        with mock.patch.object(subprocess, "run", side_effect=FileNotFoundError("git")):
            with pytest.raises(GitError):
                run_git(repo, "status")

    def test_git_env_is_stripped(self, repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GIT_DIR", "/nonexistent")

        assert run_git(repo, "rev-parse", "--git-dir").returncode == 0


class TestResolveConfigPath:
    def test_plain_repo(self, repo: Path) -> None:
        assert resolve_config_path(repo) == (repo / ".git" / "config").resolve()

    def test_relative_common_dir_resolves_against_repo(self, repo: Path) -> None:
        assert resolve_config_path(repo).is_absolute()

    def test_missing_directory(self, tmp_path: Path) -> None:
        with pytest.raises(NotARepositoryError):
            resolve_config_path(tmp_path / "absent")

    def test_non_repository(self, tmp_path: Path) -> None:
        plain = tmp_path / "plain"
        plain.mkdir()
        with mock.patch.dict("os.environ", {"GIT_CEILING_DIRECTORIES": str(tmp_path)}):
            with pytest.raises(NotARepositoryError):
                resolve_config_path(plain)


class TestFormatAndMain:
    def test_dry_run_hint(self, repo: Path) -> None:
        _add_section(repo, "gone")

        text = format_result(prune_branch_config(repo), apply=False)

        assert "stale: gone" in text
        assert "pass --apply" in text

    def test_clean_report_has_no_hint(self, repo: Path) -> None:
        text = format_result(prune_branch_config(repo), apply=False)

        assert "stale: 0" in text
        assert "--apply" not in text

    def test_main_dry_run(self, repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
        _add_section(repo, "gone")

        assert main(["--path", str(repo)]) == 0
        assert "stale: gone" in capsys.readouterr().out
        assert _sections(repo) == ("gone",)

    def test_main_apply(self, repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
        _add_section(repo, "gone")

        assert main(["--path", str(repo), "--apply"]) == 0
        assert "removed 1 section(s)" in capsys.readouterr().out
        assert _sections(repo) == ()

    def test_main_not_a_repo_exits_2(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main(["--path", str(tmp_path / "absent")]) == 2
        assert "ERROR" in capsys.readouterr().err

    def test_main_git_failure_exits_3(self, repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
        with mock.patch.object(mod, "prune_branch_config", side_effect=GitError("x")):
            assert main(["--path", str(repo)]) == 3
        assert "prune failed" in capsys.readouterr().err


class TestCommandLine:
    def test_script_runs_as_entry_point(self, repo: Path) -> None:
        _add_section(repo, "gone")
        script = Path(mod.__file__).resolve()

        result = subprocess.run(
            ["python3", str(script), "--path", str(repo)],
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 0
        assert "stale: gone" in result.stdout
