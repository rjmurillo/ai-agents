"""Tests for scripts/scope_pr_base.py.

Covers the three pieces the scope gate uses to ask what a PR is really built
on: remote-prefix normalization, the gh lookup, and the credibility test that
decides whether a second measurement may be trusted.

Every function here fails closed, so the negative cases carry the weight.
"""

from __future__ import annotations

import subprocess
from unittest.mock import patch

from scripts.detect_scope_explosion import ScopeResult
from scripts.scope_pr_base import (
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
        """No gh on PATH is a normal local state, not an error."""
        with patch("scripts.scope_pr_base.shutil.which", return_value=None):
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


class TestIsCredibleRescope:
    """Tests for is_credible_rescope."""

    @staticmethod
    def _result(*files: str) -> ScopeResult:
        return ScopeResult(
            file_count=len(files),
            merge_base="abc123def456",
            current_branch="feat/stacked",
            files=files,
        )

    def test_rejects_none(self) -> None:
        """An unresolvable re-measurement is not credible."""
        assert is_credible_rescope(None, self._result("a.py")) is False

    def test_rejects_zero_files(self) -> None:
        """A failed git diff reads as zero files, which would clear the block.

        get_index_files_against_ref returns [] on any nonzero git diff and
        detect_scope turns that into ScopeResult(file_count=0) rather than
        None. A genuinely empty result is indistinguishable from that
        failure, so both are refused.
        """
        assert is_credible_rescope(self._result(), self._result("a.py")) is False

    def test_rejects_a_file_the_first_pass_never_saw(self) -> None:
        """A foreign file means the two runs did not compare the same thing."""
        blocked = self._result("a.py", "b.py")
        foreign = self._result("a.py", "elsewhere.py")
        assert is_credible_rescope(foreign, blocked) is False

    def test_accepts_a_proper_subset(self) -> None:
        """A stacked-base surface is contained in the main-relative surface."""
        blocked = self._result("a.py", "b.py", "c.py")
        assert is_credible_rescope(self._result("b.py"), blocked) is True

    def test_accepts_an_identical_set(self) -> None:
        """A subset includes the equal case; the count is what changes."""
        blocked = self._result("a.py", "b.py")
        assert is_credible_rescope(self._result("a.py", "b.py"), blocked) is True

    def test_ignores_ordering(self) -> None:
        """Containment is a set relation, not a sequence comparison."""
        blocked = self._result("a.py", "b.py")
        assert is_credible_rescope(self._result("b.py", "a.py"), blocked) is True
