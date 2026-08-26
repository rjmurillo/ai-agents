"""Nothing in the pre-push graph may outlive the container it runs in.

Split out of `test_lefthook_declared_budget.py`, which crossed the 500-line
taste threshold when the base-ref ratchet arrived. The seam is the one the
declared-sum module's own comments already drew: that module bounds what the
configuration may CLAIM to spend on a workstation, where a long cap is the right
protection for a job with real work to do. This one bounds what a single child
process may spend inside a managed container, where a hook that runs long is not
slow but dead, because the container is reclaimed and the push carries away no
diagnostic. Different quantity, different failure, different reader.

Coverage:

- positive: no pre-push job declares a single child above the ceiling.
- negative: without the clamp the same graph exceeds it, so the assertion is
  reading the clamp rather than the declared caps under another name.
- edge: every name on the unclamped roster still exists in pre-push, so a
  rename cannot silently widen what the clamp is credited with covering.
"""

from __future__ import annotations

from tests.ci.lefthook_budget_model import (
    CONTAINER_UNCLAMPED_JOBS,
    REPO_ROOT,
    flatten,
    job_cost,
    load_config,
)

# The bound that matters is PER JOB, not the sum of every cap.
#
# An earlier revision of this module summed the clamped caps and compared the
# total against the roughly 679s at which a reclamation was observed. That
# comparison is not sound: the sum is the case where every job in the graph
# hangs to its cap on the same push, which cannot happen, and the observation it
# was compared against is a single measured push rather than a cap. Two
# different quantities.
#
# A hang is one job. So the property worth asserting is that no single job can
# run longer than this inside a container, whatever its declared cap says. The
# largest is `pre-pr-validation` at 240s, which does not route through
# `_run_command` and so carries its own cap; every job whose work is a
# subprocess is bounded by the clamp instead. Before this work the largest was
# 1800s.
#
# READ THIS BEFORE TRUSTING THE NUMBER. What the clamp bounds is one CHILD
# PROCESS, not one job, and this model conflates them for every job that spawns
# exactly one child. Two jobs spawn more:
#
#   * `python-tests` on the opt-in execution path holds an aggregate deadline
#     in `run_pytest` and passes each child its remaining time, so the job is
#     bounded, but at TEST_SUITE_TIMEOUT_SECONDS (780s), not at 240s.
#   * `security-scan` has no aggregate deadline at all: `scan_pushed_heads`
#     loops over pushed refs and each `_scan_pushed_head` gets a fresh clamp,
#     so a push of N refs costs up to N * 150s.
#
# So this assertion is evidence for "no single subprocess outlives the
# container", and only incidentally for the per-job reading. Raised in review on
# PR #5319 and tracked in #5318. The measured hook is ~148s end to end and the
# default collection path spawns one child, so the exposure is a tail case, not
# the common one; that is a reason to size the fix deliberately rather than a
# reason to keep claiming a bound that does not hold.
#
# Set to the actual largest, not above it. An earlier revision used 300s while
# the PR claimed 240s, which meant a regression to 250s would have passed the
# test that was supposed to be the claim's evidence. A ceiling with slack in it
# is a ceiling that certifies a number nobody measured. Like the declared sum,
# this leaves the graph with no room: a new job above 240s fails here until
# someone measures it and cuts something, which is the point.
CONTAINER_PER_JOB_CEILING_SECONDS = 240.0


class TestNoSingleChildOutlivesAContainer:
    """The property the originating incident is actually about.

    A developer whose hook runs long is inconvenienced. A container whose hook
    runs long is reclaimed, and the push dies carrying no diagnostic at all.
    These assertions are about the second case only.
    """

    def _per_job_container_bounds(self) -> list[tuple[float, str]]:
        import sys

        sys.path.insert(0, str(REPO_ROOT / "scripts" / "validation"))
        import git_hook_policy

        clamp = git_hook_policy.CONTAINER_SUBPROCESS_CEILING_SECONDS
        bounds = [
            (job_cost(job, clamp), str(job.get("name", "<unnamed>")))
            for entry in load_config()["pre-push"]["jobs"]
            if isinstance(entry, dict)
            for job in flatten(entry)
        ]
        return sorted(bounds, reverse=True)

    def test_no_job_declares_a_single_child_above_the_container_ceiling(self) -> None:
        bounds = self._per_job_container_bounds()
        over = [(cost, name) for cost, name in bounds if cost > CONTAINER_PER_JOB_CEILING_SECONDS]
        detail = ", ".join(f"{name} {cost:.0f}s" for cost, name in over)
        assert over == [], (
            f"{detail} can run longer than {CONTAINER_PER_JOB_CEILING_SECONDS:.0f}s "
            "inside a container. A container is reclaimed after a period without "
            "progress and a reclaimed push leaves no diagnostic, so a job that can "
            "outlast it destroys the push rather than slowing it. Cut the cap, or "
            "move the job's work behind git_hook_policy._run_command so the clamp "
            "reaches it."
        )

    def test_the_clamp_actually_binds(self) -> None:
        """Negative control: without the clamp, jobs exceed the per-job ceiling.

        If this ever passes, the clamp is doing nothing and the assertion above
        is reading the declared caps under another name.
        """
        unclamped = [
            (job_cost(job, None), str(job.get("name", "")))
            for entry in load_config()["pre-push"]["jobs"]
            if isinstance(entry, dict)
            for job in flatten(entry)
        ]
        assert [c for c, _ in unclamped if c > CONTAINER_PER_JOB_CEILING_SECONDS] != []

    def test_every_unclamped_job_exists(self) -> None:
        """A stale name in the roster silently widens the clamp's coverage.

        A job listed here but absent from pre-push contributes nothing, and a
        job renamed out from under the roster starts being treated as clamped
        when nothing clamps it. Either way the container bound above becomes a
        number about a graph that does not exist.
        """
        names = {
            str(job.get("name"))
            for entry in load_config()["pre-push"]["jobs"]
            if isinstance(entry, dict)
            for job in flatten(entry)
        }
        missing = sorted(CONTAINER_UNCLAMPED_JOBS - names)
        assert missing == [], f"{missing} are in the roster but not in pre-push."
