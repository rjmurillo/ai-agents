"""Tests for is_credible_rescope in scripts/scope_pr_base.py.

Separated from test_scope_pr_base.py because credibility is a different
subject from the gh lookup that feeds it. The lookup asks what a pull request
says its base is; this asks whether the branch actually left main first and
left that base second, which is what "stacked" means.

These tests stub the ancestry oracle so they can drive every branch cheaply.
The claim that the oracle itself behaves this way against real commits is
proved in test_scope_pr_base_real_git.py, which builds repositories and runs
git. A mocked ancestry test cannot establish a fact about a real commit graph;
see .claude/rules/testing.md item 13.
"""

from __future__ import annotations

from pathlib import Path

from scripts.detect_scope_explosion import ScopeResult
from scripts.scope_pr_base import is_credible_rescope


class TestIsCredibleRescope:
    """Tests for is_credible_rescope.

    The credibility test is a graph property, not a diff property. It asks
    whether this branch left main first and left the PR base second, which is
    what "stacked" means. An earlier version tested path-set containment and
    was wrong; see test_accepts_a_stacked_base_whose_files_main_never_saw.
    """

    MAIN_FORK = "aaaa111"
    STACK_FORK = "bbbb222"

    @classmethod
    def _blocked(cls, *files: str) -> ScopeResult:
        return ScopeResult(
            file_count=len(files),
            merge_base=cls.MAIN_FORK,
            current_branch="feat/stacked",
            files=files,
        )

    @classmethod
    def _rescoped(cls, *files: str, merge_base: str | None = None) -> ScopeResult:
        return ScopeResult(
            file_count=len(files),
            merge_base=cls.STACK_FORK if merge_base is None else merge_base,
            current_branch="feat/stacked",
            files=files,
        )

    @staticmethod
    def _ancestry(result: bool):
        """Return an is_ancestor stub plus a record of how it was called."""
        calls: list[tuple[str, str]] = []

        def is_ancestor(commit: str, ref: str) -> bool:
            calls.append((commit, ref))
            return result

        return is_ancestor, calls

    def test_rejects_none(self) -> None:
        """An unresolvable re-measurement is not credible."""
        ancestor, calls = self._ancestry(True)
        assert is_credible_rescope(None, self._blocked("a.py"), ancestor) is False
        assert calls == []

    def test_rejects_a_different_branch(self) -> None:
        """A rescope measured on another branch cannot clear this one.

        Both calls re-read HEAD, so a checkout landing between them can
        substitute a branch stacked on the same parent. Its file count is
        small and its ancestry checks out, so every other condition passes.
        """
        ancestor, calls = self._ancestry(True)
        other = ScopeResult(
            file_count=1,
            merge_base=self.STACK_FORK,
            current_branch="feat/someone-else",
            files=("x.py",),
        )
        assert is_credible_rescope(other, self._blocked("a.py"), ancestor) is False
        assert calls == []

    def test_accepts_the_same_branch(self) -> None:
        """The guard rejects on branch identity alone, not on any other field."""
        ancestor, _ = self._ancestry(True)
        blocked = self._blocked("a.py")
        same = self._rescoped("x.py")
        assert same.current_branch == blocked.current_branch
        assert is_credible_rescope(same, blocked, ancestor) is True

    def test_branch_comparison_is_exact(self) -> None:
        """A name that merely shares a prefix is a different branch."""
        ancestor, calls = self._ancestry(True)
        near_miss = ScopeResult(
            file_count=1,
            merge_base=self.STACK_FORK,
            current_branch=self._blocked("a.py").current_branch + "-2",
            files=("x.py",),
        )
        assert is_credible_rescope(near_miss, self._blocked("a.py"), ancestor) is False
        assert calls == []

    def test_rejects_zero_files(self) -> None:
        """A zero-file remeasurement must not clear the original block.

        Diff failures now raise ScopeDetectionError and are caught before
        credibility is checked. A zero-file result therefore means a real
        empty diff, which still is not a branch this gate needs to unblock.
        """
        ancestor, calls = self._ancestry(True)
        assert is_credible_rescope(self._rescoped(), self._blocked("a.py"), ancestor) is False
        assert calls == []

    def test_accepts_a_stacked_base_whose_files_main_never_saw(self) -> None:
        """The regression the subset invariant caused.

        Verified against a constructed repository: main holds 52 files, the
        parent changes all 52, and the child reverts one to main's content.
        The child changes 51 files against main and exactly 1 against its
        parent, and that 1 file is absent from the main-relative set because
        the child agrees with main about it. The old containment test rejected
        this honest one-file stacked PR and left it blocked at 51.
        """
        blocked = self._blocked(*[f"f{i:02d}.txt" for i in range(1, 52)])
        rescoped = self._rescoped("f00.txt")
        ancestor, calls = self._ancestry(True)
        assert is_credible_rescope(rescoped, blocked, ancestor) is True
        assert calls == [(self.MAIN_FORK, self.STACK_FORK)]

    def test_rejects_an_identical_fork_point(self) -> None:
        """A base that forks where main forks is not a stack.

        An unrelated branch shares main's fork point exactly. Requiring a
        strict ancestor rejects it without consulting git at all.
        """
        ancestor, calls = self._ancestry(True)
        rescoped = self._rescoped("b.py", merge_base=self.MAIN_FORK)
        assert is_credible_rescope(rescoped, self._blocked("a.py", "b.py"), ancestor) is False
        assert calls == []

    def test_rejects_a_fork_point_that_is_not_downstream(self) -> None:
        """A base whose fork point does not descend from main's is incomparable."""
        ancestor, calls = self._ancestry(False)
        rescoped = self._rescoped("b.py")
        assert is_credible_rescope(rescoped, self._blocked("a.py", "b.py"), ancestor) is False
        assert calls == [(self.MAIN_FORK, self.STACK_FORK)]

    def test_rejects_a_missing_merge_base_on_either_side(self) -> None:
        """An empty merge base cannot be reasoned about, so it fails closed."""
        ancestor, _ = self._ancestry(True)
        assert (
            is_credible_rescope(
                self._rescoped("b.py", merge_base=""), self._blocked("a.py"), ancestor
            )
            is False
        )
        blocked_without_base = ScopeResult(
            file_count=1, merge_base="", current_branch="feat/stacked", files=("a.py",)
        )
        assert is_credible_rescope(self._rescoped("b.py"), blocked_without_base, ancestor) is False

    def test_asks_ancestry_in_the_direction_that_means_stacked(self) -> None:
        """Argument order is the whole meaning: main's fork must come first."""
        ancestor, calls = self._ancestry(True)
        is_credible_rescope(self._rescoped("b.py"), self._blocked("a.py"), ancestor)
        assert calls == [(self.MAIN_FORK, self.STACK_FORK)]


class TestDocstringCitationStaysAccurate:
    """The `is_credible_rescope` docstring quotes another module by line number.

    `.claude/rules/canonical-source-mirror.md` requires a behavioral claim about
    another component to quote the line it relies on, with path and line number.
    A quote decays two ways: the source text can change, or it can move. Both
    leave a docstring that reads as verified while describing code that is no
    longer there, which is the exact failure the rule exists to prevent.

    These tests are the positive control for that citation. They fail loudly
    with the corrected line numbers rather than letting the claim rot.
    """

    QUOTED = (
        "if result.returncode != 0:",
        "raise ScopeDetectionError(",
        'f"git diff --cached against {base_ref} failed (rc={result.returncode}): "',
    )
    CITED_PATH = "scripts/detect_scope_explosion.py"
    CITED_LINES = (201, 203)

    def _source_lines(self) -> list[str]:
        root = Path(__file__).resolve().parents[1]
        return (root / self.CITED_PATH).read_text(encoding="utf-8").splitlines()

    def test_cited_lines_hold_the_quoted_text(self) -> None:
        """The exact lines named in the docstring still carry the quoted code."""
        lines = self._source_lines()
        start, end = self.CITED_LINES
        actual = tuple(line.strip() for line in lines[start - 1 : end])
        assert actual == self.QUOTED, (
            f"{self.CITED_PATH}:{start}-{end} no longer holds the quoted branch. "
            f"Found {actual!r}. Update the citation in "
            f"scripts/scope_pr_base.py::is_credible_rescope."
        )

    def test_quoted_text_appears_exactly_once(self) -> None:
        """The quote is unambiguous, so a moved citation can be repointed."""
        lines = [line.strip() for line in self._source_lines()]
        starts = [
            i for i in range(len(lines) - len(self.QUOTED) + 1)
            if tuple(lines[i : i + len(self.QUOTED)]) == self.QUOTED
        ]
        assert len(starts) == 1, (
            f"Expected one occurrence of the quoted branch in {self.CITED_PATH}, "
            f"found {len(starts)} at lines {[s + 1 for s in starts]}."
        )

    def test_docstring_contains_the_citation(self) -> None:
        """The docstring actually carries the path, the lines, and the quote."""
        doc = is_credible_rescope.__doc__ or ""
        assert f"{self.CITED_PATH}:201-203" in doc
        for fragment in self.QUOTED:
            assert fragment in doc, f"docstring lost the quoted line {fragment!r}"
