"""Tests for the batched symlink-target read in tracked_paths (issue #6734).

The snapshot used to start one ``git cat-file blob`` process per tracked
symlink. It now starts one ``git cat-file --batch`` for all of them. These tests
pin the process count and that every link still resolves to the same target.
"""

from __future__ import annotations

import subprocess
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from scripts.validation import tracked_paths as tp
from scripts.validation.tracked_paths import (
    GitQueryError,
    clear_tracked_path_cache,
    path_exists_in_repo,
)


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def _repo_with_links(tmp_path: Path, count: int) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@example.invalid")
    _git(repo, "config", "user.name", "t")
    (repo / "seed.md").write_text("seed", encoding="utf-8")
    for index in range(count):
        target = repo / f"real{index}" / "mod.py"
        target.parent.mkdir(parents=True)
        target.write_text(f"code {index}", encoding="utf-8")
        (repo / f"link{index}").symlink_to(f"real{index}")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "links")
    clear_tracked_path_cache()
    return repo


@pytest.fixture(autouse=True)
def _clean_cache() -> Iterator[None]:
    clear_tracked_path_cache()
    yield
    clear_tracked_path_cache()


def _count_git_calls(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    calls: list[list[str]] = []
    real = tp._run_git_bytes

    def spy(repo_root: Path, args: list[str], stdin: bytes | None = None) -> bytes | None:
        calls.append(args)
        return real(repo_root, args, stdin)

    monkeypatch.setattr(tp, "_run_git_bytes", spy)
    return calls


class TestBatchedRead:
    def test_many_links_cost_one_cat_file_process(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo = _repo_with_links(tmp_path, 25)
        calls = _count_git_calls(monkeypatch)

        assert path_exists_in_repo(repo, "link24/mod.py") is True

        cat_file = [cmd for cmd in calls if "cat-file" in cmd]
        assert len(cat_file) == 1
        assert "--batch" in cat_file[0]
        assert len(calls) == 2, "one ls-files plus one cat-file, however many links"

    def test_every_link_resolves_and_a_miss_stays_a_miss(self, tmp_path: Path) -> None:
        repo = _repo_with_links(tmp_path, 12)

        for index in range(12):
            assert path_exists_in_repo(repo, f"link{index}/mod.py") is True
            assert path_exists_in_repo(repo, f"link{index}/absent.py") is False

    def test_links_to_one_target_share_a_blob(self, tmp_path: Path) -> None:
        """Two links with the same target text are one blob; both still resolve."""
        repo = _repo_with_links(tmp_path, 1)
        (repo / "second").symlink_to("real0")
        _git(repo, "add", "second")
        _git(repo, "commit", "-qm", "second link")
        clear_tracked_path_cache()

        assert path_exists_in_repo(repo, "link0/mod.py") is True
        assert path_exists_in_repo(repo, "second/mod.py") is True

    def test_non_ascii_target_is_decoded(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        _git(repo, "init", "-q")
        _git(repo, "config", "user.email", "t@example.invalid")
        _git(repo, "config", "user.name", "t")
        real = repo / "réel" / "mod.py"
        real.parent.mkdir()
        real.write_text("x", encoding="utf-8")
        (repo / "alias").symlink_to("réel")
        _git(repo, "add", ".")
        _git(repo, "commit", "-qm", "unicode")
        clear_tracked_path_cache()

        assert path_exists_in_repo(repo, "alias/mod.py") is True

    def test_link_whose_index_entry_is_an_annotated_tag_still_resolves(
        self, tmp_path: Path
    ) -> None:
        """``git cat-file blob <tag>`` peels the tag; the batch must too.

        Git accepts a mode 120000 index entry whose object is an annotated tag
        of the target blob. A batch that asked for the bare sha would receive
        the tag object, reject it, and turn a normal verdict into a gate error.
        """
        repo = _repo_with_links(tmp_path, 1)
        blob = (
            subprocess.run(
                ["git", "-C", str(repo), "hash-object", "-w", "--stdin"],
                input=b"real0",
                check=True,
                capture_output=True,
            )
            .stdout.decode("ascii")
            .strip()
        )
        _git(repo, "tag", "-a", "-m", "tagged target", "target-tag", blob)
        tag = (
            subprocess.run(
                ["git", "-C", str(repo), "rev-parse", "target-tag"],
                check=True,
                capture_output=True,
            )
            .stdout.decode("ascii")
            .strip()
        )
        assert tag != blob
        _git(repo, "update-index", "--add", "--cacheinfo", f"120000,{tag},tagged")
        clear_tracked_path_cache()

        assert path_exists_in_repo(repo, "tagged/mod.py") is True
        assert path_exists_in_repo(repo, "tagged/absent.py") is False

    def test_repository_without_links_runs_no_cat_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo = _repo_with_links(tmp_path, 0)
        (repo / "f.md").write_text("x", encoding="utf-8")
        _git(repo, "add", "f.md")
        _git(repo, "commit", "-qm", "f")
        clear_tracked_path_cache()
        calls = _count_git_calls(monkeypatch)

        assert path_exists_in_repo(repo, "f.md") is True
        assert not [cmd for cmd in calls if "cat-file" in cmd]


class TestBatchFailuresStayLoud:
    def test_missing_object_raises(self, tmp_path: Path) -> None:
        repo = _repo_with_links(tmp_path, 1)

        with pytest.raises(GitQueryError, match="unexpected reply"):
            tp._read_link_targets(repo, {"link0": "0" * 40})

    def test_non_blob_object_raises(self, tmp_path: Path) -> None:
        repo = _repo_with_links(tmp_path, 1)
        tree = (
            subprocess.run(
                ["git", "-C", str(repo), "rev-parse", "HEAD^{tree}"],
                check=True,
                capture_output=True,
            )
            .stdout.decode("ascii")
            .strip()
        )

        with pytest.raises(GitQueryError, match="unexpected reply"):
            tp._read_link_targets(repo, {"link0": tree})

    def test_truncated_output_raises(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        repo = _repo_with_links(tmp_path, 1)
        sha = "a" * 40
        monkeypatch.setattr(
            tp, "_run_git_bytes", lambda *_a, **_k: f"{sha} blob 99\nshort".encode()
        )

        with pytest.raises(GitQueryError, match="truncated blob"):
            tp._read_link_targets(repo, {"link0": sha})

    def test_empty_output_raises(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        repo = _repo_with_links(tmp_path, 1)
        monkeypatch.setattr(tp, "_run_git_bytes", lambda *_a, **_k: b"")

        with pytest.raises(GitQueryError, match="truncated output"):
            tp._read_link_targets(repo, {"link0": "a" * 40})

    def test_operational_failure_still_raises(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo = _repo_with_links(tmp_path, 2)
        real = subprocess.run

        def fail_batch(cmd: list[str], *_args: Any, **kwargs: Any) -> Any:
            if "--batch" in cmd:
                raise OSError("pipe broke")
            return real(cmd, input=kwargs.get("input"), capture_output=True, check=False)

        monkeypatch.setattr(tp.subprocess, "run", fail_batch)

        with pytest.raises(GitQueryError):
            path_exists_in_repo(repo, "link0/mod.py")
