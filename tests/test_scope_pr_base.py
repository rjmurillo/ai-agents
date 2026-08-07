"""Tests for scripts/scope_pr_base.py.

Covers the three pieces the scope gate uses to ask what a PR is really built
on: remote-prefix normalization, the gh lookup, and the credibility test that
decides whether a second measurement may be trusted.

Every function here fails closed, so the negative cases carry the weight.
"""

from __future__ import annotations

import json
import subprocess
from unittest.mock import patch

import pytest

from scripts.detect_scope_explosion import ScopeResult
from scripts.scope_pr_base import (
    _is_plain_branch_name,
    is_credible_rescope,
    resolve_pr_base_branch,
    strip_remote_prefix,
)


class TestStripRemotePrefix:
    """Tests for strip_remote_prefix."""

    def test_strips_origin(self) -> None:
        """A remote-qualified ref loses the remote."""
        assert strip_remote_prefix("origin/main") == "main"

    def test_leaves_plain_name(self) -> None:
        """A plain branch name passes through untouched."""
        assert strip_remote_prefix("main") == "main"

    def test_strips_only_the_leading_occurrence(self) -> None:
        """A branch whose name embeds the prefix keeps the inner text."""
        assert strip_remote_prefix("origin/feat/origin/thing") == "feat/origin/thing"

    def test_leaves_other_remotes(self) -> None:
        """Only origin is stripped; another remote is not this script's base."""
        assert strip_remote_prefix("upstream/main") == "upstream/main"


class TestResolvePrBaseBranch:
    """Tests for resolve_pr_base_branch."""

    @staticmethod
    def _gh(stdout: str, returncode: int = 0):
        return subprocess.CompletedProcess(
            args=[], returncode=returncode, stdout=stdout, stderr=""
        )

    def test_returns_base_ref_name(self) -> None:
        """Exactly one open PR yields its base branch name."""
        with (
            patch(
                "scripts.scope_pr_base.shutil.which",
                return_value="/usr/bin/gh",
            ),
            patch(
                "scripts.scope_pr_base.subprocess.run",
                return_value=self._gh('[{"baseRefName": "fix/base-branch"}]'),
            ),
        ):
            assert resolve_pr_base_branch("feat/stacked") == "fix/base-branch"

    def test_queries_only_open_prs_for_this_branch(self) -> None:
        """gh pr view falls back to a merged PR, so the query must be explicit.

        Verified against gh 2.97.0: on a branch whose PR had already merged,
        `gh pr view` returned that PR with state=MERGED. A reused branch would
        then be rescoped against a dead PR's base.
        """
        with (
            patch(
                "scripts.scope_pr_base.shutil.which",
                return_value="/usr/bin/gh",
            ),
            patch(
                "scripts.scope_pr_base.subprocess.run",
                return_value=self._gh('[{"baseRefName": "main"}]'),
            ) as run,
        ):
            resolve_pr_base_branch("feat/stacked")
        argv = run.call_args.args[0]
        assert "view" not in argv
        assert argv[:3] == ["gh", "pr", "list"]
        assert "--state" in argv and argv[argv.index("--state") + 1] == "open"
        assert "--head" in argv and argv[argv.index("--head") + 1] == "feat/stacked"

    def test_returns_none_when_no_open_pr_matches(self) -> None:
        """An empty list means no open PR, which is a normal local state."""
        with (
            patch(
                "scripts.scope_pr_base.shutil.which",
                return_value="/usr/bin/gh",
            ),
            patch(
                "scripts.scope_pr_base.subprocess.run",
                return_value=self._gh("[]"),
            ),
        ):
            assert resolve_pr_base_branch("feat/stacked") is None

    def test_returns_none_when_several_open_prs_match(self) -> None:
        """Picking one of several open PRs would be a guess that removes a block."""
        with (
            patch(
                "scripts.scope_pr_base.shutil.which",
                return_value="/usr/bin/gh",
            ),
            patch(
                "scripts.scope_pr_base.subprocess.run",
                return_value=self._gh(
                    '[{"baseRefName": "main"}, {"baseRefName": "fix/other"}]'
                ),
            ),
        ):
            assert resolve_pr_base_branch("feat/stacked") is None

    def test_returns_none_on_malformed_json(self) -> None:
        """Unparseable gh output yields None rather than an exception."""
        with (
            patch(
                "scripts.scope_pr_base.shutil.which",
                return_value="/usr/bin/gh",
            ),
            patch(
                "scripts.scope_pr_base.subprocess.run",
                return_value=self._gh("not json at all"),
            ),
        ):
            assert resolve_pr_base_branch("feat/stacked") is None

    def test_returns_none_on_non_list_payload(self) -> None:
        """A JSON object where a list is expected yields None."""
        with (
            patch(
                "scripts.scope_pr_base.shutil.which",
                return_value="/usr/bin/gh",
            ),
            patch(
                "scripts.scope_pr_base.subprocess.run",
                return_value=self._gh('{"baseRefName": "main"}'),
            ),
        ):
            assert resolve_pr_base_branch("feat/stacked") is None

    def test_returns_none_when_gh_missing(self) -> None:
        """No gh on PATH is a normal local state, not an error.

        Asserts the subprocess was never reached. Without that the test passes
        even with the PATH check deleted, because it then shells out to the
        real gh and depends on the host having no open PR for this name.
        """
        with (
            patch("scripts.scope_pr_base.shutil.which", return_value=None),
            patch("scripts.scope_pr_base.subprocess.run") as run,
        ):
            assert resolve_pr_base_branch("feat/stacked") is None
        run.assert_not_called()

    def test_returns_none_when_the_payload_holds_a_non_object(self) -> None:
        """gh is trusted for shape as well as content, so the shape is checked.

        A list of one string parses as valid JSON with length one and reaches
        the same code path as a PR object. Without the type check that is an
        AttributeError inside a git hook rather than a refusal.
        """
        completed = subprocess.CompletedProcess(
            args=[], returncode=0, stdout='["fix/parent"]', stderr=""
        )
        with (
            patch("scripts.scope_pr_base.shutil.which", return_value="/usr/bin/gh"),
            patch("scripts.scope_pr_base.subprocess.run", return_value=completed),
        ):
            assert resolve_pr_base_branch("feat/stacked") is None

    def test_returns_none_on_nonzero_exit(self) -> None:
        """A gh failure (auth, offline) yields None."""
        with (
            patch(
                "scripts.scope_pr_base.shutil.which",
                return_value="/usr/bin/gh",
            ),
            patch(
                "scripts.scope_pr_base.subprocess.run",
                return_value=self._gh("", returncode=1),
            ),
        ):
            assert resolve_pr_base_branch("feat/stacked") is None

    def test_returns_none_on_empty_base_name(self) -> None:
        """A match carrying a blank base name yields None, not an empty string."""
        with (
            patch(
                "scripts.scope_pr_base.shutil.which",
                return_value="/usr/bin/gh",
            ),
            patch(
                "scripts.scope_pr_base.subprocess.run",
                return_value=self._gh('[{"baseRefName": "  "}]'),
            ),
        ):
            assert resolve_pr_base_branch("feat/stacked") is None

    def test_returns_none_on_timeout(self) -> None:
        """A hung network call must not propagate out of a git hook."""
        with (
            patch(
                "scripts.scope_pr_base.shutil.which",
                return_value="/usr/bin/gh",
            ),
            patch(
                "scripts.scope_pr_base.subprocess.run",
                side_effect=subprocess.TimeoutExpired(cmd="gh", timeout=5),
            ),
        ):
            assert resolve_pr_base_branch("feat/stacked") is None

    def test_returns_none_on_oserror(self) -> None:
        """A gh binary that cannot execute yields None."""
        with (
            patch(
                "scripts.scope_pr_base.shutil.which",
                return_value="/usr/bin/gh",
            ),
            patch(
                "scripts.scope_pr_base.subprocess.run",
                side_effect=OSError("exec format error"),
            ),
        ):
            assert resolve_pr_base_branch("feat/stacked") is None

    def test_uses_a_bounded_timeout(self) -> None:
        """The gh call is bounded so a hook cannot hang on it."""
        with (
            patch(
                "scripts.scope_pr_base.shutil.which",
                return_value="/usr/bin/gh",
            ),
            patch(
                "scripts.scope_pr_base.subprocess.run",
                return_value=self._gh('[{"baseRefName": "main"}]'),
            ) as run,
        ):
            resolve_pr_base_branch("feat/stacked")
        assert run.call_args.kwargs["timeout"] == 5


class TestResolveRejectsUntrustedBaseNames:
    """The name validation must be wired into resolve, not merely available.

    Mutation control: deleting the validation from ``resolve_pr_base_branch``
    and coercing with ``str(base or "")`` instead left every other test in this
    file passing. These are the tests that fail on that mutation.

    ``baseRefName`` comes from a network response and is interpolated into a
    ref that reaches ``git``, so the shape has to be checked at the boundary.
    """

    @staticmethod
    def _resolve(base_value: object) -> str | None:
        payload = json.dumps([{"baseRefName": base_value}])
        completed = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=payload, stderr=""
        )
        with (
            patch("scripts.scope_pr_base.shutil.which", return_value="/usr/bin/gh"),
            patch("scripts.scope_pr_base.subprocess.run", return_value=completed),
        ):
            return resolve_pr_base_branch("feat/stacked")

    def test_accepts_an_ordinary_branch_name(self) -> None:
        """Positive control: without this the rejections prove nothing."""
        assert self._resolve("fix/parent") == "fix/parent"

    def test_rejects_a_non_string_base(self) -> None:
        """A JSON number must not be coerced into a plausible branch name.

        ``str(123)`` is ``"123"``, which matches the plain-name shape and would
        be handed to git as a real ref.
        """
        assert self._resolve(123) is None

    def test_rejects_a_null_base(self) -> None:
        assert self._resolve(None) is None

    @pytest.mark.parametrize(
        "name",
        [
            "HEAD",
            "MERGE_HEAD",
            "--upload-pack=touch /tmp/pwned",
            "../../etc/passwd",
            "fix/..%2Fparent",
            "fix/parent;rm -rf .",
            "fix/\nparent",
            "fix/parent\ttab",
            "fix/parent.lock",
            "fix/parent/",
            "",
            "   ",
        ],
    )
    def test_rejects_a_name_git_would_read_as_something_else(
        self, name: str
    ) -> None:
        """Reserved refs, traversal, option-looking names, and metacharacters.

        ``HEAD`` is the sharpest of these: it is a legal string that resolves
        ``origin/HEAD`` to the default branch, so it would silently re-measure
        against main and report a stacked base that does not exist.
        """
        assert self._resolve(name) is None

    def test_strips_surrounding_whitespace_before_validating(self) -> None:
        """Normalization runs first, so a padded name is cleaned, not refused.

        Order matters in both directions: validating before stripping would
        reject an ordinary name over trailing whitespace, and stripping without
        validating would pass the padding through into a ref.
        """
        assert self._resolve("  fix/parent\n") == "fix/parent"


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

    def test_rejects_zero_files(self) -> None:
        """A failed git diff reads as zero files, which would clear the block.

        get_index_files_against_ref returns [] on any nonzero git diff and
        detect_scope turns that into ScopeResult(file_count=0) rather than
        None. A genuinely empty result is indistinguishable from that
        failure at this call site, so both are refused.
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


class TestIsPlainBranchName:
    """Tests for _is_plain_branch_name.

    The resolved base reaches git as origin/<name>, so a name carrying
    revision syntax resolves to something other than a branch.
    """

    @pytest.mark.parametrize(
        "name",
        ["main", "feat/stacked", "release-1.2", "user/feat_x", "a", "v1.0.0"],
    )
    def test_accepts_ordinary_branch_names(self, name: str) -> None:
        """Names real branches actually use are accepted."""
        assert _is_plain_branch_name(name) is True

    @pytest.mark.parametrize(
        "name",
        [
            "",
            "HEAD",
            "FETCH_HEAD",
            "ORIG_HEAD",
            "MERGE_HEAD",
            "-rf",
            "--force",
            "a..b",
            "main~1",
            "main^",
            "main@{1}",
            "refs:main",
            "has space",
            "star*",
            "quest?",
            "brack[et",
            "back\\slash",
            "trailing/",
            "thing.lock",
            "/leading",
            ".dotfirst",
        ],
    )
    def test_rejects_anything_that_is_not_a_plain_name(self, name: str) -> None:
        """Revision syntax, option-looking names, and reserved refs are refused."""
        assert _is_plain_branch_name(name) is False
