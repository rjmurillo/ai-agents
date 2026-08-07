"""Tests for scripts/validation/tracked_paths.py and its use by drift checking.

Existence checks must be reproducible: the same commit must produce the same
result whether or not gitignored build output happens to be present. These
tests pin both directions, the symlink case, the loud-failure boundary, and
the integration point, so reverting the drift checker to a filesystem
existence test fails here.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.validation.check_skill_md_drift import marker_path_drift
from scripts.validation.check_skill_md_portability import (
    _strip_code,
    _strip_inline_code,
)
from scripts.validation.tracked_paths import (
    GitQueryError,
    clear_tracked_path_cache,
    path_exists_in_repo,
    tracked_paths,
)


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
    )


def _make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@example.invalid")
    _git(repo, "config", "user.name", "t")
    (repo / "tracked.md").write_text("x", encoding="utf-8")
    (repo / ".gitignore").write_text("/build/audit/\n", encoding="utf-8")
    _git(repo, "add", "tracked.md", ".gitignore")
    _git(repo, "commit", "-qm", "seed")
    clear_tracked_path_cache()
    return repo


def _drift(repo: Path, text: str) -> list[str]:
    return marker_path_drift(
        text, repo, "SKILL.md", _strip_code, _strip_inline_code
    )


class TestPathExistsInRepo:
    def test_tracked_file_exists(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        assert path_exists_in_repo(repo, "tracked.md") is True

    def test_untracked_file_on_disk_does_not_exist(self, tmp_path: Path) -> None:
        """The defect: gitignored build output made a baseline unreproducible."""
        repo = _make_repo(tmp_path)
        artifact = repo / "build" / "audit" / "GENERATION-AUDIT.md"
        artifact.parent.mkdir(parents=True)
        artifact.write_text("generated", encoding="utf-8")
        clear_tracked_path_cache()

        assert artifact.exists() is True
        assert path_exists_in_repo(repo, "build/audit/GENERATION-AUDIT.md") is False

    def test_absent_path_does_not_exist(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        assert path_exists_in_repo(repo, "nope.md") is False

    def test_tracked_parent_directory_exists(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        nested = repo / "a" / "b" / "c.md"
        nested.parent.mkdir(parents=True)
        nested.write_text("y", encoding="utf-8")
        _git(repo, "add", "a/b/c.md")
        _git(repo, "commit", "-qm", "nested")
        clear_tracked_path_cache()

        assert path_exists_in_repo(repo, "a") is True
        assert path_exists_in_repo(repo, "a/b") is True

    def test_staged_addition_counts_as_existing(self, tmp_path: Path) -> None:
        """Index semantics: the validator sees the tree the commit will have."""
        repo = _make_repo(tmp_path)
        (repo / "staged.md").write_text("s", encoding="utf-8")
        _git(repo, "add", "staged.md")
        clear_tracked_path_cache()

        assert path_exists_in_repo(repo, "staged.md") is True

    def test_path_below_tracked_symlink_exists(self, tmp_path: Path) -> None:
        """This repo tracks a symlink; git lists the link, not what is under it."""
        repo = _make_repo(tmp_path)
        real = repo / "pkg" / "mod.py"
        real.parent.mkdir(parents=True)
        real.write_text("code", encoding="utf-8")
        (repo / "alias").symlink_to("pkg")
        _git(repo, "add", "pkg/mod.py", "alias")
        _git(repo, "commit", "-qm", "symlink")
        clear_tracked_path_cache()

        assert path_exists_in_repo(repo, "alias/mod.py") is True
        assert path_exists_in_repo(repo, "alias/missing.py") is False

    def test_untracked_symlink_does_not_make_paths_exist(self, tmp_path: Path) -> None:
        """A local link the repo does not track must not decide the answer."""
        repo = _make_repo(tmp_path)
        real = repo / "pkg" / "mod.py"
        real.parent.mkdir(parents=True)
        real.write_text("code", encoding="utf-8")
        _git(repo, "add", "pkg/mod.py")
        _git(repo, "commit", "-qm", "pkg")
        (repo / "local").symlink_to("pkg")
        clear_tracked_path_cache()

        assert (repo / "local" / "mod.py").exists() is True
        assert path_exists_in_repo(repo, "local/mod.py") is False

    def test_unstaged_edit_to_a_tracked_link_is_ignored(self, tmp_path: Path) -> None:
        """The index decides where a tracked link points, not the working tree."""
        repo = _make_repo(tmp_path)
        for pkg in ("pkg", "other"):
            target = repo / pkg / "mod.py"
            target.parent.mkdir(parents=True)
            target.write_text("code", encoding="utf-8")
        (repo / "alias").symlink_to("pkg")
        _git(repo, "add", "pkg/mod.py", "other/mod.py", "alias")
        _git(repo, "commit", "-qm", "links")

        (repo / "alias").unlink()
        (repo / "alias").symlink_to("nowhere")
        clear_tracked_path_cache()

        assert (repo / "alias" / "mod.py").exists() is False
        assert path_exists_in_repo(repo, "alias/mod.py") is True

    def test_parent_relative_tracked_link_stays_inside_repo(
        self, tmp_path: Path
    ) -> None:
        repo = _make_repo(tmp_path)
        target = repo / "shared" / "mod.py"
        target.parent.mkdir(parents=True)
        target.write_text("code", encoding="utf-8")
        link_dir = repo / "dir"
        link_dir.mkdir()
        (link_dir / "alias").symlink_to("../shared")
        _git(repo, "add", "shared/mod.py", "dir/alias")
        _git(repo, "commit", "-qm", "parent relative link")
        clear_tracked_path_cache()

        assert path_exists_in_repo(repo, "dir/alias/mod.py") is True

    def test_one_cache_clear_refreshes_paths_and_links(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        for package in ("old", "new"):
            target = repo / package / f"{package}.py"
            target.parent.mkdir(parents=True)
            target.write_text("code", encoding="utf-8")
        (repo / "alias").symlink_to("old")
        _git(repo, "add", "old/old.py", "new/new.py", "alias")
        _git(repo, "commit", "-qm", "old link")
        clear_tracked_path_cache()
        assert path_exists_in_repo(repo, "alias/old.py") is True

        (repo / "alias").unlink()
        (repo / "alias").symlink_to("new")
        _git(repo, "add", "alias")
        clear_tracked_path_cache()

        assert path_exists_in_repo(repo, "alias/old.py") is False
        assert path_exists_in_repo(repo, "alias/new.py") is True

    def test_symlink_cycle_terminates(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        (repo / "a").symlink_to("b")
        (repo / "b").symlink_to("a")
        _git(repo, "add", "a", "b")
        _git(repo, "commit", "-qm", "cycle")
        clear_tracked_path_cache()

        assert path_exists_in_repo(repo, "a/mod.py") is False

    def test_absolute_and_traversal_paths_are_rejected(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        assert path_exists_in_repo(repo, "/tracked.md") is False
        assert path_exists_in_repo(repo, "../tracked.md") is False

    def test_non_repository_falls_back_to_filesystem(self, tmp_path: Path) -> None:
        plain = tmp_path / "plain"
        plain.mkdir()
        (plain / "f.md").write_text("z", encoding="utf-8")
        clear_tracked_path_cache()

        assert tracked_paths(plain) is None
        assert path_exists_in_repo(plain, "f.md") is True
        assert path_exists_in_repo(plain, "missing.md") is False

    def test_operational_git_failure_raises(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A silent filesystem fallback would restore the machine-dependence."""
        repo = _make_repo(tmp_path)

        def _boom(*_args: object, **_kwargs: object) -> None:
            raise OSError("disk on fire")

        monkeypatch.setattr(subprocess, "run", _boom)
        clear_tracked_path_cache()

        with pytest.raises(GitQueryError):
            path_exists_in_repo(repo, "tracked.md")

        clear_tracked_path_cache()


class TestDriftUsesTrackedPaths:
    """Integration: reverting the drift checker to candidate.exists() fails here."""

    def test_gitignored_artifact_is_still_an_existence_miss(
        self, tmp_path: Path
    ) -> None:
        repo = _make_repo(tmp_path)
        text = (
            "<!-- vendor-portability: declared. References "
            "build/audit/other.md. -->\nSee build/audit/other.md for output.\n"
        )

        clear_tracked_path_cache()
        absent = _drift(repo, text)

        artifact = repo / "build" / "audit" / "other.md"
        artifact.parent.mkdir(parents=True)
        artifact.write_text("generated", encoding="utf-8")
        clear_tracked_path_cache()
        present = _drift(repo, text)

        assert present == absent
        assert any("existence miss" in f for f in present)

    def test_typo_under_generated_directory_is_reported(self, tmp_path: Path) -> None:
        """build/audit is not blanket-exempt: only the known artifact is."""
        repo = _make_repo(tmp_path)
        text = (
            "<!-- vendor-portability: declared. References "
            "build/audit/TYPOFILE.md. -->\nSee build/audit/TYPOFILE.md.\n"
        )
        clear_tracked_path_cache()

        failures = _drift(repo, text)

        assert any("TYPOFILE.md" in f and "existence miss" in f for f in failures)

    def test_known_generated_artifact_is_exempt(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        text = (
            "<!-- vendor-portability: declared. References "
            "build/audit/GENERATION-AUDIT.md. -->\n"
            "The generator writes build/audit/GENERATION-AUDIT.md.\n"
        )
        clear_tracked_path_cache()

        failures = _drift(repo, text)

        assert not any("existence miss" in f for f in failures)


class TestExternalFailureExitCode:
    """An operational git failure is external (exit 3), not config (exit 2)."""

    def test_executable_git_failure_exits_three(self, tmp_path: Path) -> None:
        """Exercise __main__; calling _run() alone would not pin the entry point."""
        fake_bin = tmp_path / "bin"
        fake_bin.mkdir()
        fake_git = fake_bin / "git"
        fake_git.write_text(
            f"#!{sys.executable}\n"
            "import sys\n"
            "print('git exploded', file=sys.stderr)\n"
            "sys.exit(7)\n",
            encoding="utf-8",
        )
        fake_git.chmod(0o755)
        repo_root = Path(__file__).resolve().parents[2]
        script = repo_root / "scripts" / "validation" / "check_skill_md_portability.py"
        env = os.environ | {"PATH": str(fake_bin)}

        completed = subprocess.run(
            [sys.executable, str(script)],
            cwd=repo_root,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

        assert completed.returncode == 3
        assert "External failure:" in completed.stderr
