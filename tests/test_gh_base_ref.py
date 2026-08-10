"""Tests for the `_gh_base_ref` probe, cache, and reset in checks_common.

Covers per-process memoization keyed on `(repo_root, branch, HEAD sha)`
(perf/git-hook-latency), the run-boundary cache reset (`_reset_gh_base_cache`),
and the local-branch-name-differs-from-PR-head retry path (issue #4382).

Self-tracking-upstream detection tests live in
`tests/test_self_tracking_upstream.py`; the subprocess wrapper, remote-refresh
helper, and build-script gate live in `tests/test_checks_common.py`.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.validation import checks_common
from scripts.validation.checks_common import (
    _gh_base_ref,
    _PrViewProbe,
    _reset_gh_base_cache,
    _resolve_branch_base_ref,
    _resolve_default_base_ref,
)
from tests.gh_base_ref_test_helpers import _commit, _init_git_repo

# ---------------------------------------------------------------------------
# _resolve_branch_base_ref -- per-process memoization (perf/git-hook-latency)
# ---------------------------------------------------------------------------


class TestGhBaseRefCaching:
    """``_gh_base_ref`` caches only the ``gh pr view`` query, keyed on
    ``(repo_root, branch, HEAD sha)`` (perf/git-hook-latency, revised).

    A prior version cached the entire :func:`_resolve_branch_base_ref` chain
    with a bare ``functools.cache``, which had no invalidation hook at all:
    a branch switch or new commit mid-process would keep serving the first
    answer. This suite locks in the replacement contract: only the network
    query is cached, the key invalidates on branch and HEAD, transient
    gh/auth/network failures are never cached, a verified "no open PR" is
    cached, and non-no-PR failures are logged exactly once per key.
    """

    def setup_method(self) -> None:
        checks_common._gh_pr_base_cache.clear()
        checks_common._gh_pr_base_logged_failures.clear()

    @staticmethod
    def _solo_repo(tmp_path: Path) -> Path:
        """A single-commit repo with no remote and no upstream configured."""
        repo = tmp_path / "solo"
        repo.mkdir(parents=True)
        _init_git_repo(repo)
        _commit(repo, "a.txt", "a\n", "chore: seed")
        return repo

    @pytest.mark.parametrize("call_count", [2, 3], ids=["two-calls", "three-gate-calls"])
    def test_repeated_calls_for_same_branch_head_probe_gh_once(
        self, tmp_path: Path, call_count: int
    ) -> None:
        """Regardless of how many gates ask, the network-costing probe runs
        exactly once per ``(repo_root, branch, HEAD)``."""
        repo = self._solo_repo(tmp_path)
        with (
            patch("scripts.validation.checks_common.shutil.which", return_value="/usr/bin/gh"),
            patch("scripts.validation.checks_common._gh_pr_base_ref_name") as mock_probe,
        ):
            mock_probe.return_value = _PrViewProbe("main", False, 0, "")

            results = [_gh_base_ref(repo) for _ in range(call_count)]

        assert results == ["origin/main"] * call_count
        mock_probe.assert_called_once()

    def test_confirmed_no_pr_is_cached(self, tmp_path: Path) -> None:
        """A verified 'no open PR' is a stable answer for this branch/HEAD,
        not a signal to retry -- retrying would re-pay the network cost for
        the same non-answer."""
        repo = self._solo_repo(tmp_path)
        with (
            patch("scripts.validation.checks_common.shutil.which", return_value="/usr/bin/gh"),
            patch("scripts.validation.checks_common._gh_pr_base_ref_name") as mock_probe,
        ):
            mock_probe.return_value = _PrViewProbe(
                None, True, 1, 'no pull requests found for branch "solo"'
            )

            first = _gh_base_ref(repo)
            second = _gh_base_ref(repo)

        assert first is None
        assert second is None
        mock_probe.assert_called_once()

    def test_transient_failure_is_not_cached(self, tmp_path: Path) -> None:
        """An auth/network/rate-limit failure must be retried on the next
        call, not frozen in as a false 'no PR' for the rest of the process."""
        repo = self._solo_repo(tmp_path)
        with (
            patch("scripts.validation.checks_common.shutil.which", return_value="/usr/bin/gh"),
            patch("scripts.validation.checks_common._gh_pr_base_ref_name") as mock_probe,
        ):
            mock_probe.return_value = _PrViewProbe(None, False, 1, "HTTP 401: Bad credentials")

            first = _gh_base_ref(repo)
            second = _gh_base_ref(repo)
            third = _gh_base_ref(repo)

        assert (first, second, third) == (None, None, None)
        assert mock_probe.call_count == 3

    def test_transient_failure_logged_once_not_per_call(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A persistent auth/network problem should be visible, but not repeat
        the same line for every gate in one ``pre_pr.py`` run."""
        repo = self._solo_repo(tmp_path)
        with (
            patch("scripts.validation.checks_common.shutil.which", return_value="/usr/bin/gh"),
            patch("scripts.validation.checks_common._gh_pr_base_ref_name") as mock_probe,
        ):
            mock_probe.return_value = _PrViewProbe(None, False, 1, "HTTP 401: Bad credentials")

            for _ in range(3):
                _gh_base_ref(repo)

        stderr = capsys.readouterr().err
        assert stderr.count("Bad credentials") == 1
        assert "[WARN]" in stderr

    def test_different_repo_roots_are_resolved_independently(self, tmp_path: Path) -> None:
        """The cache must not let one repo's answer leak into another's."""
        repo_a = self._solo_repo(tmp_path / "a")
        repo_b = self._solo_repo(tmp_path / "b")

        with (
            patch("scripts.validation.checks_common.shutil.which", return_value="/usr/bin/gh"),
            patch("scripts.validation.checks_common._gh_pr_base_ref_name") as mock_probe,
        ):
            mock_probe.side_effect = [
                _PrViewProbe("main", False, 0, ""),
                _PrViewProbe("develop", False, 0, ""),
            ]

            result_a = _gh_base_ref(repo_a)
            result_b = _gh_base_ref(repo_b)
            result_a_again = _gh_base_ref(repo_a)

        assert result_a == "origin/main"
        assert result_b == "origin/develop"
        assert result_a_again == "origin/main"
        assert mock_probe.call_count == 2

    def test_branch_switch_invalidates_the_cache(self, tmp_path: Path) -> None:
        """Checking out a different branch must not reuse the prior branch's
        cached answer -- the key includes the branch name."""
        repo = self._solo_repo(tmp_path)
        subprocess.run(
            ["git", "checkout", "-b", "other-branch"],
            cwd=repo,
            check=True,
            capture_output=True,
        )

        with (
            patch("scripts.validation.checks_common.shutil.which", return_value="/usr/bin/gh"),
            patch("scripts.validation.checks_common._gh_pr_base_ref_name") as mock_probe,
        ):
            mock_probe.side_effect = [
                _PrViewProbe("main", False, 0, ""),
                _PrViewProbe("develop", False, 0, ""),
            ]

            subprocess.run(["git", "checkout", "main"], cwd=repo, check=True, capture_output=True)
            first = _gh_base_ref(repo)

            subprocess.run(
                ["git", "checkout", "other-branch"], cwd=repo, check=True, capture_output=True
            )
            second = _gh_base_ref(repo)

        assert first == "origin/main"
        assert second == "origin/develop"
        assert mock_probe.call_count == 2

    def test_new_commit_invalidates_the_cache(self, tmp_path: Path) -> None:
        """Advancing HEAD (a new commit) must not reuse the prior HEAD's
        cached answer -- the key includes the HEAD sha."""
        repo = self._solo_repo(tmp_path)

        with (
            patch("scripts.validation.checks_common.shutil.which", return_value="/usr/bin/gh"),
            patch("scripts.validation.checks_common._gh_pr_base_ref_name") as mock_probe,
        ):
            mock_probe.side_effect = [
                _PrViewProbe("main", False, 0, ""),
                _PrViewProbe("develop", False, 0, ""),
            ]

            first = _gh_base_ref(repo)
            _commit(repo, "b.txt", "b\n", "chore: second commit")
            second = _gh_base_ref(repo)

        assert first == "origin/main"
        assert second == "origin/develop"
        assert mock_probe.call_count == 2

    def test_branch_and_default_resolvers_share_one_probe(self, tmp_path: Path) -> None:
        """``_resolve_branch_base_ref`` and ``_resolve_default_base_ref`` both
        call ``_gh_base_ref``; within one branch/HEAD state they must share
        its cached result rather than each paying their own network cost.

        Uses a real solo repo (no mocked ``_run_subprocess``) so the
        ``git rev-parse --verify``/self-tracking/cache-key plumbing that both
        resolvers also perform runs for real; only the network-costing gh
        probe is mocked, which is the one call this test asserts on.
        """
        repo = self._solo_repo(tmp_path)

        with (
            patch("scripts.validation.checks_common.shutil.which", return_value="/usr/bin/gh"),
            patch("scripts.validation.checks_common._gh_pr_base_ref_name") as mock_probe,
        ):
            mock_probe.return_value = _PrViewProbe("main", False, 0, "")

            _resolve_branch_base_ref(repo)
            _resolve_default_base_ref(repo)

        mock_probe.assert_called_once()

    def test_uncached_fallback_semantics_are_unchanged(self, tmp_path: Path) -> None:
        """No cache mechanics change what resolution returns when nothing
        resolves: no PR, no upstream, no origin remote in a plain
        ``tmp_path`` still yields None.
        """
        subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)

        with patch("scripts.validation.checks_common.shutil.which", return_value=None):
            assert _resolve_branch_base_ref(tmp_path) is None


# ---------------------------------------------------------------------------
# _reset_gh_base_cache -- run-boundary cache scoping (item 3, round 2 review)
# ---------------------------------------------------------------------------


class TestResetGhBaseCache:
    """The gh PR-base cache is keyed on (repo_root, branch, HEAD sha), a
    proxy for "did the local checkout change", not for "did the remote PR
    change". Two invocations of ``pre_pr.py`` in the same process (a retry,
    or a test harness calling ``main()`` twice) with an unchanged
    branch/HEAD must not let the second invocation reuse the first's
    answer -- ``_reset_gh_base_cache`` is the run-boundary hook that
    prevents that.
    """

    def setup_method(self) -> None:
        checks_common._gh_pr_base_cache.clear()
        checks_common._gh_pr_base_logged_failures.clear()

    @staticmethod
    def _solo_repo(tmp_path: Path) -> Path:
        repo = tmp_path / "solo"
        repo.mkdir(parents=True)
        _init_git_repo(repo)
        _commit(repo, "a.txt", "a\n", "chore: seed")
        return repo

    def test_clears_the_cache_dict(self, tmp_path: Path) -> None:
        repo = self._solo_repo(tmp_path)
        with (
            patch("scripts.validation.checks_common.shutil.which", return_value="/usr/bin/gh"),
            patch("scripts.validation.checks_common._gh_pr_base_ref_name") as mock_probe,
        ):
            mock_probe.return_value = _PrViewProbe("main", False, 0, "")
            _gh_base_ref(repo)
        assert checks_common._gh_pr_base_cache

        _reset_gh_base_cache()

        assert checks_common._gh_pr_base_cache == {}

    def test_clears_the_logged_failures_set(self, tmp_path: Path) -> None:
        repo = self._solo_repo(tmp_path)
        with (
            patch("scripts.validation.checks_common.shutil.which", return_value="/usr/bin/gh"),
            patch("scripts.validation.checks_common._gh_pr_base_ref_name") as mock_probe,
        ):
            mock_probe.return_value = _PrViewProbe(None, False, 1, "HTTP 401: Bad credentials")
            _gh_base_ref(repo)
        assert checks_common._gh_pr_base_logged_failures

        _reset_gh_base_cache()

        assert checks_common._gh_pr_base_logged_failures == set()

    def test_same_branch_and_head_gets_a_fresh_answer_after_reset(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """The scenario the run-boundary reset exists for: branch and HEAD
        are IDENTICAL across two "invocations" (nothing was committed or
        checked out in between), yet the remote PR state is what changed
        (e.g. a PR was opened between the two runs). Without a reset, the
        cache key would be unchanged and the second call would wrongly
        reuse the first invocation's None.
        """
        repo = self._solo_repo(tmp_path)
        with (
            patch("scripts.validation.checks_common.shutil.which", return_value="/usr/bin/gh"),
            patch("scripts.validation.checks_common._gh_pr_base_ref_name") as mock_probe,
        ):
            mock_probe.return_value = _PrViewProbe(
                None, True, 1, 'no pull requests found for branch "solo"'
            )
            first = _gh_base_ref(repo)

            _reset_gh_base_cache()

            mock_probe.return_value = _PrViewProbe("main", False, 0, "")
            second = _gh_base_ref(repo)

        assert first is None
        assert second == "origin/main"
        assert mock_probe.call_count == 2, "the reset must force a fresh gh query"
