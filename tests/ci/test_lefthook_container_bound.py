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
    routes_through_the_clamp,
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
#   * `python-tests` runs up to four partition commands. `run_pytest` holds an
#     aggregate deadline over them and now passes that deadline through
#     `_container_clamped`, so the job is bounded at 150s in a container on
#     every path rather than at TEST_SUITE_TIMEOUT_SECONDS. Closed on PR #5319
#     after review found the aggregate unclamped on the ordinary subset path.
#   * `security-scan` runs one scan per pushed ref and batches targets within a
#     ref. `scan_pushed_heads` now holds one deadline across all of them and
#     passes the remaining time down, so the job is bounded at 150s in a
#     container rather than at N refs times M batches times 150s. Closed on
#     PR #5319, last of the four rounds spent on this same confusion.
#
# So this assertion is evidence for "no single subprocess outlives the
# container". The whole-job bound for those two comes from their own aggregate
# deadlines, covered in `tests/test_safe_push_pr_branch.py` and
# `tests/validation/test_security_scan_budget.py`, not from this number.
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

    def test_the_roster_matches_what_the_config_actually_routes(self) -> None:
        """Both directions, because the model no longer takes the roster's word.

        `job_cost` derives the clamp from the job's own `run:` string. The
        roster is the readable list beside it, and a list that can drift from
        the thing it describes is the hole review found on PR #5319: any job not
        named there used to be credited with a clamp, so a rename onto a direct
        command joined the clamped side silently.

        Asserting both directions is what makes the roster load-bearing again. A
        job that stops routing through `git_hook_policy.py` and is not added
        here fails, and a job named here that starts routing through it fails
        too, each naming itself.
        """
        jobs = [
            job
            for entry in load_config()["pre-push"]["jobs"]
            if isinstance(entry, dict)
            for job in flatten(entry)
        ]
        derived = {
            str(job.get("name")) for job in jobs if not routes_through_the_clamp(job)
        }

        assert derived == set(CONTAINER_UNCLAMPED_JOBS), (
            "the unclamped roster disagrees with the configuration. Only in the "
            f"roster: {sorted(set(CONTAINER_UNCLAMPED_JOBS) - derived)}. Only in "
            f"the config: {sorted(derived - set(CONTAINER_UNCLAMPED_JOBS))}. A "
            "job that stopped invoking git_hook_policy.py belongs in the roster; "
            "one that started invoking it belongs out of it. Do not edit the "
            "roster to match without reading the job's command first."
        )

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
