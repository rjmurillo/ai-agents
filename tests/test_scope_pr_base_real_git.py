"""Real-git tests for the stacked-base credibility rule.

Every other test in this area substitutes git with a mock, which is what let a
false invariant survive a full review and 88 passing tests. The original rule
required the stacked-base file set to be a subset of the main-relative one. That
claim is about the shape of a git graph, so a mock cannot refute it: the mock
returns whatever the test author already believes.

These tests build real repositories in ``tmp_path`` and run the real
``git merge-base``. The counterexample below took ten lines of shell to find and
is the reason the rule is now an ancestry test rather than a containment test.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.detect_scope_explosion import is_ancestor
from scripts.scope_pr_base import is_credible_rescope

pytestmark = pytest.mark.integration

FANOUT = 52
"""File count. Above the 50-file gate, so the block under test is a real one."""


def _git(repo: Path, *args: str) -> str:
    """Run git in ``repo`` and return stdout, raising on any nonzero exit."""
    done = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return done.stdout.strip()


def _commit(repo: Path, message: str) -> str:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


def _write_all(repo: Path, content: str, count: int = FANOUT) -> None:
    for i in range(count):
        (repo / f"f{i:02d}.txt").write_text(content, encoding="utf-8")


@pytest.fixture
def stacked_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A repository holding the counterexample that disproved containment.

    main     f00..f51 all contain "0"
    parent   every one of the 52 files changed to "1"
    child    f00.txt reverted to "0", nothing else touched

    The child is an honest one-file PR on top of the parent. It also agrees
    with main about f00.txt, so f00.txt cannot appear in the main-relative
    diff, and the containment rule rejected it.

    The fixture chdirs into the repository because the production
    ``is_ancestor`` shells out to ``git merge-base`` with no ``-C``, so it
    reads the current working directory. Without the chdir every commit here
    is an unknown ref, git exits 128, and ``is_ancestor`` returns False: the
    reject tests would then pass for the wrong reason.
    """
    repo = tmp_path / "stack"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "Test")
    _git(repo, "config", "commit.gpgsign", "false")

    _write_all(repo, "0")
    _commit(repo, "main: baseline")

    _git(repo, "checkout", "-q", "-b", "parent")
    _write_all(repo, "1")
    _commit(repo, "parent: change every file")

    _git(repo, "checkout", "-q", "-b", "child")
    (repo / "f00.txt").write_text("0", encoding="utf-8")
    _commit(repo, "child: revert one file")

    monkeypatch.chdir(repo)
    return repo


def _names(repo: Path, left: str, right: str) -> set[str]:
    out = _git(repo, "diff", "--name-only", left, right)
    return set(out.splitlines()) if out else set()


class TestContainmentIsFalseOnARealGraph:
    """The disproof, kept executable so nobody re-derives the old rule."""

    def test_the_stacked_file_is_absent_from_the_main_relative_set(
        self, stacked_repo: Path
    ) -> None:
        """The one file the child actually changed is invisible against main."""
        against_main = _names(stacked_repo, "main", "child")
        against_parent = _names(stacked_repo, "parent", "child")

        assert against_parent == {"f00.txt"}
        assert "f00.txt" not in against_main
        assert not against_parent.issubset(against_main)

    def test_the_block_is_real_and_the_rescope_is_small(self, stacked_repo: Path) -> None:
        """Confirms the case matters: 51 files blocks, 1 file does not."""
        assert len(_names(stacked_repo, "main", "child")) == FANOUT - 1
        assert len(_names(stacked_repo, "parent", "child")) == 1


class TestAncestryDiscriminatesOnARealGraph:
    """The replacement rule, exercised against the real merge-base."""

    @staticmethod
    def _result(repo: Path, base: str, count: int, files: tuple[str, ...]):
        from scripts.detect_scope_explosion import ScopeResult

        return ScopeResult(
            file_count=count,
            merge_base=_git(repo, "merge-base", "HEAD", base),
            current_branch="child",
            files=files,
        )

    def test_the_real_is_ancestor_can_see_this_repository(self, stacked_repo: Path) -> None:
        """Guards every reject test below against passing vacuously.

        ``is_ancestor`` returns False both when the answer is genuinely no and
        when git cannot resolve the refs at all. An earlier draft of this file
        did not chdir, so all three reject cases passed while the accept cases
        failed. This asserts the positive direction first.
        """
        main_fork = _git(stacked_repo, "merge-base", "HEAD", "main")
        stack_fork = _git(stacked_repo, "merge-base", "HEAD", "parent")

        assert main_fork != stack_fork
        assert is_ancestor(main_fork, stack_fork)
        assert not is_ancestor(stack_fork, main_fork)

    def test_accepts_the_case_containment_rejected(self, stacked_repo: Path) -> None:
        """A genuine stacked PR is credible even with a disjoint file set."""
        blocked = self._result(
            stacked_repo,
            "main",
            FANOUT - 1,
            tuple(sorted(_names(stacked_repo, "main", "child"))),
        )
        rescoped = self._result(stacked_repo, "parent", 1, ("f00.txt",))

        assert is_credible_rescope(rescoped, blocked, is_ancestor)

    def test_rejects_an_unrelated_branch(self, stacked_repo: Path) -> None:
        """A sibling off main shares main's fork point, so it is not a stack.

        This is the abuse the rule exists to stop: naming any small-diff branch
        as a base to walk a 51-file change past the gate.
        """
        _git(stacked_repo, "checkout", "-q", "main")
        _git(stacked_repo, "checkout", "-q", "-b", "unrelated")
        (stacked_repo / "elsewhere.txt").write_text("x", encoding="utf-8")
        _commit(stacked_repo, "unrelated: a sibling of main")
        _git(stacked_repo, "checkout", "-q", "child")

        blocked = self._result(stacked_repo, "main", FANOUT - 1, ("f01.txt",))
        rescoped = self._result(stacked_repo, "unrelated", 1, ("f00.txt",))

        assert not is_credible_rescope(rescoped, blocked, is_ancestor)

    def test_rejects_main_named_as_its_own_base(self, stacked_repo: Path) -> None:
        """Identical fork points are not strictly ordered, so this is refused."""
        blocked = self._result(stacked_repo, "main", FANOUT - 1, ("f01.txt",))
        rescoped = self._result(stacked_repo, "main", 1, ("f00.txt",))

        assert not is_credible_rescope(rescoped, blocked, is_ancestor)

    def test_accepts_a_parent_that_main_has_already_moved_past(self, stacked_repo: Path) -> None:
        """Advancing main must not invalidate a stack that is already open.

        The rejected alternative rule (main must be an ancestor of the base)
        fails here, because one commit on main puts main outside the parent's
        history while the stack itself is unchanged.
        """
        _git(stacked_repo, "checkout", "-q", "main")
        (stacked_repo / "moved-on.txt").write_text("x", encoding="utf-8")
        _commit(stacked_repo, "main: advance past the stack")
        _git(stacked_repo, "checkout", "-q", "child")

        assert not is_ancestor(
            _git(stacked_repo, "rev-parse", "main"),
            _git(stacked_repo, "rev-parse", "parent"),
        )

        blocked = self._result(stacked_repo, "main", FANOUT - 1, ("f01.txt",))
        rescoped = self._result(stacked_repo, "parent", 1, ("f00.txt",))

        assert is_credible_rescope(rescoped, blocked, is_ancestor)
