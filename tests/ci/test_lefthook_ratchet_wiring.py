"""Ratchet registry and aggregate pre-push wiring tests (issues #4041, #5317)."""

from __future__ import annotations

import subprocess
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

from scripts.ci.ruleset_required_contexts import REQUIRED_CONTEXTS  # noqa: E402
from tests.ci.ratchet_test_helpers import (  # noqa: E402
    ALLOWED_STEP_IF,
    RATCHET_WORKFLOWS,
    ci_owners_of,
)


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


# The last main commit whose pre-push hook still ran the removed jobs (2026-11-27).
_BASE_COMMIT = "d31aa71e60"
# Job name, and the command fragment the job ran at _BASE_COMMIT. The fragment
# catches the same command moved under another job name.
_REMOVED_HOOK_JOBS = (
    ("count-ratchets", "git_hook_policy.py count-ratchets"),
    ("plugin-scanner", "check_plugin_scanner_score.py"),
)


def _pre_push_jobs() -> list[dict]:
    config = yaml.safe_load(_LEFTHOOK.read_text(encoding="utf-8"))
    assert isinstance(config, dict)
    pre_push = config.get("pre-push")
    assert isinstance(pre_push, dict)
    return _walk_jobs(pre_push.get("jobs"))


class TestCountRatchetsAreOwnedByCi:
    """Owner ruling 2026-11-27: CI is the test authority, so pre-push runs no ratchets.

    This inverts the issue #4251 and #5482 contract, which asserted the
    ratchets ran in the local hook. The contract now is: the hook does not run
    them, and every registry entry runs unconditionally in a required CI job.
    """

    @pytest.mark.parametrize(("removed", "command"), _REMOVED_HOOK_JOBS)
    def test_the_pre_push_hook_does_not_run_the_removed_job(
        self, removed: str, command: str
    ) -> None:
        names = {str(job.get("name")) for job in _pre_push_jobs()}
        assert removed not in names
        offenders = [
            str(job.get("name")) for job in _pre_push_jobs() if command in str(job.get("run", ""))
        ]
        assert offenders == []

    @pytest.mark.parametrize(("removed", "command"), _REMOVED_HOOK_JOBS)
    def test_the_command_fragment_matched_the_job_before_removal(
        self, removed: str, command: str
    ) -> None:
        """Negative control: on the base the fragment found the removed job."""
        base = subprocess.run(
            ["git", "show", f"{_BASE_COMMIT}:lefthook.yml"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if base.returncode != 0:
            pytest.skip(f"base commit {_BASE_COMMIT} not in this clone (shallow checkout)")
        jobs = _walk_jobs(yaml.safe_load(base.stdout)["pre-push"]["jobs"])
        assert [str(j.get("name")) for j in jobs if command in str(j.get("run", ""))] == [removed]

    @pytest.mark.parametrize(
        "script", sorted(ratchet.script for ratchet in checks_ratchet.RATCHETS)
    )
    def test_every_registry_script_runs_in_a_required_unconditional_ci_job(
        self, script: str
    ) -> None:
        assert ci_owners_of(script), (
            f"{script} has no required, unconditional CI job in "
            f"{RATCHET_WORKFLOWS}. With the pre-push job removed, nothing "
            "would enforce this ratchet before merge."
        )

    def test_the_owner_check_rejects_an_unknown_script(self) -> None:
        """Negative control: a script no workflow runs has no owner."""
        assert ci_owners_of("scripts/ci/no_such_ratchet.py") == []

    def test_the_owner_check_rejects_a_conditional_step(self) -> None:
        """Negative control: a step-level `if:` other than the allowed one disqualifies."""
        assert ci_owners_of("scripts/ci/ruff_ratchet.py") == ["pytest.yml test"]
        saved = dict(ALLOWED_STEP_IF)
        try:
            ALLOWED_STEP_IF.clear()
            assert ci_owners_of("scripts/ci/ruff_ratchet.py") == []
        finally:
            ALLOWED_STEP_IF.update(saved)

    _FIXTURE = (
        "on: pull_request\n"
        "jobs:\n"
        "  good:\n"
        "    name: {required}\n"
        "    steps:\n"
        "      - run: python3 scripts/ci/fixture_ratchet.py\n"
        "  optional:\n"
        "    name: Not A Required Context\n"
        "    steps:\n"
        "      - run: python3 scripts/ci/fixture_ratchet.py\n"
        "  softjob:\n"
        "    name: {required}\n"
        "    continue-on-error: true\n"
        "    steps:\n"
        "      - run: python3 scripts/ci/fixture_ratchet.py\n"
        "  softstep:\n"
        "    name: {required}\n"
        "    steps:\n"
        "      - run: python3 scripts/ci/fixture_ratchet.py\n"
        "        continue-on-error: ${{{{ github.event_name == 'push' }}}}\n"
    )

    def test_the_owner_check_rejects_unrequired_and_soft_failing_jobs(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Negative control: drive ``ci_owners_of`` on a fixture workflow.

        Of four jobs that run the script, only ``good`` qualifies: ``optional``
        is outside ``REQUIRED_CONTEXTS``, and ``softjob`` and ``softstep`` set
        ``continue-on-error``, so a failure there would not fail the check.
        """
        import tests.ci.ratchet_test_helpers as helpers

        required = sorted(REQUIRED_CONTEXTS)[0]
        assert "Not A Required Context" not in REQUIRED_CONTEXTS
        (tmp_path / "fixture.yml").write_text(
            self._FIXTURE.format(required=required), encoding="utf-8"
        )
        monkeypatch.setattr(helpers, "_WORKFLOWS", tmp_path)
        monkeypatch.setattr(helpers, "RATCHET_WORKFLOWS", ("fixture.yml",))
        assert ci_owners_of("scripts/ci/fixture_ratchet.py") == ["fixture.yml good"]


class TestRegistryContents:
    def test_registry_retains_taste_and_type_ignore_ratchets(self) -> None:
        by_name = {ratchet.job_name: ratchet for ratchet in checks_ratchet.RATCHETS}
        assert by_name["taste-count-ratchet"].script == ("scripts/ci/taste_count_ratchet.py")
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


def ci_baseline_ratchet_scripts() -> list[str]:
    """Every count ratchet under ``scripts/ci``, whichever way it gets its ceiling.

    Two sources, unioned. A scalar ratchet owns ``<name>_baseline.txt`` beside
    ``<name>_ratchet.py``. A base-derived ratchet (issue #5363) owns no file, so
    it is found by importing ``base_derived_ratchet``. Deriving the second set
    from the import rather than a hand-written list keeps deletion of a
    baseline from dropping a ratchet out of this inventory, which would turn
    every wiring test below into a check of nothing.
    """
    ci_dir = REPO_ROOT / "scripts" / "ci"
    scalar = {
        f"scripts/ci/{path.name.removesuffix('_baseline.txt')}_ratchet.py"
        for path in ci_dir.glob("*_baseline.txt")
    }
    derived = {
        f"scripts/ci/{path.name}"
        for path in ci_dir.glob("*_ratchet.py")
        if "from scripts.ci.base_derived_ratchet import" in path.read_text(encoding="utf-8")
    }
    return sorted(scalar | derived)


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
        pre_fix = {ratchet.script for ratchet in checks_ratchet.RATCHETS} - {target}

        assert unregistered_ratchet_scripts(pre_fix) == [target]

    def test_the_inventory_is_not_empty(self) -> None:
        """Edge: a glob that matched nothing would make the check vacuous."""
        assert ci_baseline_ratchet_scripts()

    def test_every_derived_ratchet_script_exists(self) -> None:
        """Edge: a baseline whose module breaks the naming convention fails here."""
        missing = [
            script for script in ci_baseline_ratchet_scripts() if not (REPO_ROOT / script).is_file()
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

    monkeypatch.setattr(checks_ratchet, "_resolve_default_base_ref", lambda _root: "origin/main")
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

    def test_every_declared_ratchet_is_launched(self, monkeypatch: pytest.MonkeyPatch) -> None:
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

    def test_a_skipped_entry_is_reported(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Negative control: the gate declares the entry and never launches it.

        The entry stays in ``RATCHETS``. Only the spawn is suppressed, so the
        declared set and the launched set disagree by exactly one script, which
        is the shape ``test_every_baseline_owning_ratchet_is_launched`` exists
        to catch.
        """
        target = "scripts/ci/taste_count_ratchet.py"
        assert target in [r.script for r in checks_ratchet.RATCHETS], (
            f"{target} must stay declared for this control to model declared-but-never-launched"
        )
        launched = set(spawned_scripts(monkeypatch, skip=target))

        assert [s for s in ci_baseline_ratchet_scripts() if s not in launched] == [target]

    def test_no_script_is_launched_twice(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Edge: one process per entry, so the set comparison cannot hide one."""
        launched = spawned_scripts(monkeypatch)

        assert sorted({s for s in launched if launched.count(s) > 1}) == []
