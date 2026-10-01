"""The promotion gate refuses a candidate that is not where ADR-113 decision 5 puts it.

Issue #5636. Real git repositories in a temporary directory, because the check
is a read of git state and a stub would only restate the implementation.
"""

from __future__ import annotations

import os
import subprocess
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from scripts.validation.promotion_gate import EXIT_CONFIG, EXIT_EXTERNAL, EXIT_OK, main

TODAY = date(2026, 10, 1)


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
        env={"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
             "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com",
             "PATH": os.environ["PATH"], "HOME": str(repo)},
    )  # fmt: skip
    return result.stdout.strip()


@pytest.fixture
def clone(tmp_path: Path) -> tuple[Path, str, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    (repo / "a").write_text("1", encoding="utf-8")
    _git(repo, "add", "a")
    _git(repo, "commit", "-q", "-m", "one")
    first = _git(repo, "rev-parse", "HEAD")
    _git(repo, "checkout", "-q", "-b", "side")
    (repo / "b").write_text("2", encoding="utf-8")
    _git(repo, "add", "b")
    _git(repo, "commit", "-q", "-m", "side")
    side = _git(repo, "rev-parse", "HEAD")
    _git(repo, "checkout", "-q", "main")
    _git(repo, "tag", "v1", first)
    return repo, first, side


class TestCandidatePlacement:
    def _args(self, repo: Path, sha: str, *extra: str) -> list[str]:
        ev = repo.parent / "ev"
        ev.mkdir(exist_ok=True)
        return [
            "--repo-root", str(repo), "--evidence-dir", str(ev), "--candidate-sha", sha,
            "--today", TODAY.isoformat(), *extra,
        ]  # fmt: skip

    def test_an_ancestor_of_main_is_accepted(self, clone: tuple[Path, str, str]) -> None:
        repo, first, _ = clone
        assert main(self._args(repo, first, "--ancestor-of", "main")) == EXIT_OK

    def test_a_commit_not_on_main_is_refused(self, clone: tuple[Path, str, str]) -> None:
        repo, _, side = clone
        assert main(self._args(repo, side, "--ancestor-of", "main")) == EXIT_CONFIG

    def test_a_tag_naming_the_candidate_is_accepted(self, clone: tuple[Path, str, str]) -> None:
        repo, first, _ = clone
        assert main(self._args(repo, first, "--expect-tag", "v1")) == EXIT_OK

    def test_a_tag_naming_another_commit_is_refused(self, clone: tuple[Path, str, str]) -> None:
        repo, _, side = clone
        assert main(self._args(repo, side, "--expect-tag", "v1")) == EXIT_CONFIG

    def test_a_missing_tag_is_refused(self, clone: tuple[Path, str, str]) -> None:
        repo, first, _ = clone
        assert main(self._args(repo, first, "--expect-tag", "v9")) == EXIT_CONFIG

    def test_a_flag_shaped_ref_is_bad_input_and_exits_two(
        self, clone: tuple[Path, str, str]
    ) -> None:
        repo, first, _ = clone
        assert main(self._args(repo, first, "--ancestor-of=--all")) == EXIT_CONFIG

    def test_a_flag_shaped_tag_is_bad_input_and_exits_two(
        self, clone: tuple[Path, str, str]
    ) -> None:
        repo, first, _ = clone
        assert main(self._args(repo, first, "--expect-tag=-v1")) == EXIT_CONFIG

    def test_an_unknown_ref_exits_three(self, clone: tuple[Path, str, str]) -> None:
        repo, first, _ = clone
        assert main(self._args(repo, first, "--ancestor-of", "nope")) == EXIT_EXTERNAL

    def test_a_non_repository_exits_three(self, tmp_path: Path) -> None:
        sha = "a" * 40
        args = ["--repo-root", str(tmp_path), "--evidence-dir", str(tmp_path),
                "--candidate-sha", sha, "--ancestor-of", "main"]  # fmt: skip
        assert main(args) == EXIT_EXTERNAL


class TestGitFailures:
    def test_git_that_cannot_run_exits_three(
        self, clone: tuple[Path, str, str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo, first, _ = clone

        def boom(*_a: Any, **_k: Any) -> None:
            raise subprocess.TimeoutExpired("git", 1)

        monkeypatch.setattr(subprocess, "run", boom)
        args = ["--repo-root", str(repo), "--evidence-dir", str(repo), "--candidate-sha", first,
                "--ancestor-of", "main"]  # fmt: skip
        assert main(args) == EXIT_EXTERNAL

    def test_rev_parse_failure_other_than_missing_exits_three(
        self, clone: tuple[Path, str, str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo, first, _ = clone

        def failing(*_a: Any, **_k: Any) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess([], 128, "", "fatal")

        monkeypatch.setattr(subprocess, "run", failing)
        args = ["--repo-root", str(repo), "--evidence-dir", str(repo), "--candidate-sha", first,
                "--expect-tag", "v1"]  # fmt: skip
        assert main(args) == EXIT_EXTERNAL
