"""Tests for scripts/validation/tracked_paths.py.

Existence checks must be reproducible: the same commit must produce the same
result whether or not gitignored build output happens to be present. These
tests pin both directions, plus the fallback when git cannot answer.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from scripts.validation.tracked_paths import path_exists_in_repo, tracked_paths


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
    return repo


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

    def test_non_repository_falls_back_to_filesystem(self, tmp_path: Path) -> None:
        plain = tmp_path / "plain"
        plain.mkdir()
        (plain / "f.md").write_text("z", encoding="utf-8")
        tracked_paths.cache_clear()

        assert tracked_paths(plain) is None
        assert path_exists_in_repo(plain, "f.md") is True
        assert path_exists_in_repo(plain, "missing.md") is False
