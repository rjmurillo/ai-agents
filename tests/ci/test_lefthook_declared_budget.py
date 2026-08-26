"""The declared worst case of each git hook, as a ratchet that may only fall.

ADR-104 states a 300s pre-push target and a 60s pre-commit target, then admits
both are unenforced. That admission is the gap this module closes, and it
closes it in the only way a static file can: not by measuring a push, but by
bounding what the configuration is *allowed to claim* it might spend.

Why the declared number matters even though real pushes are far below it. Two
consecutive real pushes of this branch measured 142.39s and 144.39s. The
declared worst case at that moment was 4170s, 29x higher, because jobs carried
caps chosen for an unloaded machine and never revisited. A cap is not a cost,
but it is a promise about the worst case, and the worst case is what reclaims
a container. Nothing was watching that number, so it drifted upward one job at
a time, which is exactly the accretion ADR-104 exists to stop.

The model mirrors lefthook's own scheduling semantics, which
`ci-scripts.md` MUST-17 warns must be read from the config rather than
inferred from a run summary:

- the hook's top level is `piped`, so entries run in order: sum them.
- a `parallel: true` group's members overlap: take the max.
- a `piped: true` group's members run in order: sum them.

Coverage:

- positive: each hook's declared worst case is at or below its baseline.
- negative: raising any cap above the baseline fails, and the failure names the
  job whose cap dominates its group so the reader knows where to look.
- edge: the model is exercised directly on synthetic configs covering a bare
  job, a parallel group, a piped group, and a nested group, so a scheduling
  bug in the model cannot pass by agreeing with itself on the real file.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
_LEFTHOOK = REPO_ROOT / "lefthook.yml"

# Baselines are the measured declared worst case at the time this ratchet was
# introduced, not aspirations. They may only fall. ADR-104's targets (300s
# pre-push, 60s pre-commit) are far below both; closing that distance means
# measuring jobs and cutting caps, which is issue #5318, not editing these.
#
# pre-push 2850s is dominated by three blocks nobody has measured while firing:
# the two CLI e2e smokes at 20m (they set the expensive group's cost),
# `workflow-local-run` at 10m, and `security-scan` at 15m, which ADR-054 sets
# as an enforced 900s budget this record does not overturn. On a workstation a
# long cap for those is the right protection; the container bound below is what
# the originating incident is about.
DECLARED_BUDGET_BASELINE_SECONDS: dict[str, float] = {
    "pre-push": 2850.0,
    "pre-commit": 6530.0,
}

# The declared sum above is the worst case on a developer workstation, where a
# long cap is the right protection for a job that has legitimate work to do.
# It is not the number the originating incident is about. A managed container
# is reclaimed after a period without progress, so there the question is not
# "how long may this job take" but "can anything here outlive the container".
#
# `git_hook_policy._container_clamped` answers it by clamping every subprocess
# that module spawns to CONTAINER_SUBPROCESS_CEILING_SECONDS when
# `_is_remote_container()` is true. Every pre-push job whose cost lives in a
# child process routes through it. This model applies the same clamp to the
# declared caps so the container bound is a number, not a hope.
#
# Jobs that do NOT route through `git_hook_policy._run_command` keep their
# declared cap here, because nothing clamps them: they are named rather than
# assumed, so a job moved onto or off that path shows up as a baseline change.
CONTAINER_UNCLAMPED_JOBS = frozenset(
    {
        "repair-packed-refs",
        "mutation-safety",
        "push-ref-staleness",
        "pre-pr-validation",
        "python-lint-ratchet",
        "python-lint-count-ratchet",
        "taste-count-ratchet",
        "type-ignore-count-ratchet",
        "memory-index-count-ratchet",
        "cli-exit-contract-ratchet",
        "memory-index-token-ratchet",
        "merge-tree-ratchet",
        "python-unreachable-statements",
        "path-normalization",
        "planning-artifacts",
        "branch-scope",
        "review-axis-drift",
        "worktree-gc-report",
        "python-lint-advisory",
        "infrastructure-advisory",
    }
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

_UNITS = {"h": 3600.0, "m": 60.0, "s": 1.0}


def _seconds(raw: object) -> float:
    if raw is None:
        return 0.0
    text = str(raw).strip()
    if not text:
        return 0.0
    if text[-1] in _UNITS:
        return float(text[:-1]) * _UNITS[text[-1]]
    return float(text)


def _job_cost(entry: dict[str, Any], clamp: float | None) -> float:
    declared = _seconds(entry.get("timeout"))
    if clamp is None or str(entry.get("name", "")) in CONTAINER_UNCLAMPED_JOBS:
        return declared
    return min(declared, clamp)


def _entry_cost(entry: dict[str, Any], clamp: float | None = None) -> tuple[float, str]:
    """Worst-case seconds for one top-level entry, and the job that sets it.

    ``clamp`` models `git_hook_policy._container_clamped`: when set, every job
    whose cost lives in a subprocess that module spawns is bounded by it.
    """
    group = entry.get("group")
    if not isinstance(group, dict):
        return _job_cost(entry, clamp), str(entry.get("name", "<unnamed>"))
    parts = [
        _entry_cost(job, clamp) for job in group.get("jobs", []) if isinstance(job, dict)
    ]
    if not parts:
        return 0.0, "<empty group>"
    if group.get("parallel"):
        return max(parts, key=lambda part: part[0])
    total = sum(cost for cost, _ in parts)
    worst = max(parts, key=lambda part: part[0])[1]
    return total, worst


def _declared_budget(
    config: dict[str, Any], hook: str, clamp: float | None = None
) -> tuple[float, list[tuple[float, str]]]:
    entries = [e for e in config[hook]["jobs"] if isinstance(e, dict)]
    rows = [_entry_cost(e, clamp) for e in entries]
    return sum(cost for cost, _ in rows), rows


def _config() -> dict[str, Any]:
    data = yaml.safe_load(_LEFTHOOK.read_text(encoding="utf-8"))
    assert isinstance(data, dict), "lefthook.yml must parse to a YAML mapping."
    return data


@pytest.mark.parametrize("hook", sorted(DECLARED_BUDGET_BASELINE_SECONDS))
def test_declared_budget_is_at_or_below_its_baseline(hook: str) -> None:
    baseline = DECLARED_BUDGET_BASELINE_SECONDS[hook]
    total, rows = _declared_budget(_config(), hook)
    worst = sorted(rows, key=lambda row: row[0], reverse=True)[:3]
    detail = ", ".join(f"{name} {cost:.0f}s" for cost, name in worst)
    assert total <= baseline, (
        f"{hook} declared worst case rose to {total:.0f}s against a baseline of "
        f"{baseline:.0f}s. Largest contributors: {detail}. A cap is a promise "
        "about the worst case, and the worst case is what reclaims a container. "
        "Cut a cap to fit, or measure the job during a real push "
        "(ci-scripts.md MUST-16) and lower the baseline in the same change."
    )


@pytest.mark.parametrize("hook", sorted(DECLARED_BUDGET_BASELINE_SECONDS))
def test_baseline_is_not_slack(hook: str) -> None:
    """A baseline far above the real number stops being a ratchet.

    Kept loose (10%) because caps are sized for a loaded machine, not for the
    current total. It only catches a baseline lowered carelessly or a cap cut
    that nobody folded back in.
    """
    baseline = DECLARED_BUDGET_BASELINE_SECONDS[hook]
    total, _ = _declared_budget(_config(), hook)
    assert total >= baseline * 0.9, (
        f"{hook} declared worst case is {total:.0f}s, well under its "
        f"{baseline:.0f}s baseline. Lower the baseline to {total:.0f}s so the "
        "ratchet keeps its grip."
    )


class TestTheModelMatchesLefthookScheduling:
    """Exercised on synthetic configs, so it cannot pass by agreeing with itself."""

    def test_a_bare_job_costs_its_own_timeout(self) -> None:
        cost, name = _entry_cost({"name": "solo", "timeout": "90s"})
        assert (cost, name) == (90.0, "solo")

    def test_a_parallel_group_costs_its_slowest_member(self) -> None:
        cost, name = _entry_cost(
            {
                "group": {
                    "parallel": True,
                    "jobs": [
                        {"name": "fast", "timeout": "10s"},
                        {"name": "slow", "timeout": "5m"},
                    ],
                }
            }
        )
        assert (cost, name) == (300.0, "slow")

    def test_a_piped_group_costs_the_sum_of_its_members(self) -> None:
        cost, name = _entry_cost(
            {
                "group": {
                    "piped": True,
                    "jobs": [
                        {"name": "first", "timeout": "1m"},
                        {"name": "second", "timeout": "2m"},
                    ],
                }
            }
        )
        assert (cost, name) == (180.0, "second")

    def test_a_nested_group_is_resolved_by_its_own_scheduling(self) -> None:
        cost, _ = _entry_cost(
            {
                "group": {
                    "parallel": True,
                    "jobs": [
                        {"name": "plain", "timeout": "30s"},
                        {
                            "group": {
                                "piped": True,
                                "jobs": [
                                    {"name": "a", "timeout": "40s"},
                                    {"name": "b", "timeout": "50s"},
                                ],
                            }
                        },
                    ],
                }
            }
        )
        assert cost == 90.0

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [("2h", 7200.0), ("15m", 900.0), ("45s", 45.0), ("120", 120.0), (None, 0.0)],
    )
    def test_duration_units_parse(self, raw: object, expected: float) -> None:
        assert _seconds(raw) == expected

    def test_a_raised_cap_breaks_the_budget(self) -> None:
        """Negative control for the ratchet itself.

        Without this, `test_declared_budget_is_at_or_below_its_baseline` passing
        says nothing about whether it could ever fail.
        """
        config = _config()
        before, _ = _declared_budget(config, "pre-push")
        for entry in config["pre-push"]["jobs"]:
            if isinstance(entry, dict) and entry.get("name") == "security-scan":
                entry["timeout"] = "99h"
                break
        else:  # pragma: no cover - the job is asserted to exist below
            pytest.fail("security-scan is missing from pre-push.")
        after, _ = _declared_budget(config, "pre-push")
        assert after > before
        assert after > DECLARED_BUDGET_BASELINE_SECONDS["pre-push"]


class TestNothingCanOutliveAContainer:
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
            (_job_cost(job, clamp), str(job.get("name", "<unnamed>")))
            for entry in _config()["pre-push"]["jobs"]
            if isinstance(entry, dict)
            for job in _flatten(entry)
        ]
        return sorted(bounds, reverse=True)

    def test_no_single_job_can_run_longer_than_the_per_job_ceiling(self) -> None:
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
            (_job_cost(job, None), str(job.get("name", "")))
            for entry in _config()["pre-push"]["jobs"]
            if isinstance(entry, dict)
            for job in _flatten(entry)
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
            for entry in _config()["pre-push"]["jobs"]
            if isinstance(entry, dict)
            for job in _flatten(entry)
        }
        missing = sorted(CONTAINER_UNCLAMPED_JOBS - names)
        assert missing == [], f"{missing} are in the roster but not in pre-push."


def _flatten(entry: dict[str, Any]) -> list[dict[str, Any]]:
    group = entry.get("group")
    if not isinstance(group, dict):
        return [entry]
    out: list[dict[str, Any]] = []
    for job in group.get("jobs", []):
        if isinstance(job, dict):
            out.extend(_flatten(job))
    return out
