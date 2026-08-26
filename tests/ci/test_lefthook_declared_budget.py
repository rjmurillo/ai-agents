"""The declared worst case of each git hook, held down two different ways.

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

The scheduling model these totals come from lives in `lefthook_budget_model.py`
alongside the reason it has to be read from the config rather than inferred from
a run summary. Its unit tests are at the bottom of this module, because they
share a negative control with the ceiling below.

Two guards, because neither alone is a ratchet:

- a hard ceiling, `DECLARED_BUDGET_BASELINE_SECONDS`, which runs anywhere and
  needs no git. It is not a ratchet: the number lives beside the assertion, so
  one edit can raise a cap and the ceiling together. Review on PR #5319 said so.
- the ratchet proper, which recomputes the same model from `lefthook.yml` as of
  the base ref and requires the current total not to rise against it. Its
  baseline is git history, which the branch under test cannot edit. It needs the
  base ref present, so it runs on pre-push (where the count ratchets already
  read `origin/main`) and skips on a shallow CI checkout, leaving the ceiling as
  the only guard there. That is a real gap, stated rather than papered over.

Coverage:

- positive: each hook's declared worst case is at or below its ceiling, and at
  or below the same total measured on the base ref.
- negative: raising any cap above the ceiling fails, and the failure names the
  job whose cap dominates its group so the reader knows where to look. Raising
  a cap and the ceiling in one edit fails the base-ref comparison.
- edge: the model is exercised directly on synthetic configs covering a bare
  job, a parallel group, a piped group, and a nested group, so a scheduling
  bug in the model cannot pass by agreeing with itself on the real file.
"""

from __future__ import annotations

import subprocess
from typing import Any

import pytest
import yaml

from scripts.ci import count_ratchet
from tests.ci.lefthook_budget_model import (
    LEFTHOOK,
    REPO_ROOT,
    declared_budget,
    entry_cost,
    load_config,
    seconds,
)

# The measured declared worst case at the time this guard was introduced, not
# aspirations. ADR-104's targets (300s pre-push, 60s pre-commit) are far below
# both; closing that distance means measuring jobs and cutting caps, which is
# issue #5318, not editing these.
#
# This is a CEILING, not the ratchet. It was described as "a ratchet that may
# only fall" until review on PR #5319 pointed out that the number lives beside
# the assertion that reads it, so a future change can raise a timeout and this
# number in the same edit and satisfy both tests here. The ratchet is
# `test_declared_budget_does_not_rise_against_the_base_ref` below, whose
# baseline is `lefthook.yml` as committed on the base ref. Lowering this
# constant stays a one-line edit on purpose; raising it does not get past the
# base-ref comparison wherever that ref is reachable.
#
# pre-push 3450s is dominated by three blocks nobody has measured while firing:
# the two CLI e2e smokes at 20m (they set the expensive group's cost),
# `workflow-local-run` at 30m, and `security-scan` at 15m, which ADR-054 sets
# as an enforced 900s budget this record does not overturn. On a workstation a
# long cap for those is the right protection; the container bound elsewhere is
# what the originating incident is about.
#
# It read 2850 until review put `workflow-local-run` back at main's 30m. That
# cut was the one cap on this branch with no in-hook measurement behind it, and
# ADR-104 rule 7 says a cap is sized from a measured worst case. Raising a
# ceiling to accommodate a restored cap is the honest direction here and the
# base-ref ratchet still holds: 3450s is below the 4170s on the base ref, so
# the total has fallen, just by less than an unmeasured cut made it look.
DECLARED_BUDGET_BASELINE_SECONDS: dict[str, float] = {
    "pre-push": 3450.0,
    "pre-commit": 6530.0,
}

# The order the count ratchets use. They are handed `--base-ref origin/main` by
# lefthook, so on a workstation and inside the pre-push hook that ref usually
# exists. It is NOT guaranteed current: nothing in this hook fetches, so
# `origin/main` is whatever the last fetch left behind. A stale base ref makes
# this ratchet weaker, never stricter, because the comparison is against a
# total that may be higher than main's real one, so a reduction on main can go
# unrecorded here until something fetches. `ci-scripts.md` item 14 records the
# opposite direction biting the count ratchets, where a stale base produced a
# phantom regression; this comparison has no such failure mode, which is why
# the staleness is stated rather than fixed by fetching inside a hook.
# `main` is the fallback for a clone that tracks it locally without a remote of
# that name.
_BASE_REF_CANDIDATES = ("origin/main", "main")


def _config_at_ref(ref: str) -> dict[str, Any] | None:
    """`lefthook.yml` as committed at `ref`, or None when it cannot be read.

    Runs under `count_ratchet.git_environment()` rather than the ambient one.
    A `git push` from a linked worktree exports `GIT_DIR` into the pre-push
    hook, and an exported `GIT_DIR` outranks `-C <root>`, so the ambient
    environment would read the pushing worktree's object store instead of this
    checkout's (issue #4914). This test runs inside that hook.
    """
    try:
        proc = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "show", f"{ref}:lefthook.yml"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            env=count_ratchet.git_environment(),
        )
    except OSError:
        return None
    if proc.returncode != 0:
        return None
    data = yaml.safe_load(proc.stdout)
    return data if isinstance(data, dict) else None


def _baseconfig() -> tuple[str, dict[str, Any]] | None:
    """The first reachable base ref and its `lefthook.yml`, or None."""
    for ref in _BASE_REF_CANDIDATES:
        config = _config_at_ref(ref)
        if config is not None:
            return ref, config
    return None


def _hook_is_present(config: dict[str, Any], hook: str) -> bool:
    hook_config = config.get(hook)
    return isinstance(hook_config, dict) and isinstance(hook_config.get("jobs"), list)


def _ratchet_failure(
    hook: str, current: tuple[float, list[tuple[float, str]]], base_total: float, ref: str
) -> str | None:
    """Message naming the rise, or None when the declared total did not rise.

    Extracted so the control below can drive it with a doctored config. A guard
    whose predicate only ever runs on the real file is a guard nobody has seen
    fail, which is how this module shipped a ceiling described as a ratchet.
    """
    total, rows = current
    if total <= base_total:
        return None
    worst = ", ".join(f"{cost:.0f}s {name}" for cost, name in sorted(rows, reverse=True)[:3])
    return (
        f"{hook} declared worst case rose from {base_total:.0f}s on {ref} to "
        f"{total:.0f}s. Largest contributors here: {worst}. This is the ratchet, "
        "and its baseline is the committed config on the base ref, so raising "
        "DECLARED_BUDGET_BASELINE_SECONDS in the same edit does not clear it. "
        "Cut a cap to fit, or measure the job during a real push "
        "(ci-scripts.md MUST-16) and cut something else to pay for it."
    )


@pytest.mark.parametrize("hook", sorted(DECLARED_BUDGET_BASELINE_SECONDS))
def test_declared_budget_is_at_or_below_its_baseline(hook: str) -> None:
    baseline = DECLARED_BUDGET_BASELINE_SECONDS[hook]
    total, rows = declared_budget(load_config(), hook)
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
    """A ceiling far above the real number stops holding anything down.

    Kept loose (10%) because caps are sized for a loaded machine, not for the
    current total. It only catches a ceiling lowered carelessly or a cap cut
    that nobody folded back in.
    """
    baseline = DECLARED_BUDGET_BASELINE_SECONDS[hook]
    total, _ = declared_budget(load_config(), hook)
    assert total >= baseline * 0.9, (
        f"{hook} declared worst case is {total:.0f}s, well under its "
        f"{baseline:.0f}s ceiling. Lower the ceiling to {total:.0f}s so it "
        "keeps its grip."
    )


@pytest.mark.parametrize("hook", sorted(DECLARED_BUDGET_BASELINE_SECONDS))
def test_declared_budget_does_not_rise_against_the_base_ref(hook: str) -> None:
    """The ratchet proper: the baseline is git history, not a line in this file.

    The two tests above read `DECLARED_BUDGET_BASELINE_SECONDS`, which sits
    twenty lines from the assertions that compare against it. Review on PR #5319
    named the consequence: a change that raises a job's timeout and raises that
    number in the same edit satisfies both, so what looked like a ratchet was a
    ceiling that moves with whoever is editing it.

    Here the baseline is the same model recomputed from `lefthook.yml` as
    committed on the base ref, which the branch under test cannot edit. Falling
    is free; rising has to be argued for in review, because there is nothing to
    edit that would make this pass.

    Skips when no base ref is reachable, which is a shallow CI checkout rather
    than a workstation or the pre-push hook. The ceiling still runs there.
    """
    found = _baseconfig()
    if found is None:
        pytest.skip(
            f"none of {_BASE_REF_CANDIDATES} is reachable, so there is no "
            "committed baseline to ratchet against. Expected on a shallow "
            "checkout; DECLARED_BUDGET_BASELINE_SECONDS is the only guard here."
        )
    ref, base_config = found
    if not _hook_is_present(base_config, hook):
        pytest.skip(f"{ref} declares no {hook} jobs, so there is nothing to compare.")

    base_total, _ = declared_budget(base_config, hook)
    failure = _ratchet_failure(hook, declared_budget(load_config(), hook), base_total, ref)
    assert failure is None, failure


def test_the_ratchet_catches_a_cap_raised_on_this_branch() -> None:
    """Negative control: bump one real cap and the predicate names the rise.

    Drives `_ratchet_failure` with the committed config as the baseline and a
    doctored copy as the branch, which is the shape of the change the ratchet
    exists to stop. Without this the predicate would only ever be observed
    returning None, and a comparison nobody has watched fail is the defect this
    whole module keeps rediscovering.
    """
    hook = "pre-push"
    config = load_config()
    base_total, _ = declared_budget(config, hook)

    doctored = yaml.safe_load(LEFTHOOK.read_text(encoding="utf-8"))
    first = next(job for job in doctored[hook]["jobs"] if "timeout" in job)
    raised = seconds(first["timeout"]) + 60.0
    first["timeout"] = f"{raised:.0f}s"

    doctored_total, _ = declared_budget(doctored, hook)
    failure = _ratchet_failure(hook, (doctored_total, []), base_total, "origin/main")
    assert failure is not None, (
        f"raising {first['name']!r} by 60s did not trip the ratchet. The "
        "comparison does not discriminate, so the ratchet test above passes "
        "for a reason other than the declared total holding."
    )
    # Both numbers, not a phrase the message always carries. An earlier version
    # asserted `name in failure or "rose from" in failure`, and every non-None
    # `_ratchet_failure` contains "rose from", so the disjunction could not
    # fail and said nothing about whether the message described THIS mutation.
    # Review on PR #5319; same shape as the other vacuous controls this branch
    # has found, in a control written to close one of them.
    assert f"{base_total:.0f}s" in failure and f"{doctored_total:.0f}s" in failure, (
        f"the failure names neither total. Expected {base_total:.0f}s and "
        f"{doctored_total:.0f}s in: {failure!r}"
    )
    assert doctored_total > base_total, (
        "the doctored config did not actually raise the declared total, so the "
        "message above is about something other than the mutation."
    )


class TestTheModelMatchesLefthookScheduling:
    """Exercised on synthetic configs, so it cannot pass by agreeing with itself."""

    def test_a_bare_job_costs_its_own_timeout(self) -> None:
        cost, name = entry_cost({"name": "solo", "timeout": "90s"})
        assert (cost, name) == (90.0, "solo")

    def test_a_parallel_group_costs_its_slowest_member(self) -> None:
        cost, name = entry_cost(
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
        cost, name = entry_cost(
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
        cost, _ = entry_cost(
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
        assert seconds(raw) == expected

    def test_a_raised_cap_breaks_the_budget(self) -> None:
        """Negative control for the ratchet itself.

        Without this, `test_declared_budget_is_at_or_below_its_baseline` passing
        says nothing about whether it could ever fail.
        """
        config = load_config()
        before, _ = declared_budget(config, "pre-push")
        for entry in config["pre-push"]["jobs"]:
            if isinstance(entry, dict) and entry.get("name") == "security-scan":
                entry["timeout"] = "99h"
                break
        else:  # pragma: no cover - the job is asserted to exist below
            pytest.fail("security-scan is missing from pre-push.")
        after, _ = declared_budget(config, "pre-push")
        assert after > before
        assert after > DECLARED_BUDGET_BASELINE_SECONDS["pre-push"]
