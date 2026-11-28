"""``pre_pr_sequence`` is a registry; this pins the registry (issue #4285).

The sequence used to be 47 ordered ``run_validation`` calls inside one 408-line
function. It is now a ``_SEQUENCE`` tuple read by one loop. That refactor is
only safe if the emitted order, the skip flags, and the two special-cased gates
behave exactly as they did before, so this module hard-codes the expected order
rather than reading it back out of the module under test.

The expectation is deliberately a literal. An earlier attempt at this guard
derived its expected list from the production source with ``inspect.getsource``
and therefore moved in lockstep with any reorder: it could not fail. An
expectation must come from a different authority than the code it grades. The
literal below was captured from the pre-refactor implementation at
``origin/main`` and is the only authority this file trusts.

Coverage:

- positive: the default run emits every gate in order with no skips.
- negative: a reorder, an added gate, or a dropped gate fails the order
  assertion; ``--quick`` marks exactly four gates skipped and no others.
- edge: no gate bypasses ``run_validation``. ``_Gate`` used to carry a
  ``skip_flag`` escape that dropped a gate from the record list entirely
  instead of recording a skip; it served ``--skip-tests``, no gate ever set it,
  and both are gone. ``TestNoGateBypassesTheRunner`` pins that.
"""

from __future__ import annotations

import dataclasses
import io
import sys
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]

# Import the way production imports (issue #2223): prepend ``scripts/validation``
# to ``sys.path`` and import by bare name. The insert is at index 0, so this
# directory takes import precedence over everything already on the path. Never
# restored.
_VALIDATION_DIR = REPO_ROOT / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))
import pre_pr
import pre_pr_sequence

from scripts.validation.pre_pr import ValidationState

EXPECTED_ORDER: tuple[str, ...] = (
    "Python Syntax (compile gate)",
    "Count Ratchets",
    "Nested Test Detection",
    "Duplicate Test Helper Detection",
    "Python Duplicate Code Detection",
    "Unused Dependency Detection",
    "Dependency Version Drift",
    "Unreachable Code Detection",
    "Unused Argument Detection",
    "Subprocess Encoding Convention",
    "Test Working Tree Writes",
    "Push Lock Path Agreement",
    "Index Line Endings",
    "Worktree Recipe Destinations",
    "Legacy .agents Write Targets",
    "Temp-filesystem Worktrees (advisory)",
    "In-root Worktrees (advisory)",
    "Serena Memory Worktree Scope (advisory)",
    "Session End Validation",
    "Mypy Changed Files (ratchet)",
    "Markdown Linting",
    "Workflow YAML Validation",
    "Required-Context Conditions (advisory)",
    "Copilot CLI Version Pin",
    "CI Dependency Pins",
    "ADR Lifecycle Frontmatter (ratchet)",
    "ADR Link Resolution",
    "Markdown Link Resolution",
    "ADR Exception Markers",
    "Skill ADR Bindings (ratchet)",
    "Rule ADR Citations (ratchet)",
    "ADR Supersession Citations (ratchet)",
    "Design Review Frontmatter",
    "Build Command Exit Gates",
    "Stale Script References",
    "Agent and Skill Reference Pages (docs/skills, docs/agents)",
    "Skill Page Freshness (advisory)",
    "Agent and Skill Doc Review",
    "Citation Freshness (added lines)",
    "Citation Freshness (reverse pass)",
    "Measurement Anchoring (added lines)",
    "Doc Date Drift (advisory, added lines)",
    "IO Portability (added lines)",
    "Documented Interpreter Portability",
    "Orphaned Build Deferrals",
    "Generated Artifact Staleness",
    "Skill Template Drift",
    "Agent Template Drift",
    "Rule Template Drift",
    "Rule Lossless Fixtures",
    "Hook Template Drift",
    "Spec ID Uniqueness",
    "Traceability",
    "Bypass Allowlist",
    "Promotion Exceptions",
    "Agent Registry",
    "Plugin Frontmatter Self-Containment",
    "Python3 Entrypoints",
    "GitHub Actions SHA Pinning",
    "ADR Number Uniqueness",
    "Agent-Skill Discriminator",
    "Hook Contracts",
    "Passive Context Budget",
    "Skillbook Validation",
    "Skill Description Budget",
    "Import Boundaries",
    "Closure Manifest (advisory)",
    "Placeholder Identity",
    "Tracked Conflict Markers",
    "Security Suppressions Diff",
    "Skill Rewrite Evidence (ADR-127)",
    "Memory Placement",
    "Vendor Portability",
    "Skill Script Portability",
    "Skill Markdown Portability",
    "Skill Markdown Exec Portability",
    "Host-Neutral Dispatch",
    "Skill Resolver Anchoring",
    "Plugin-Root Interpreter",
    "Projection Invariants (ADR-107)",
    "Skill Contract Tests",
    "Skill Shell Detection",
    "Skill SKIP Clause Routing",
    "Skill Memory References",
    "Commands Retired (ADR-064)",
    "Retired Ownership Claims (ADR-109)",
    "Skill Output Envelope",
    "Colocated Skill Tests",
    "Rule Activation Coverage",
    "Route Scenario Coverage",
    "Copilot Routing Exclusions",
    "Sync Registry Provenance",
    "Agent Catalog Drift",
    "Shipped Skill Routes",
    "Canonical Citation Check",
    "Orchestrator Citation Check",
    "Em/en-dash Prohibition",
    "Spec Contradiction Check",
    "Model Pin Governance (warn)",
    "Doc Accuracy Same-PR (advisory)",
    "Active Plan Closeout Advisory",
    "YAML Style Validation",
    "Path Normalization",
    "Planning Artifacts",
    "Agent Drift Detection",
    "Agent Content Parity (.claude/agents vs src/claude)",
    "Agent Source Parity",
    "Equivalence Predicates",
    "Agent Tree Frontmatter (.claude/agents)",
    "Agent Delegation (src/claude/agents)",
    "Agent Success Criterion (src/claude/agents)",
    "Router Vocabulary (orchestrator)",
    "Skill Tree Layout (.claude/skills)",
    "Skill Frontmatter (all skill trees)",
    "Template Repo References (templates/skills, templates/agents)",
    "Skill Shell Placeholders (.claude/skills)",
    "Host Marketplaces",
    "Plugin Version Bump",
    "Hook Anchoring (Claude + Copilot)",
    "Copilot Agent Frontmatter",
    "Argument-Hint Frontmatter",
    "Git Hook Health (core.hooksPath)",
    "Lefthook Installed",
    "Workflow Local Run",
    "Review Marker (SHA-bound /review)",
    "Instruction Budget (always-on)",
    "Instruction Bytes (per-fixture)",
    "Always-on Corpus Claims",
    "Rule Scope Declarations (paths:)",
    "Capability Graph (metadata.capability)",
    "External Contract Records (external-contract)",
    "NL Structural Debt Ratchet",
    "Skill Routing Roles (metadata.routing)",
    "Skill Artifact Flow (metadata.inputs/outputs)",
    "Skill Trigger Phrase Resolution (ratchet)",
    "Path-Local Effective Context Ratchet",
)

QUICK_SKIPPED: frozenset[str] = frozenset(
    {
        "YAML Style Validation",
        "Path Normalization",
        "Planning Artifacts",
        "Agent Drift Detection",
    }
)
# Heavy whole-tree gates a CI job owns (owner ruling 2026-11-27): skipped, with a
# visible [SKIP], when pre_pr runs inside the pre-push hook.
CI_OWNED_GATES = frozenset({"Count Ratchets", "Generated Artifact Staleness"})
FAST_STAGE_DUPLICATES = frozenset(
    {
        "Unreachable Code Detection",
        "Path Normalization",
        "Planning Artifacts",
        "Em/en-dash Prohibition",
    }
)


@pytest.fixture(autouse=True)
def _clear_fast_stage_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(pre_pr_sequence.FAST_STAGE_RAN_ENV, raising=False)


def _record(**flags: bool) -> tuple[list[tuple[str, bool]], ValidationState, str]:
    """Drive the real sequence with a fake runner and capture what it emits.

    ``state`` is the real ``ValidationState`` rather than a SimpleNamespace of
    counters. Since issue #5635 the sequence writes through ``state.record``,
    which owns both the appended row and the per-state counter, so a fake that
    carries only the integers cannot stand in for it.
    """
    recorded: list[tuple[str, bool]] = []

    def fake_run_validation(
        name: str,
        _state: ValidationState,
        _callback: object,
        skip: bool = False,
    ) -> bool:
        recorded.append((name, bool(skip)))
        return True

    defaults = {"quick": False}
    args = SimpleNamespace(**{**defaults, **flags})
    state = ValidationState()
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        pre_pr_sequence.run_all_validations(REPO_ROOT, args, state, fake_run_validation)
    return recorded, state, buffer.getvalue()


class TestRegistryOrder:
    """The emitted order is the contract every consumer depends on."""

    def test_default_run_emits_the_expected_gates_in_order(self) -> None:
        recorded, _state, _out = _record()
        assert tuple(name for name, _ in recorded) == EXPECTED_ORDER

    def test_default_run_skips_nothing(self) -> None:
        recorded, _state, _out = _record()
        assert [name for name, skip in recorded if skip] == []

    def test_registry_length_matches_the_emitted_count(self) -> None:
        recorded, _state, _out = _record()
        assert len(pre_pr_sequence._SEQUENCE) == len(recorded)

    def test_no_gate_name_repeats(self) -> None:
        assert len(set(EXPECTED_ORDER)) == len(EXPECTED_ORDER)


class TestQuickFlag:
    """``--quick`` marks a fixed subset skipped and drops nothing."""

    def test_quick_emits_the_same_gates_in_the_same_order(self) -> None:
        recorded, _state, _out = _record(quick=True)
        assert tuple(name for name, _ in recorded) == EXPECTED_ORDER

    def test_quick_skips_exactly_the_slow_gates(self) -> None:
        recorded, _state, _out = _record(quick=True)
        assert {name for name, skip in recorded if skip} == QUICK_SKIPPED


class TestNoGateBypassesTheRunner:
    """Every gate reaches ``run_validation``; none is dropped by an args flag.

    ``_Gate.skip_flag`` named an ``args`` attribute that, when truthy, skipped
    ``run_validation`` entirely and only bumped the totals. It existed for
    ``--skip-tests``, no gate in ``_SEQUENCE`` ever set it, and it is removed.
    """

    def test_gate_carries_no_args_driven_bypass_field(self) -> None:
        fields = {f.name for f in dataclasses.fields(pre_pr_sequence._Gate)}
        assert not fields & {"skip_flag", "skip_note"}

    def test_quick_is_the_only_args_attribute_the_sequence_reads(self) -> None:
        """An args namespace carrying only ``quick`` must drive the full run."""
        recorded, _state, _out = _record()
        assert tuple(name for name, _ in recorded) == EXPECTED_ORDER

    def test_unknown_args_attributes_change_nothing(self) -> None:
        """Negative: a stale ``skip_tests`` attribute must not skip anything."""
        recorded, state, out = _record(skip_tests=True, verbose=True)
        assert tuple(name for name, _ in recorded) == EXPECTED_ORDER
        assert (state.total, state.skipped, out) == (0, 0, "")

    def test_default_run_leaves_the_totals_to_the_runner(self) -> None:
        _recorded, state, out = _record()
        assert (state.total, state.skipped, out) == (0, 0, "")


class TestFastStageDeferral:
    def test_flag_defers_exactly_the_duplicate_gates(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(pre_pr_sequence.FAST_STAGE_RAN_ENV, "1")
        recorded, state, out = _record()

        emitted = {name for name, _skip in recorded}
        assert set(EXPECTED_ORDER) - emitted == FAST_STAGE_DUPLICATES | CI_OWNED_GATES
        assert state.total == state.skipped == len(FAST_STAGE_DUPLICATES | CI_OWNED_GATES)
        assert "python-unreachable-statements" in out
        for gate in CI_OWNED_GATES:
            assert f"[SKIP] {gate}" in out

    def test_other_flag_values_run_every_gate(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(pre_pr_sequence.FAST_STAGE_RAN_ENV, "true")
        recorded, state, _out = _record()

        assert tuple(name for name, _ in recorded) == EXPECTED_ORDER
        assert (state.total, state.skipped) == (0, 0)

    def test_quick_mode_does_not_double_count_deferred_gates(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(pre_pr_sequence.FAST_STAGE_RAN_ENV, "1")
        recorded, state, _out = _record(quick=True)

        assert set(name for name, _ in recorded).isdisjoint(FAST_STAGE_DUPLICATES | CI_OWNED_GATES)
        assert state.total == state.skipped == len(FAST_STAGE_DUPLICATES | CI_OWNED_GATES)


class TestCiOwnedGates:
    """``ci_owned_by`` names a real, unconditional CI job for every gate that sets it."""

    @staticmethod
    def _owned() -> list[pre_pr_sequence._Gate]:
        return [gate for gate in pre_pr_sequence._SEQUENCE if gate.ci_owned_by]

    def test_exactly_the_expected_gates_are_ci_owned(self) -> None:
        assert {gate.name for gate in self._owned()} == CI_OWNED_GATES

    @staticmethod
    def _gates_with_both(gates: tuple[pre_pr_sequence._Gate, ...]) -> list[str]:
        return [gate.name for gate in gates if gate.already_run_by and gate.ci_owned_by]

    def test_no_gate_sets_both_deferral_fields(self) -> None:
        assert self._gates_with_both(pre_pr_sequence._SEQUENCE) == []

    def test_the_both_fields_check_detects_a_violation(self) -> None:
        """Negative control: the same scan must name a gate that sets both fields."""
        bad = pre_pr_sequence._Gate(
            "Bad", lambda _r, _a: True, already_run_by="x", ci_owned_by="y.yml z"
        )
        good = pre_pr_sequence._Gate("Good", lambda _r, _a: True, ci_owned_by="y.yml z")
        assert self._gates_with_both((good, bad)) == ["Bad"]

    @pytest.mark.parametrize("gate_name", sorted(CI_OWNED_GATES))
    def test_every_ci_owned_by_entry_names_a_required_unconditional_job(
        self, gate_name: str
    ) -> None:
        gate = next(g for g in pre_pr_sequence._SEQUENCE if g.name == gate_name)
        entries = _ci_owned_entries(gate)
        assert entries
        for entry in entries:
            assert _owner_problems(entry, needle=None) == []

    def test_staleness_owner_runs_the_command_the_gate_runs(self) -> None:
        """ADR-104 rule 6: the deferral is tested on what it relies on.

        The gate shells out to ``build_all.py --check``; the CI job it defers to
        must run that same command in an unconditional step of a required job.
        """
        import check_generated_staleness

        gate_scripts = {"/".join(parts) for _label, parts in check_generated_staleness._CHECKS}
        assert gate_scripts == {"build/scripts/build_all.py"}
        gate = next(
            g for g in pre_pr_sequence._SEQUENCE if g.name == "Generated Artifact Staleness"
        )
        for entry in _ci_owned_entries(gate):
            assert _owner_problems(entry, needle="build/scripts/build_all.py --check") == []

    def test_count_ratchets_owners_are_exactly_the_jobs_that_run_the_registry(self) -> None:
        """Every RATCHETS script has a required, unconditional CI owner, and the
        ``ci_owned_by`` text names exactly that set of jobs."""
        from checks_ratchet import RATCHETS

        from tests.ci.ratchet_test_helpers import ci_owners_of

        owners: set[str] = set()
        for ratchet in RATCHETS:
            found = ci_owners_of(ratchet.script)
            assert found, f"{ratchet.script} has no required, unconditional CI job"
            owners.update(found)
        gate = next(g for g in pre_pr_sequence._SEQUENCE if g.name == "Count Ratchets")
        assert set(_ci_owned_entries(gate)) == owners


def _ci_owned_entries(gate: object) -> list[str]:
    return [
        part.strip() for part in str(getattr(gate, "ci_owned_by", "")).split(",") if part.strip()
    ]


def _owner_problems(entry: str, needle: str | None, workflows_dir: Path | None = None) -> list[str]:
    """Return why ``entry`` (``<workflow>.yml <job-id>``) is not a valid CI owner.

    Valid means: the workflow and job exist, the job has no job-level ``if:``,
    the job or a rollup that needs it is a required context, and, when
    ``needle`` is given, an unconditional step of the job runs it.
    """
    from tests.ci.ratchet_test_helpers import _is_required_job

    base = workflows_dir or REPO_ROOT / ".github" / "workflows"
    workflow, _, job_id = entry.partition(" ")
    if not workflow.endswith(".yml") or not job_id:
        return [f"{entry!r} is not '<workflow>.yml <job>'"]
    path = base / workflow
    if not path.is_file():
        return [f"{entry!r}: {path} does not exist"]
    jobs = yaml.safe_load(path.read_text(encoding="utf-8"))["jobs"]
    if job_id not in jobs:
        return [f"{entry!r}: job {job_id!r} not in {workflow}"]
    problems: list[str] = []
    if jobs[job_id].get("if") is not None:
        problems.append(f"{entry!r}: job carries an if:")
    if not _is_required_job(jobs, job_id):
        problems.append(f"{entry!r}: neither the job nor a rollup that needs it is required")
    if needle is not None and not any(
        needle in str(step.get("run", "")) and step.get("if") is None
        for step in jobs[job_id].get("steps", [])
    ):
        problems.append(f"{entry!r}: no unconditional step runs {needle!r}")
    return problems


class TestOwnerProblemsNegativeControls:
    """Each failure mode ``_owner_problems`` guards must be reported."""

    _WORKFLOW = (
        "jobs:\n"
        "  good:\n"
        "    name: Run Python Tests\n"
        "    steps:\n"
        "      - run: uv run python build/scripts/build_all.py --check\n"
        "  gated:\n"
        "    name: Run Python Tests\n"
        "    if: github.event_name == 'push'\n"
        "    steps:\n"
        "      - run: uv run python build/scripts/build_all.py --check\n"
        "  optional:\n"
        "    name: Not A Required Context\n"
        "    steps:\n"
        "      - run: uv run python build/scripts/build_all.py --check\n"
        "  stepgated:\n"
        "    name: Run Python Tests\n"
        "    steps:\n"
        "      - run: uv run python build/scripts/build_all.py --check\n"
        "        if: matrix.primary\n"
    )

    @pytest.fixture
    def workflows(self, tmp_path: Path) -> Path:
        (tmp_path / "w.yml").write_text(self._WORKFLOW, encoding="utf-8")
        return tmp_path

    def test_a_valid_owner_has_no_problem(self, workflows: Path) -> None:
        assert _owner_problems("w.yml good", "build_all.py --check", workflows) == []

    @pytest.mark.parametrize(
        ("entry", "needle", "fragment"),
        [
            ("w.yml missing", None, "not in w.yml"),
            ("absent.yml good", None, "does not exist"),
            ("w.yml", None, "is not '<workflow>.yml <job>'"),
            ("w.yml gated", None, "job carries an if:"),
            ("w.yml optional", None, "required"),
            ("w.yml stepgated", "build_all.py --check", "no unconditional step"),
            ("w.yml good", "some_other_script.py", "no unconditional step"),
        ],
    )
    def test_each_failure_mode_is_reported(
        self, workflows: Path, entry: str, needle: str | None, fragment: str
    ) -> None:
        problems = _owner_problems(entry, needle, workflows)
        assert any(fragment in problem for problem in problems), problems


class TestPrePrReexportsEverySequenceValidator:
    """``pre_pr.py`` is a facade (issue #2223): ``from scripts.validation.pre_pr
    import X`` must keep working for every validator ``pre_pr_sequence`` imports.
    A validator imported there without the matching re-export in ``pre_pr.py``
    raises ``ImportError`` for callers (issue #5272,
    first seen for ``validate_adr_links`` in PR #5209).

    The check walks ``vars(pre_pr_sequence)`` rather than a hand-kept list, so
    a new gate cannot drift. Identity comparison (``is``, not ``==``), so
    ``pre_pr.py`` defining a same-named but different function would not
    silently pass.
    """

    @staticmethod
    def _sequence_validators() -> dict[str, object]:
        return {
            name: obj
            for name, obj in vars(pre_pr_sequence).items()
            if name.startswith("validate_") and callable(obj)
        }

    def test_sequence_exposes_validators(self) -> None:
        """Guard against a vacuous pass if the discovery filter breaks."""
        assert len(self._sequence_validators()) > 50

    def test_every_sequence_validator_is_reexported_as_identical_object(self) -> None:
        missing = sorted(name for name in self._sequence_validators() if not hasattr(pre_pr, name))
        assert not missing, (
            f"pre_pr.py does not re-export these pre_pr_sequence validators: {missing}"
        )
        not_identical = sorted(
            name
            for name, obj in self._sequence_validators().items()
            if getattr(pre_pr, name) is not obj
        )
        assert not not_identical, (
            f"pre_pr.py exposes a different object than pre_pr_sequence for: {not_identical}"
        )

    def test_missing_reexport_is_reported(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Negative control: removing a re-export must make the walk see it."""
        monkeypatch.delattr(pre_pr, "validate_count_ratchets")
        missing = [name for name in self._sequence_validators() if not hasattr(pre_pr, name)]
        assert missing == ["validate_count_ratchets"]
