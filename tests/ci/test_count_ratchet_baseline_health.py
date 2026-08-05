"""Whether a baseline scalar still describes the tree it guards.

Split from ``test_count_ratchet.py`` to keep that file under the taste-lint
size ceiling. The subject here is one function, so it reads better alone.
"""

from __future__ import annotations

from scripts.ci import count_ratchet


class TestBaselineHealth:
    """`baseline_health` decides when a scalar stops describing its tree.

    The boundary is the whole point. Equality is the ideal, a small gap is the
    accepted cost of the concurrent-lowering race in issue #4057, and anything
    above the tree is a regression the branch introduced.
    """

    def test_equality_is_healthy(self):
        """The ideal state: the scalar is exactly what the tree measures."""
        assert count_ratchet.baseline_health(592, 592) is None

    def test_slack_within_the_bound_is_healthy(self):
        """The accepted state. Two concurrent lowerings leave a gap of one.

        Reddening here is the outage PR #4214 resolved, so this must pass.
        """
        assert count_ratchet.baseline_health(592, 593) is None

    def test_slack_exactly_at_the_bound_is_healthy(self):
        """Edge: the bound is inclusive, so ``slack == max_slack`` passes."""
        actual = 592
        baseline = actual + count_ratchet.MAX_BASELINE_SLACK
        assert count_ratchet.baseline_health(actual, baseline) is None

    def test_slack_one_past_the_bound_is_reported(self):
        """Edge: one more than the bound fails, and names the true count.

        Without this the accepted slack would grow without limit, and the gap
        would silently absorb later regressions.
        """
        actual = 592
        baseline = actual + count_ratchet.MAX_BASELINE_SLACK + 1
        problem = count_ratchet.baseline_health(actual, baseline)
        assert problem is not None
        assert "write 592 into the baseline file" in problem

    def test_a_tree_above_the_baseline_is_reported_as_a_regression(self):
        """Negative: violations were added. The remedy is removal, not a raise."""
        problem = count_ratchet.baseline_health(594, 593)
        assert problem is not None
        assert "1 violation(s) were added" in problem
        assert "rather than raising the baseline" in problem

    def test_the_two_failures_do_not_share_a_remedy(self):
        """A regression and dead allowance must not read as the same problem.

        They are opposite edits. Conflating them is how a contributor "fixes" a
        regression by raising the baseline, which is the one move the ratchet
        exists to prevent.
        """
        regression = count_ratchet.baseline_health(600, 593)
        stale = count_ratchet.baseline_health(580, 593)
        assert regression is not None and stale is not None
        assert regression != stale
        assert "were added" in regression
        assert "were added" not in stale

    def test_the_bound_is_configurable(self):
        """A caller may tighten the bound without editing the module."""
        assert count_ratchet.baseline_health(592, 593, max_slack=0) is not None
        assert count_ratchet.baseline_health(592, 592, max_slack=0) is None
