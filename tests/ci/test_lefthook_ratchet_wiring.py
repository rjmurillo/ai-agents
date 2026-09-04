"""Ratchet registry and aggregate pre-push wiring tests (issues #4041, #5317)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
_LEFTHOOK = REPO_ROOT / "lefthook.yml"
_VALIDATION_DIR = REPO_ROOT / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))
import checks_ratchet  # noqa: E402


def _walk_jobs(jobs: object) -> list[dict]:
    if not isinstance(jobs, list):
        return []
    found: list[dict] = []
    for job in jobs:
        if not isinstance(job, dict):
            continue
        found.append(job)
        group = job.get("group")
        if isinstance(group, dict):
            found.extend(_walk_jobs(group.get("jobs")))
    return found


def _aggregate_job() -> dict | None:
    config = yaml.safe_load(_LEFTHOOK.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        return None
    pre_push = config.get("pre-push")
    if not isinstance(pre_push, dict):
        return None
    return next(
        (job for job in _walk_jobs(pre_push.get("jobs")) if job.get("name") == "count-ratchets"),
        None,
    )


class TestAggregateRatchetWiring:
    def test_job_invokes_the_authoritative_registry(self) -> None:
        job = _aggregate_job()
        assert job is not None
        assert str(job.get("run")) == (
            "uv run --frozen python scripts/validation/checks_ratchet.py"
        )

    def test_job_runs_for_every_push(self) -> None:
        job = _aggregate_job()
        assert job is not None
        assert job.get("glob") is None

    def test_registry_retains_taste_and_type_ignore_ratchets(self) -> None:
        by_name = {ratchet.job_name: ratchet for ratchet in checks_ratchet.RATCHETS}
        assert by_name["taste-count-ratchet"].script == (
            "scripts/ci/taste_count_ratchet.py"
        )
        assert by_name["type-ignore-count-ratchet"].script == (
            "scripts/ci/type_ignore_count_ratchet.py"
        )

    def test_registry_retains_every_consolidated_ratchet(self) -> None:
        """Floor against silent deletion, by name rather than by count.

        This was `len(RATCHETS) == 8`. A bare count also fails on an addition,
        which is not the loss it exists to catch, and it names nothing when it
        does fail. The exact registry contents, additions included, are pinned
        by `_EXPECTED_RATCHETS` in test_pre_pr_runs_lefthook_ratchets.py, so
        this one only has to hold the floor.
        """
        consolidated = {
            "python-lint-ratchet",
            "python-lint-count-ratchet",
            "taste-count-ratchet",
            "type-ignore-count-ratchet",
            "memory-index-count-ratchet",
            "cli-exit-contract-ratchet",
            "memory-index-token-ratchet",
            "merge-tree-ratchet",
        }
        registered = {ratchet.job_name for ratchet in checks_ratchet.RATCHETS}

        assert consolidated <= registered, consolidated - registered

    def test_base_ref_contracts_stay_explicit(self) -> None:
        by_name = {ratchet.job_name: ratchet for ratchet in checks_ratchet.RATCHETS}
        assert by_name["taste-count-ratchet"].uses_base_ref is True
        assert by_name["type-ignore-count-ratchet"].uses_base_ref is True


class TestAggregateBudgetIsConsistentWithLefthook:
    """The gate's own deadline must fire before lefthook kills the job (#5482).

    If lefthook's timeout were the smaller of the two, it would kill the gate
    mid-run with no attribution: the operator sees the job fail and not which
    ratchet was responsible. The gate's deadline fires first precisely so the
    failure names the offending entry.
    """

    def _count_ratchets_timeout_seconds(self) -> int:
        config = yaml.safe_load((REPO_ROOT / "lefthook.yml").read_text(encoding="utf-8"))
        found: list[str] = []

        def walk(node: object) -> None:
            if isinstance(node, dict):
                if node.get("name") == "count-ratchets":
                    found.append(str(node.get("timeout", "")))
                for value in node.values():
                    walk(value)
            elif isinstance(node, list):
                for item in node:
                    walk(item)

        walk(config)
        assert len(found) == 1, f"expected one count-ratchets job, found {found}"
        return int(found[0].removesuffix("s"))

    def test_lefthook_allows_more_time_than_the_aggregate_deadline(self) -> None:
        assert (
            self._count_ratchets_timeout_seconds()
            > checks_ratchet._AGGREGATE_TIMEOUT_SECONDS
        )

    def test_the_module_declares_the_lefthook_budget_it_assumes(self) -> None:
        """Keep the two numbers from drifting apart silently."""
        assert (
            checks_ratchet._LEFTHOOK_TIMEOUT_SECONDS
            == self._count_ratchets_timeout_seconds()
        )


def ci_baseline_ratchet_scripts() -> list[str]:
    """Every count ratchet that owns a baseline under ``scripts/ci``.

    Derived from the baseline files rather than a hand-written list, so the
    next ratchet is covered on the day its baseline lands. The name mapping is
    the repository's own convention, ``<name>_baseline.txt`` beside
    ``<name>_ratchet.py``; a module that breaks it is caught by
    ``test_every_derived_ratchet_script_exists`` rather than silently dropping
    out of the inventory.
    """
    ci_dir = REPO_ROOT / "scripts" / "ci"
    return sorted(
        f"scripts/ci/{path.name.removesuffix('_baseline.txt')}_ratchet.py"
        for path in ci_dir.glob("*_baseline.txt")
    )


def unregistered_ratchet_scripts(registered: set[str]) -> list[str]:
    """Baseline-owning ratchets that no local registry entry runs."""
    return [script for script in ci_baseline_ratchet_scripts() if script not in registered]


class TestEveryCountRatchetIsGatedLocally:
    """A ratchet enforced only in CI costs a push and a full CI cycle (#5482).

    ``subprocess_encoding_count_ratchet.py`` ran in
    ``.github/workflows/pytest.yml`` and in no local gate, so a violation in
    any of the 1729 tracked Python files outside ``scripts/`` passed
    pre-commit, pre-push, and ``pre_pr.py``, then failed CI. Measured live on
    PR #5476.

    Coverage: positive, every baseline-owning ratchet is in the local
    registry; negative, dropping one from the registry is reported by name,
    which is the pre-fix state; edge, the inventory is non-empty and every
    derived script exists, so the check cannot pass vacuously.
    """

    def test_every_baseline_owning_ratchet_runs_in_the_local_registry(self) -> None:
        registered = {ratchet.script for ratchet in checks_ratchet.RATCHETS}
        missing = unregistered_ratchet_scripts(registered)

        assert not missing, (
            f"count ratchet(s) enforced in CI and in no local gate: {missing}. "
            f"Add a Ratchet(...) entry in scripts/validation/checks_ratchet.py."
        )

    def test_dropping_a_ratchet_from_the_registry_is_reported(self) -> None:
        """Negative control: the pre-fix registry, which omitted this one."""
        target = "scripts/ci/subprocess_encoding_count_ratchet.py"
        pre_fix = {
            ratchet.script for ratchet in checks_ratchet.RATCHETS
        } - {target}

        assert unregistered_ratchet_scripts(pre_fix) == [target]

    def test_the_inventory_is_not_empty(self) -> None:
        """Edge: a glob that matched nothing would make the check vacuous."""
        assert ci_baseline_ratchet_scripts()

    def test_every_derived_ratchet_script_exists(self) -> None:
        """Edge: a baseline whose module breaks the naming convention fails here."""
        missing = [
            script
            for script in ci_baseline_ratchet_scripts()
            if not (REPO_ROOT / script).is_file()
        ]

        assert not missing, (
            f"baseline file(s) with no matching *_ratchet.py module: {missing}. "
            f"Fix the name, or teach ci_baseline_ratchet_scripts the mapping."
        )


def spawned_scripts(monkeypatch: pytest.MonkeyPatch, *, skip: str | None = None) -> list[str]:
    """Every ratchet script one ``validate_count_ratchets`` run launches.

    Reads the argv the gate hands ``_run_subprocess`` rather than the registry
    it was built from. A declaration the gate never launches is the failure
    this helper exists to see, and a registry-derived expectation cannot see it.
    Duplicates are kept so a script launched twice is visible too.

    ``skip`` drops one script from the recorded list while still returning an OK
    result for it, which models a gate that declares an entry and never spawns
    it. It leaves ``RATCHETS`` untouched on purpose: removing the entry from the
    registry would move the declared set and the launched set together, and the
    regression under test is the two disagreeing.
    """
    launched: list[str] = []

    def record(args: list[str], **_kwargs: object) -> tuple[int, str, str]:
        script = args[args.index("python") + 1]
        if script != skip:
            launched.append(script)
        return 0, "", ""

    monkeypatch.setattr(
        checks_ratchet, "_resolve_default_base_ref", lambda _root: "origin/main"
    )
    monkeypatch.setattr(checks_ratchet, "_refresh_remote_base", lambda *_a: "")
    monkeypatch.setattr(checks_ratchet, "_resolve_base_oid", lambda *_a: "a" * 40)
    monkeypatch.setattr(checks_ratchet, "_run_subprocess", record)
    assert checks_ratchet.validate_count_ratchets(REPO_ROOT) is True
    return launched


class TestEveryDeclaredRatchetIsLaunched:
    """Declaring a ratchet is not running it (issues #5482, #5510).

    Issue #5510 asked for the five counters ``merge_tree_ratchet_check.py``
    also runs to stop being launched here, on the reading that the merged-tree
    pass makes the standalone run redundant. It does not.
    ``count_ratchet.py::_base_ref_verdict`` states the opposite in its own
    words, "this check reads the fork point, which the merge-tree gate never
    does, and it evaluates the branch's own tree rather than the merged one.
    Neither subsumes the other." Two verdict classes are the difference, and
    both were probed against the real code: with base 575, merged baseline 615
    and count 575, ``merge_tree_ratchet_check._check_one`` returns
    ``(0, 'taste count ratchet: OK. 575 <= 575.')`` where the standalone run
    exits 1 with BASELINE ABOVE BASE; with baseline 130 over a tree of 118 it
    returns OK where ``count_ratchet.baseline_health`` reports a stale
    baseline. Dropping those launches leaves both classes enforced in CI and
    in no local gate, which is the #5482 defect this same change set repairs.

    Coverage: positive, every declared entry and every baseline-owning ratchet
    is launched; negative, an entry the gate skips is reported by name; edge,
    no script is launched twice, so the assertion cannot pass on a duplicate.
    """

    def test_every_declared_ratchet_is_launched(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        launched = spawned_scripts(monkeypatch)
        declared = [ratchet.script for ratchet in checks_ratchet.RATCHETS]

        assert sorted(launched) == sorted(declared)

    def test_every_baseline_owning_ratchet_is_launched(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        launched = set(spawned_scripts(monkeypatch))
        missing = [s for s in ci_baseline_ratchet_scripts() if s not in launched]

        assert not missing, (
            f"count ratchet(s) declared but never launched: {missing}. "
            f"A declaration no gate runs is enforcement in CI only."
        )

    def test_a_skipped_entry_is_reported(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Negative control: the gate declares the entry and never launches it.

        The entry stays in ``RATCHETS``. Only the spawn is suppressed, so the
        declared set and the launched set disagree by exactly one script, which
        is the shape ``test_every_baseline_owning_ratchet_is_launched`` exists
        to catch.
        """
        target = "scripts/ci/taste_count_ratchet.py"
        assert target in [r.script for r in checks_ratchet.RATCHETS], (
            f"{target} must stay declared for this control to model "
            f"declared-but-never-launched"
        )
        launched = set(spawned_scripts(monkeypatch, skip=target))

        assert [s for s in ci_baseline_ratchet_scripts() if s not in launched] == [
            target
        ]

    def test_no_script_is_launched_twice(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Edge: one process per entry, so the set comparison cannot hide one."""
        launched = spawned_scripts(monkeypatch)

        assert sorted({s for s in launched if launched.count(s) > 1}) == []
