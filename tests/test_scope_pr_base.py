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

from scripts.scope_pr_base import (
    _is_plain_branch_name,
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
        return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr="")

    def test_returns_base_ref_name(self) -> None:
        """Exactly one open PR yields its base branch name."""
        with (
            patch(
                "scripts.scope_pr_base.shutil.which",
                return_value="/usr/bin/gh",
            ),
            patch(
                "scripts.scope_pr_base.subprocess.run",
                return_value=self._gh(
                    '[{"baseRefName": "fix/base-branch", "isCrossRepository": false}]'
                ),
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
                return_value=self._gh('[{"baseRefName": "main"}, {"baseRefName": "fix/other"}]'),
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
        payload = json.dumps([{"baseRefName": base_value, "isCrossRepository": False}])
        completed = subprocess.CompletedProcess(args=[], returncode=0, stdout=payload, stderr="")
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
    def test_rejects_a_name_git_would_read_as_something_else(self, name: str) -> None:
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


class TestResolveRefusesForkPullRequests:
    """The lookup must not accept a base chosen by a stranger.

    ``gh pr list --head`` filters on the branch name alone. A pull request
    opened from a fork carries its own head branch name, so a fork PR whose
    branch happens to match this branch's name is a match. When the local
    branch has no PR of its own that fork PR is the *only* match, it clears
    the exactly-one-result guard, and its base becomes the ref this gate
    measures against. The base of a fork PR is a branch in this repository,
    so the damage is bounded, but the choice of which one is not ours.

    ``isCrossRepository`` is false only when head and base live in the same
    repository. The check is ``is not False`` rather than a truthiness test
    because a truthiness test accepts every falsy value gh never sends,
    including ``0``, ``""``, and an absent field, and an absent field is
    exactly what a gh version that drops the column would produce.
    """

    @staticmethod
    def _resolve(entry: dict[str, object]) -> str | None:
        completed = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=json.dumps([entry]), stderr=""
        )
        with (
            patch("scripts.scope_pr_base.shutil.which", return_value="/usr/bin/gh"),
            patch("scripts.scope_pr_base.subprocess.run", return_value=completed),
        ):
            return resolve_pr_base_branch("feat/stacked")

    def test_accepts_a_pull_request_from_this_repository(self) -> None:
        """Positive control: the same payload with the flag false is accepted.

        Without this the rejection cases below would pass even if the function
        refused every payload, or was deleted outright.
        """
        assert (
            self._resolve({"baseRefName": "fix/parent", "isCrossRepository": False}) == "fix/parent"
        )

    def test_refuses_a_pull_request_from_a_fork(self) -> None:
        """A cross-repository PR is somebody else's, so its base is not ours."""
        assert self._resolve({"baseRefName": "fix/parent", "isCrossRepository": True}) is None

    def test_refuses_when_the_field_is_absent(self) -> None:
        """A gh version that omits the column must not be read as "not a fork"."""
        assert self._resolve({"baseRefName": "fix/parent"}) is None

    @pytest.mark.parametrize(
        "value",
        [None, 0, "", [], {}, "false", "no"],
        ids=["none", "zero", "empty-str", "empty-list", "empty-dict", "str-false", "str-no"],
    )
    def test_refuses_every_value_that_is_not_the_boolean_false(self, value: object) -> None:
        """Only a real boolean False passes.

        Every value here is one a truthiness test would wave through while
        carrying no evidence that the PR is local. ``"false"`` and ``"no"`` are
        the inverse trap: truthy strings that read as negative to a human.
        """
        assert self._resolve({"baseRefName": "fix/parent", "isCrossRepository": value}) is None

    def test_asks_gh_for_the_field_it_checks(self) -> None:
        """The guard is worthless if the query never requests the column.

        gh omits any field absent from --json, so dropping it there would make
        every lookup fail closed and silently disable the rescope entirely.
        """
        completed = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout='[{"baseRefName": "main", "isCrossRepository": false}]',
            stderr="",
        )
        with (
            patch("scripts.scope_pr_base.shutil.which", return_value="/usr/bin/gh"),
            patch("scripts.scope_pr_base.subprocess.run", return_value=completed) as run,
        ):
            resolve_pr_base_branch("feat/stacked")
        argv = run.call_args.args[0]
        assert "--json" in argv
        requested = argv[argv.index("--json") + 1].split(",")
        assert "isCrossRepository" in requested
        assert "baseRefName" in requested


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
