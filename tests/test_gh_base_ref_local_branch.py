"""Tests for `_gh_base_ref`'s upstream-head retry-gating (issue #4382),
covering the two scenarios the binary-grounded suite cannot express.

Issue #4382: inside a worktree where the local branch name does not match the
PR head (e.g. `pr-4294` locally vs. `fix/gc-report-time-budget` on GitHub),
`gh pr view` (no `--head` arg) fails, and `_gh_base_ref` retries via the
upstream tracking ref stripped of the `origin/` prefix. The happy path,
successful retry, both-no-PR, and no-upstream cases for that retry are
covered by `tests/test_checks_common_pr_head_fallback.py` against a fake
grounded on the real `gh` binary; this file holds only the two retry-gating
regressions (round 2 review finding, item 4) that need to assert on the
exact subprocess call sequence, which that grounded fake does not expose:
a transient failure must not trigger the retry, and a self-tracking
upstream must not repeat the query that already confirmed no PR.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from scripts.validation.checks_common import _gh_base_ref


class TestGhBaseRefLocalBranchRetryGating:
    """The upstream-head retry (issue #4382) must not fire when it cannot
    possibly produce a new answer: on an unconfirmed (transient) failure, or
    when the upstream head is the same branch name already queried.
    """

    def test_transient_first_failure_does_not_retry(self, tmp_path: Path) -> None:
        """A transient failure (unconfirmed no-PR: auth, network, rate
        limit) must not enter the upstream-head retry at all -- round 2
        review finding, item 4. Contrast with a confirmed no-PR (stderr
        containing gh's actual no-PR marker), which does retry -- see
        ``test_gh_base_ref_retries_with_the_upstream_head`` in
        ``tests/test_checks_common_pr_head_fallback.py``.
        """
        calls: list[list[str]] = []

        def _run(cmd, **kwargs):
            calls.append(list(cmd))
            if cmd[:3] == ["gh", "pr", "view"] and len(cmd) == 7:
                return (1, "", "no PR for current branch")
            if "rev-parse" in cmd:
                return (0, "pr-4294\n", "")
            if "config" in cmd:
                return (0, "refs/heads/fix/some-feature\n", "")
            if cmd[:4] == ["gh", "pr", "view", "fix/some-feature"]:
                return (0, "main\n", "")
            return (1, "", "unexpected")

        with (
            patch("scripts.validation.checks_common.shutil.which", return_value="/usr/bin/gh"),
            patch("scripts.validation.checks_common._run_subprocess", side_effect=_run),
        ):
            result = _gh_base_ref(tmp_path)

        assert result is None
        head_calls = [c for c in calls if c[:4] == ["gh", "pr", "view", "fix/some-feature"]]
        assert not head_calls, "a transient failure must not retry with the upstream head"
        # ``rev-parse --abbrev-ref HEAD`` / ``rev-parse HEAD`` are also made
        # by ``_branch_head_cache_key`` for the OUTER cache key, unrelated to
        # the retry; ``config --get branch.<x>.merge`` is unique to
        # ``_upstream_head_ref_name``, which only the retry path calls.
        config_calls = [c for c in calls if "config" in c]
        assert not config_calls, "a transient failure must not even query the upstream head branch"

    def test_retry_skipped_when_upstream_head_equals_local_branch(self, tmp_path: Path) -> None:
        """Self-tracking upstream (``git push -u origin HEAD``): the
        upstream head branch name is identical to the local branch name, so
        retrying would repeat the exact query that already confirmed no PR
        (round 2 review finding, item 4).
        """
        calls: list[list[str]] = []

        def _run(cmd, **kwargs):
            calls.append(list(cmd))
            if cmd[:3] == ["gh", "pr", "view"] and len(cmd) == 7:
                return (1, "", 'no pull requests found for branch "feature-x"')
            if "rev-parse" in cmd:
                return (0, "feature-x\n", "")
            if "config" in cmd:
                return (0, "refs/heads/feature-x\n", "")
            return (1, "", "unexpected")

        with (
            patch("scripts.validation.checks_common.shutil.which", return_value="/usr/bin/gh"),
            patch("scripts.validation.checks_common._run_subprocess", side_effect=_run),
        ):
            result = _gh_base_ref(tmp_path)

        assert result is None
        second_gh_calls = [c for c in calls if c[:3] == ["gh", "pr", "view"] and len(c) == 4]
        assert not second_gh_calls, "same-named upstream head must not trigger a second gh call"
