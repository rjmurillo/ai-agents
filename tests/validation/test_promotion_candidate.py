"""The promotion gate refuses a candidate that is not where ADR-113 decision 5 puts it.

Issue #5636. Real git repositories in a temporary directory, because the check
is a read of git state and a stub would only restate the implementation.
"""

from __future__ import annotations

import subprocess
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from scripts.validation.promotion_gate import EXIT_CONFIG, EXIT_EXTERNAL, EXIT_OK, main
from tests.validation.promotion_gate_helpers import git, make_clone

TODAY = date(2026, 10, 1)


@pytest.fixture
def clone(tmp_path: Path) -> tuple[Path, str, str]:
    return make_clone(tmp_path)


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

    @pytest.mark.parametrize(
        "name", ["foo/", "foo//bar", "foo.lock", "foo/.hidden", "foo.", "a/b.lock/c", "a@{b"]
    )
    def test_names_git_would_refuse_are_bad_input_and_exit_two(
        self, clone: tuple[Path, str, str], name: str
    ) -> None:
        repo, first, _ = clone
        assert main(self._args(repo, first, f"--ancestor-of={name}")) == EXIT_CONFIG
        assert main(self._args(repo, first, f"--expect-tag={name}")) == EXIT_CONFIG

    def test_a_namespaced_ref_is_accepted_as_a_name(self, clone: tuple[Path, str, str]) -> None:
        repo, first, _ = clone
        git(repo, "branch", "release/2026.10", first)
        assert main(self._args(repo, first, "--ancestor-of=release/2026.10")) == EXIT_OK

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
