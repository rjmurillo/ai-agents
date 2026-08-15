"""Fast-fail staging tests for the pre-push hook (issue #5066).

The pre-push hook declares ``piped: true``, so lefthook runs its top-level
entries in order and a failing entry (job or group) skips everything after
it. Issue #5066 leans on that to stage the hook: cheap blocking gates run
first, the expensive jobs (python-tests at roughly twelve minutes,
workflow-local-run, build-all-check, python-type-check, the e2e smokes,
pre-pr-validation) run last, so a failure that is detectable in seconds never
costs a full pytest run.

Structural tests parse ``lefthook.yml`` and assert on the object graph
(testing.md MUST 9: never substring a structured file). The runtime
counterpart lives in ``test_lefthook_prepush_fast_fail_runtime.py``, which
drives the real lefthook binary against a fixture repository to pin the
scheduling semantics the staging relies on.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
_LEFTHOOK = _REPO_ROOT / "lefthook.yml"

# The fast stage: every blocking gate that must fail before the expensive
# stage starts. The stdin gates sit in the piped group; the rest sit in the
# fast parallel group.
FAST_STDIN_GATES = (
    "push-ref-policy",
    "security-suppression-policy",
    "placeholder-identity",
    "session-json-validation",
)
FAST_PARALLEL_GATES = frozenset(
    {
        "retrospective-policy",
        "python-lint-ratchet",
        "python-lint-count-ratchet",
        "taste-count-ratchet",
        "type-ignore-count-ratchet",
        "memory-index-count-ratchet",
        "cli-exit-contract-ratchet",
        "memory-index-token-ratchet",
        "python-unreachable-statements",
        "merge-tree-ratchet",
        "path-normalization",
        "planning-artifacts",
        "branch-scope",
        "branch-context-policy",
        "review-axis-drift",
    }
)

# The expensive stage: nothing here may start until every fast gate passed.
# EXPENSIVE_JOBS are the blocking heavyweights the ordering tests quantify
# over; EXPENSIVE_STAGE_ROSTER is the exact membership of the expensive
# parallel group, advisories included, so adding any pre-push job anywhere
# requires editing a roster in this module.
EXPENSIVE_JOBS = frozenset(
    {
        "pre-pr-validation",
        "python-tests",
        "python-type-check",
        "workflow-local-run",
        "build-all-check",
        "hook-anchoring-e2e",
        "plugin-load-e2e",
    }
)
EXPENSIVE_STAGE_ROSTER = EXPENSIVE_JOBS | frozenset(
    {
        "worktree-gc-report",
        "python-lint-advisory",
        "infrastructure-advisory",
        "additions-advisory",
        "observation-sync-advisory",
        "bot-cascade-advisory",
    }
)

# Pre-#5066 exception, preserved as-is: these two carry `use_stdin: true`
# inside the expensive `parallel: true` group. They predate MUST-21 and only
# use the payload to derive the changed-file range. Do not grow this set; a
# new stdin consumer belongs in the piped group or at the top level.
PARALLEL_STDIN_EXCEPTIONS = frozenset({"hook-anchoring-e2e", "plugin-load-e2e"})

# Ceilings for jobs scheduled ahead of the expensive stage, set to the
# largest cap each stage half already carries (session-json-validation holds
# 10m in the piped stdin group; every fast parallel gate holds 5m or less).
# Job caps are sized for a loaded machine (ci-scripts.md MUST-16), so the
# ceiling pins "no slower job class enters the fast stage" rather than the
# stage's 60s wall-clock target, which caps cannot express.
_FAST_STDIN_TIMEOUT_CEILING_SECONDS = 600.0
_FAST_PARALLEL_TIMEOUT_CEILING_SECONDS = 300.0


def _load_config(path: Path = _LEFTHOOK) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict), "lefthook.yml must parse to a YAML mapping."
    return data


def _top_level_entries(config: dict[str, Any]) -> list[dict[str, Any]]:
    pre_push = config.get("pre-push")
    assert isinstance(pre_push, dict), "config must declare a pre-push mapping."
    jobs = pre_push.get("jobs")
    assert isinstance(jobs, list), "pre-push must declare a jobs list."
    return [entry for entry in jobs if isinstance(entry, dict)]


def _jobs_in_entry(entry: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the job mappings a top-level entry schedules, groups descended."""
    group = entry.get("group")
    if not isinstance(group, dict):
        return [entry]
    out: list[dict[str, Any]] = []
    for job in group.get("jobs", []):
        if isinstance(job, dict):
            out.extend(_jobs_in_entry(job))
    return out


def _entry_index_of(config: dict[str, Any], job_name: str) -> int | None:
    """Return the top-level position of the entry that schedules ``job_name``."""
    for index, entry in enumerate(_top_level_entries(config)):
        if any(job.get("name") == job_name for job in _jobs_in_entry(entry)):
            return index
    return None


def _duration_seconds(value: str) -> float:
    units = {"h": 3600.0, "m": 60.0, "s": 1.0}
    if value and value[-1] in units:
        return float(value[:-1]) * units[value[-1]]
    return float(value)


class TestStageOrdering:
    """Every fast gate must be scheduled before every expensive job."""

    def test_pre_push_hook_is_piped(self) -> None:
        # The staging only fails fast because the hook is piped; flipping
        # this to parallel would run both stages at once.
        config = _load_config()
        assert config["pre-push"].get("piped") is True

    @pytest.mark.parametrize("gate", sorted(FAST_PARALLEL_GATES) + list(FAST_STDIN_GATES))
    def test_fast_gate_exists_and_precedes_the_expensive_stage(self, gate: str) -> None:
        config = _load_config()
        gate_index = _entry_index_of(config, gate)
        assert gate_index is not None, (
            f"Fast gate {gate!r} is missing from pre-push. If it was renamed "
            "or removed on purpose, update this test's stage roster."
        )
        for expensive in sorted(EXPENSIVE_JOBS):
            expensive_index = _entry_index_of(config, expensive)
            assert expensive_index is not None, f"{expensive!r} missing from pre-push."
            assert gate_index < expensive_index, (
                f"{gate!r} (entry {gate_index}) no longer precedes "
                f"{expensive!r} (entry {expensive_index}). A cheap failure "
                "would again surface only after the expensive jobs burned "
                "(issue #5066)."
            )

    def test_security_scan_sits_between_the_stages(self) -> None:
        config = _load_config()
        scan_index = _entry_index_of(config, "security-scan")
        assert scan_index is not None, "security-scan missing from pre-push."
        for gate in FAST_PARALLEL_GATES | set(FAST_STDIN_GATES):
            gate_index = _entry_index_of(config, gate)
            assert gate_index is not None and gate_index < scan_index, (
                f"{gate!r} must precede security-scan so a cheap failure "
                "skips the semgrep scan."
            )
        for expensive in EXPENSIVE_JOBS:
            expensive_index = _entry_index_of(config, expensive)
            assert expensive_index is not None and scan_index < expensive_index, (
                f"security-scan must precede {expensive!r}; it consumes stdin "
                "and MUST-21 keeps it out of the parallel group."
            )

    def test_expensive_jobs_share_one_parallel_group(self) -> None:
        config = _load_config()
        indices = {_entry_index_of(config, name) for name in EXPENSIVE_JOBS}
        found = sorted(i for i in indices if i is not None)
        assert len(indices) == 1, (
            f"The expensive jobs spread across entries {found}; they are "
            "meant to run concurrently in a single parallel group."
        )
        (index,) = indices
        assert index is not None
        entry = _top_level_entries(config)[index]
        group = entry.get("group")
        assert isinstance(group, dict) and group.get("parallel") is True

    def test_detector_flags_a_fast_gate_scheduled_after_the_expensive_stage(self) -> None:
        # Negative control: the index comparison must actually invert on a
        # misordered config, or every assertion above is vacuous.
        misordered = yaml.safe_load(
            """
            pre-push:
              jobs:
                - group:
                    parallel: true
                    jobs:
                      - name: python-tests
                        run: pytest
                - name: taste-count-ratchet
                  run: ratchet
            """
        )
        gate = _entry_index_of(misordered, "taste-count-ratchet")
        expensive = _entry_index_of(misordered, "python-tests")
        assert gate is not None and expensive is not None
        assert not gate < expensive

    def test_entry_index_returns_none_for_an_unknown_job(self) -> None:
        assert _entry_index_of(_load_config(), "no-such-job") is None

    def test_entry_index_rejects_a_config_without_pre_push(self) -> None:
        with pytest.raises(AssertionError, match="pre-push"):
            _entry_index_of({"pre-commit": {"jobs": []}}, "python-tests")


class TestStdinPlacement:
    """ci-scripts.md MUST-21: stdin consumers stay serialized."""

    def test_no_new_stdin_job_inside_a_parallel_group(self) -> None:
        config = _load_config()
        offenders: list[str] = []
        for entry in _top_level_entries(config):
            group = entry.get("group")
            if not isinstance(group, dict) or group.get("parallel") is not True:
                continue
            for job in _jobs_in_entry(entry):
                name = str(job.get("name"))
                if job.get("use_stdin") is True and name not in PARALLEL_STDIN_EXCEPTIONS:
                    offenders.append(name)
        assert offenders == [], (
            f"{offenders} declare use_stdin inside a parallel group. Parallel "
            "stdin consumers race the shared stream and can read a truncated "
            "payload (ci-scripts.md MUST-21). Put the job in the piped group "
            "or at the top level of the piped hook."
        )

    def test_the_documented_exceptions_still_carry_use_stdin(self) -> None:
        # If either e2e job stops reading stdin, the exception list above is
        # stale and should shrink rather than silently over-allow.
        config = _load_config()
        for name in sorted(PARALLEL_STDIN_EXCEPTIONS):
            index = _entry_index_of(config, name)
            assert index is not None, f"{name!r} missing from pre-push."
            entry = _top_level_entries(config)[index]
            job = next(j for j in _jobs_in_entry(entry) if j.get("name") == name)
            assert job.get("use_stdin") is True, (
                f"{name!r} no longer reads stdin; remove it from "
                "PARALLEL_STDIN_EXCEPTIONS."
            )

    def test_security_scan_is_a_top_level_stdin_job(self) -> None:
        config = _load_config()
        entries = _top_level_entries(config)
        matches = [
            entry
            for entry in entries
            if "group" not in entry and entry.get("name") == "security-scan"
        ]
        assert len(matches) == 1, (
            "security-scan must be a top-level job of the piped hook: that "
            "serializes its stdin delivery (MUST-21) while letting the fast "
            "stage fail without waiting on semgrep."
        )
        assert matches[0].get("use_stdin") is True

    def test_detector_flags_a_stdin_job_added_to_a_parallel_group(self) -> None:
        # Negative control for the offender scan above.
        bad = yaml.safe_load(
            """
            pre-push:
              jobs:
                - group:
                    parallel: true
                    jobs:
                      - name: new-scanner
                        run: scan
                        use_stdin: true
            """
        )
        offenders = [
            str(job.get("name"))
            for entry in _top_level_entries(bad)
            if isinstance(entry.get("group"), dict)
            and entry["group"].get("parallel") is True
            for job in _jobs_in_entry(entry)
            if job.get("use_stdin") is True
            and str(job.get("name")) not in PARALLEL_STDIN_EXCEPTIONS
        ]
        assert offenders == ["new-scanner"]


class TestFastStageStaysFast:
    """No job ahead of the expensive stage may carry an expensive timeout."""

    def test_every_pre_expensive_job_fits_the_fast_ceiling(self) -> None:
        config = _load_config()
        entries = _top_level_entries(config)
        scan_index = _entry_index_of(config, "security-scan")
        assert scan_index is not None
        offenders = []
        for entry in entries[:scan_index]:
            group = entry.get("group")
            is_parallel = isinstance(group, dict) and group.get("parallel") is True
            ceiling = (
                _FAST_PARALLEL_TIMEOUT_CEILING_SECONDS
                if is_parallel
                else _FAST_STDIN_TIMEOUT_CEILING_SECONDS
            )
            for job in _jobs_in_entry(entry):
                if _duration_seconds(str(job.get("timeout"))) > ceiling:
                    offenders.append((str(job.get("name")), str(job.get("timeout"))))
        assert offenders == [], (
            f"{offenders} sit ahead of security-scan with timeouts above their "
            "stage-half ceiling (5m for the fast parallel group, 10m for the "
            "piped stdin group). The fast stage exists so failures surface in "
            "seconds; move slow jobs into the expensive group (issue #5066)."
        )

    def test_duration_parser_handles_each_unit(self) -> None:
        assert _duration_seconds("30s") == 30.0
        assert _duration_seconds("5m") == 300.0
        assert _duration_seconds("1h") == 3600.0


class TestFastStageMembershipIsExact:
    """The stage rosters are two-way pins (spec-validation gap, PR #5083).

    Relative-order tests alone let a *new* cheap blocking gate land in the
    expensive group unnoticed, silently rebuilding the serialization point.
    Exact membership forces every added, removed, or moved pre-push job
    through a conscious roster decision in this module.
    """

    def test_fast_parallel_group_membership_matches_the_roster(self) -> None:
        config = _load_config()
        entries = _top_level_entries(config)
        scan_index = _entry_index_of(config, "security-scan")
        assert scan_index is not None
        parallel_groups = [
            entry
            for entry in entries[:scan_index]
            if isinstance(entry.get("group"), dict)
            and entry["group"].get("parallel") is True
        ]
        assert len(parallel_groups) == 1, (
            "Exactly one fast parallel group is expected ahead of "
            f"security-scan; found {len(parallel_groups)}."
        )
        names = {str(job.get("name")) for job in _jobs_in_entry(parallel_groups[0])}
        assert names == set(FAST_PARALLEL_GATES), (
            f"Fast parallel group is {sorted(names)}, roster is "
            f"{sorted(FAST_PARALLEL_GATES)}. Update FAST_PARALLEL_GATES "
            "deliberately when the stage composition changes (issue #5066)."
        )

    def test_fast_stdin_group_membership_matches_the_roster(self) -> None:
        config = _load_config()
        entries = _top_level_entries(config)
        scan_index = _entry_index_of(config, "security-scan")
        assert scan_index is not None
        stdin_groups = [
            entry
            for entry in entries[:scan_index]
            if isinstance(entry.get("group"), dict)
            and entry["group"].get("piped") is True
        ]
        assert len(stdin_groups) == 1
        names = [str(job.get("name")) for job in _jobs_in_entry(stdin_groups[0])]
        assert names == list(FAST_STDIN_GATES), (
            f"Fast stdin group order is {names}, roster is "
            f"{list(FAST_STDIN_GATES)}. Order is part of the pin: the group "
            "is piped, so members run in sequence."
        )

    def test_expensive_group_membership_matches_the_roster(self) -> None:
        # Without this pin, a new job dropped into the expensive group would
        # be auto-accounted and never face a roster decision (flagged by the
        # spec validation on PR #5083).
        config = _load_config()
        entries = _top_level_entries(config)
        scan_index = _entry_index_of(config, "security-scan")
        assert scan_index is not None
        names = {
            str(job.get("name"))
            for entry in entries[scan_index + 1 :]
            for job in _jobs_in_entry(entry)
        }
        assert names == set(EXPENSIVE_STAGE_ROSTER), (
            f"Expensive stage is {sorted(names)}, roster is "
            f"{sorted(EXPENSIVE_STAGE_ROSTER)}. Update EXPENSIVE_STAGE_ROSTER "
            "deliberately: a cheap blocking gate placed here would again "
            "surface only after pytest burned (issue #5066)."
        )

    def test_every_pre_push_job_is_accounted_for_by_exactly_one_stage(self) -> None:
        # The complement pin: with every stage exact-pinned (fast rosters
        # above, EXPENSIVE_STAGE_ROSTER here, singleton guards enumerated), a
        # brand-new pre-push job cannot land anywhere without a roster
        # decision in this module.
        config = _load_config()
        entries = _top_level_entries(config)
        scan_index = _entry_index_of(config, "security-scan")
        assert scan_index is not None
        singleton_guards = {
            str(entry.get("name"))
            for entry in entries[:scan_index]
            if "group" not in entry
        }
        all_names = {
            str(job.get("name"))
            for entry in entries
            for job in _jobs_in_entry(entry)
        }
        accounted = (
            singleton_guards
            | set(FAST_STDIN_GATES)
            | set(FAST_PARALLEL_GATES)
            | {"security-scan"}
            | set(EXPENSIVE_STAGE_ROSTER)
        )
        unaccounted = all_names - accounted
        assert unaccounted == set(), (
            f"{sorted(unaccounted)} are pre-push jobs outside every pinned "
            "stage. Add each to a roster in this module so its scheduling is "
            "a decision, not an accident (issue #5066)."
        )


