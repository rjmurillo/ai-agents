"""The reachability probes are asked once per repository, not once per commit.

Issue #5382. ``commit_reachability_problem`` asked git two questions that do not
depend on the SHA it was given: is this a work tree, and is the clone shallow.
Validating the committed session-log corpus called it 878 times, so those two
invariant answers cost 1756 of the 2735 git processes that one test started.

Coverage:
* Positive: repeated calls for one repository run the invariant pair once.
* Negative control: clearing the cache makes the pair run again, which is what
  fails if the memo is removed or the seam stops working.
* Edge: a second repository root gets its own probe pair, no cross-repo bleed.
* Edge: a directory that is no work tree caches its answer too, and the
  reachability verdict stays silent.
* Failure path: a probe that raises records nothing, so a momentarily
  unavailable git cannot pin its own absence for the rest of the process.
* Real git: the verdicts for a reachable and an unreachable SHA are unchanged
  across repeated calls.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.validation import session_scope

_INVARIANT_PROBES = (
    ["rev-parse", "--is-inside-work-tree"],
    ["rev-parse", "--is-shallow-repository"],
)


@pytest.fixture(autouse=True)
def _clean_cache() -> object:
    """Never inherit or leak a memo across tests in this module."""
    session_scope._adjudication_cache_clear()
    yield
    session_scope._adjudication_cache_clear()


def _recording_git(
    monkeypatch: pytest.MonkeyPatch, *, returncode: int = 0, stdout: str = "false\n"
) -> list[list[str]]:
    calls: list[list[str]] = []

    def fake(args: list[str], repo_root: Path, **_kwargs: object):
        calls.append(list(args))
        return subprocess.CompletedProcess(["git", *args], returncode, stdout, "")

    monkeypatch.setattr(session_scope, "_git", fake)
    return calls


def _invariant_calls(calls: list[list[str]]) -> list[list[str]]:
    return [c for c in calls if c in [list(p) for p in _INVARIANT_PROBES]]


class TestTheInvariantPairIsAskedOnce:
    def test_three_commits_share_one_probe_pair(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        calls = _recording_git(monkeypatch)
        for sha in ("a" * 40, "b" * 40, "c" * 40):
            session_scope.commit_reachability_problem(sha, tmp_path)
        assert len(_invariant_calls(calls)) == 2, _invariant_calls(calls)

    def test_clearing_the_cache_asks_again(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Negative control: without the memo this is what every call did."""
        calls = _recording_git(monkeypatch)
        session_scope.commit_reachability_problem("a" * 40, tmp_path)
        session_scope._adjudication_cache_clear()
        session_scope.commit_reachability_problem("b" * 40, tmp_path)
        assert len(_invariant_calls(calls)) == 4, _invariant_calls(calls)

    def test_a_second_repository_gets_its_own_pair(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Edge: the memo is keyed per repository, so it cannot answer for another."""
        first = tmp_path / "one"
        second = tmp_path / "two"
        first.mkdir()
        second.mkdir()
        calls = _recording_git(monkeypatch)
        session_scope.commit_reachability_problem("a" * 40, first)
        session_scope.commit_reachability_problem("a" * 40, second)
        assert len(_invariant_calls(calls)) == 4, _invariant_calls(calls)

    def test_a_non_work_tree_answer_is_cached_and_stays_silent(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Edge: the negative answer is invariant too, so it is asked once."""
        calls = _recording_git(monkeypatch, returncode=1, stdout="")
        assert session_scope.commit_reachability_problem("a" * 40, tmp_path) is None
        assert session_scope.commit_reachability_problem("b" * 40, tmp_path) is None
        assert _invariant_calls(calls) == [["rev-parse", "--is-inside-work-tree"]]

    def test_a_shallow_clone_answer_is_cached_and_stays_silent(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        calls = _recording_git(monkeypatch, stdout="true\n")
        assert session_scope.commit_reachability_problem("a" * 40, tmp_path) is None
        assert session_scope.commit_reachability_problem("b" * 40, tmp_path) is None
        assert len(_invariant_calls(calls)) == 2, _invariant_calls(calls)


class TestAFailedProbeIsNotMemoized:
    def test_a_raising_probe_records_nothing(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Git being briefly unavailable must not pin its absence for the process."""

        def boom(args: list[str], repo_root: Path, **_kwargs: object):
            raise OSError("git is not on PATH")

        monkeypatch.setattr(session_scope, "_git", boom)
        assert session_scope.commit_reachability_problem("a" * 40, tmp_path) is None
        assert session_scope._ADJUDICABLE_CACHE == {}

    def test_the_next_call_after_a_failure_asks_git_again(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        state = {"fail": True}

        def flaky(args: list[str], repo_root: Path, **_kwargs: object):
            if state["fail"]:
                raise subprocess.SubprocessError("timed out")
            return subprocess.CompletedProcess(["git", *args], 0, "false\n", "")

        monkeypatch.setattr(session_scope, "_git", flaky)
        assert session_scope.commit_reachability_problem("a" * 40, tmp_path) is None
        state["fail"] = False
        assert session_scope.commit_reachability_problem("a" * 40, tmp_path) is None
        assert session_scope._ADJUDICABLE_CACHE


class TestRealGitVerdictsAreUnchanged:
    """The memo must save processes without changing a single answer."""

    @staticmethod
    def _repo(tmp_path: Path) -> tuple[Path, str, str]:
        repo = tmp_path / "repo"
        repo.mkdir()

        def git(*args: str) -> str:
            return subprocess.run(
                ["git", *args],
                cwd=repo,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=True,
            ).stdout.strip()

        git("init", "-q", "-b", "main")
        git("config", "user.email", "t@example.com")
        git("config", "user.name", "T")
        (repo / "a.txt").write_text("a", encoding="utf-8")
        git("add", "a.txt")
        git("commit", "-qm", "a")
        reachable = git("rev-parse", "HEAD")
        git("checkout", "-qb", "side")
        (repo / "b.txt").write_text("b", encoding="utf-8")
        git("add", "b.txt")
        git("commit", "-qm", "b")
        offbranch = git("rev-parse", "HEAD")
        git("checkout", "-q", "main")
        return repo, reachable, offbranch

    def test_repeated_calls_keep_reporting_the_same_verdicts(
        self, tmp_path: Path
    ) -> None:
        repo, reachable, offbranch = self._repo(tmp_path)
        for _ in range(3):
            assert session_scope.commit_reachability_problem(reachable, repo) is None
            assert (
                session_scope.commit_reachability_problem("0" * 40, repo)
                == session_scope.NO_SUCH_COMMIT
            )
            assert (
                session_scope.commit_reachability_problem(offbranch, repo)
                == session_scope.NOT_AN_ANCESTOR
            )

    def test_a_non_sha_never_reaches_git_or_the_cache(self, tmp_path: Path) -> None:
        """The argument guard still short-circuits ahead of any probe (CWE-88)."""
        assert (
            session_scope.commit_reachability_problem("--upload-pack=touch", tmp_path)
            == session_scope.NOT_A_COMMIT_SHA
        )
        assert session_scope._ADJUDICABLE_CACHE == {}
