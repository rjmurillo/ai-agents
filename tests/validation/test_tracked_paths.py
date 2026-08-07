"""Tests for scripts/validation/tracked_paths.py and its use by drift checking.

Existence checks must be reproducible: the same commit must produce the same
result whether or not gitignored build output happens to be present. These
tests pin both directions, the symlink case, the loud-failure boundary, and
the integration point, so reverting the drift checker to a filesystem
existence test fails here.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.validation.check_skill_md_drift import marker_path_drift
from scripts.validation.check_skill_md_portability import (
    _strip_code,
    _strip_inline_code,
)
from scripts.validation.tracked_paths import (
    GitQueryError,
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
    tracked_paths.cache_clear()
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
        tracked_paths.cache_clear()

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
        tracked_paths.cache_clear()

        assert path_exists_in_repo(repo, "a") is True
        assert path_exists_in_repo(repo, "a/b") is True

    def test_staged_addition_counts_as_existing(self, tmp_path: Path) -> None:
        """Index semantics: the validator sees the tree the commit will have."""
        repo = _make_repo(tmp_path)
        (repo / "staged.md").write_text("s", encoding="utf-8")
        _git(repo, "add", "staged.md")
        tracked_paths.cache_clear()

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
        tracked_paths.cache_clear()

        assert path_exists_in_repo(repo, "alias/mod.py") is True
        assert path_exists_in_repo(repo, "alias/missing.py") is False

    def test_absolute_and_traversal_paths_are_rejected(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        assert path_exists_in_repo(repo, "/tracked.md") is False
        assert path_exists_in_repo(repo, "../tracked.md") is False

    def test_non_repository_falls_back_to_filesystem(self, tmp_path: Path) -> None:
        plain = tmp_path / "plain"
        plain.mkdir()
        (plain / "f.md").write_text("z", encoding="utf-8")
        tracked_paths.cache_clear()

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
        tracked_paths.cache_clear()

        with pytest.raises(GitQueryError):
            path_exists_in_repo(repo, "tracked.md")

        tracked_paths.cache_clear()


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

        tracked_paths.cache_clear()
        absent = _drift(repo, text)

        artifact = repo / "build" / "audit" / "other.md"
        artifact.parent.mkdir(parents=True)
        artifact.write_text("generated", encoding="utf-8")
        tracked_paths.cache_clear()
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
        tracked_paths.cache_clear()

        failures = _drift(repo, text)

        assert any("TYPOFILE.md" in f and "existence miss" in f for f in failures)

    def test_known_generated_artifact_is_exempt(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        text = (
            "<!-- vendor-portability: declared. References "
            "build/audit/GENERATION-AUDIT.md. -->\n"
            "The generator writes build/audit/GENERATION-AUDIT.md.\n"
        )
        tracked_paths.cache_clear()

        failures = _drift(repo, text)

        assert not any("existence miss" in f for f in failures)
