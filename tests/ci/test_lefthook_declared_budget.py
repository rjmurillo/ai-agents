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
# pre-push 2610s is dominated by two blocks nobody has measured while firing:
# the two CLI e2e smokes at 20m (group max) and `security-scan` at 15m, which
# ADR-054 sets as an enforced 900s budget this record does not overturn.
DECLARED_BUDGET_BASELINE_SECONDS: dict[str, float] = {
    "pre-push": 2610.0,
    "pre-commit": 6570.0,
}

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


def _entry_cost(entry: dict[str, Any]) -> tuple[float, str]:
    """Worst-case seconds for one top-level entry, and the job that sets it."""
    group = entry.get("group")
    if not isinstance(group, dict):
        return _seconds(entry.get("timeout")), str(entry.get("name", "<unnamed>"))
    parts = [
        _entry_cost(job) for job in group.get("jobs", []) if isinstance(job, dict)
    ]
    if not parts:
        return 0.0, "<empty group>"
    if group.get("parallel"):
        return max(parts, key=lambda part: part[0])
    total = sum(cost for cost, _ in parts)
    worst = max(parts, key=lambda part: part[0])[1]
    return total, worst


def _declared_budget(config: dict[str, Any], hook: str) -> tuple[float, list[tuple[float, str]]]:
    entries = [e for e in config[hook]["jobs"] if isinstance(e, dict)]
    rows = [_entry_cost(e) for e in entries]
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
