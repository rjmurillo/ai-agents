"""The declared-cost model for `lefthook.yml`, shared by the guards over it.

Not a test module. It holds the scheduling model and nothing that asserts, so
that the three properties built on it fail for their own reasons and land in
their own files: `test_lefthook_declared_budget.py` (the declared sum, held down
by a ceiling and a base-ref ratchet), `test_lefthook_container_bound.py` (no
single child outlives a container), and the model's own unit tests, which live
beside the declared-sum guard because they share its negative control.

The model mirrors lefthook's scheduling semantics, which `ci-scripts.md`
MUST-17 warns must be read from the config rather than inferred from a run
summary:

- the hook's top level is `piped`, so entries run in order: sum them.
- a `parallel: true` group's members overlap: take the max.
- a `piped: true` group's members run in order: sum them.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
LEFTHOOK = REPO_ROOT / "lefthook.yml"

# The declared sum, which `test_lefthook_declared_budget.py` holds down, is the
# worst case on a developer workstation, where a long cap is the right
# protection for a job that has legitimate work to do. It is not the number the
# originating incident is about, and this roster is what the container bound in
# `test_lefthook_container_bound.py` reads instead. A managed container
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
# declared cap, because nothing clamps them.
#
# This roster used to decide that, as a denylist: any job not named here was
# credited with a clamp. Review on PR #5319 named the hole. A job renamed, or
# replaced with a command that does not reach `_run_command`, silently joined
# the clamped side and the model reported a bound nothing enforces. The roster
# promised in its own comment that such a move "shows up as a baseline change",
# and it could not: nothing compared it to the configuration.
#
# `job_cost` now derives the answer from the job's own `run:` string, which is
# where the routing actually lives, so a rename cannot lie to it. The roster
# stays as the readable list and as the assertion's other side:
# `test_the_roster_matches_what_the_config_actually_routes` requires the two to
# agree in both directions, so a job crossing the boundary fails a test that
# names it instead of changing a number quietly. At the time of writing they
# agree exactly, 14 clamped and 20 not.
CONTAINER_UNCLAMPED_JOBS = frozenset(
    {
        "repair-packed-refs",
        "mutation-safety",
        "push-ref-staleness",
        "pre-pr-validation",
        "count-ratchets",
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


_UNITS = {"h": 3600.0, "m": 60.0, "s": 1.0}


def seconds(raw: object) -> float:
    if raw is None:
        return 0.0
    text = str(raw).strip()
    if not text:
        return 0.0
    if text[-1] in _UNITS:
        return float(text[:-1]) * _UNITS[text[-1]]
    return float(text)


# The module that bounds itself in a container. A job whose `run:` invokes it
# is one `git_hook_policy` process, and `main` arms a watchdog at
# CONTAINER_PROCESS_CEILING_SECONDS covering everything that process does.
#
# The earlier justification was weaker and review on PR #5319 said so: matching
# this string proved the job spawns children through `_run_command`, which says
# nothing about the work BETWEEN them. The reviewer's counterexamples were real
# and specific, `changed_from_git` shelling out unbounded before the pytest
# clock starts, and `scan_pushed_heads` discovering paths and materializing a
# tree before its own. Neither was reached by any deadline, so a job could
# exceed the number this model reports for it.
#
# What makes the derivation sound is the watchdog, not the string. The string
# identifies the process; the process bounds itself.
_SELF_BOUNDING_ENTRYPOINT = "git_hook_policy.py"


def routes_through_the_clamp(entry: dict[str, Any]) -> bool:
    """Whether this job runs as a `git_hook_policy` process, which bounds itself."""
    return _SELF_BOUNDING_ENTRYPOINT in str(entry.get("run", ""))


def job_cost(entry: dict[str, Any], clamp: float | None) -> float:
    declared = seconds(entry.get("timeout"))
    if clamp is None or not routes_through_the_clamp(entry):
        return declared
    return min(declared, clamp)


def entry_cost(entry: dict[str, Any], clamp: float | None = None) -> tuple[float, str]:
    """Worst-case seconds for one top-level entry, and the job that sets it.

    ``clamp`` models `git_hook_policy._container_clamped`: when set, every job
    whose cost lives in a subprocess that module spawns is bounded by it.
    """
    group = entry.get("group")
    if not isinstance(group, dict):
        return job_cost(entry, clamp), str(entry.get("name", "<unnamed>"))
    parts = [entry_cost(job, clamp) for job in group.get("jobs", []) if isinstance(job, dict)]
    if not parts:
        return 0.0, "<empty group>"
    if group.get("parallel"):
        return max(parts, key=lambda part: part[0])
    total = sum(cost for cost, _ in parts)
    worst = max(parts, key=lambda part: part[0])[1]
    return total, worst


def declared_budget(
    config: dict[str, Any], hook: str, clamp: float | None = None
) -> tuple[float, list[tuple[float, str]]]:
    entries = [e for e in config[hook]["jobs"] if isinstance(e, dict)]
    rows = [entry_cost(e, clamp) for e in entries]
    return sum(cost for cost, _ in rows), rows


def load_config() -> dict[str, Any]:
    data = yaml.safe_load(LEFTHOOK.read_text(encoding="utf-8"))
    assert isinstance(data, dict), "lefthook.yml must parse to a YAML mapping."
    return data


def flatten(entry: dict[str, Any]) -> list[dict[str, Any]]:
    group = entry.get("group")
    if not isinstance(group, dict):
        return [entry]
    out: list[dict[str, Any]] = []
    for job in group.get("jobs", []):
        if isinstance(job, dict):
            out.extend(flatten(job))
    return out
