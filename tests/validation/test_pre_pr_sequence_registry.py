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
    "Unreachable Code Detection",
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
    "ADR Exception Markers",
    "Skill ADR Bindings (ratchet)",
    "Rule ADR Citations (ratchet)",
    "Design Review Frontmatter",
    "Build Command Exit Gates",
    "Stale Script References",
    "Citation Freshness (added lines)",
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
    "Review Axis Drift",
    "Skill Description Budget",
    "Closure Manifest (advisory)",
    "Placeholder Identity",
    "Tracked Conflict Markers",
    "Security Suppressions Diff",
    "Memory Placement",
    "Vendor Portability",
    "Skill Script Portability",
    "Skill Markdown Portability",
    "Skill Markdown Exec Portability",
    "Skill Resolver Anchoring",
    "Plugin-Root Interpreter",
    "Projection Invariants (ADR-107)",
    "Skill Contract Tests",
    "Skill Shell Detection",
    "Skill SKIP Clause Routing",
    "Skill Memory References",
    "Commands Retired (ADR-064)",
    "Skill Output Envelope",
    "Colocated Skill Tests",
    "Rule Activation Coverage",
    "Copilot Routing Exclusions",
    "Sync Registry Provenance",
    "Agent Catalog Drift",
    "Shipped Skill Routes",
    "Canonical Citation Check",
    "Orchestrator Citation Check",
    "Em/en-dash Prohibition",
    "Spec Contradiction Check",
    "Model Pin Governance (warn)",
    "Active Plan Closeout Advisory",
    "YAML Style Validation",
    "Path Normalization",
    "Planning Artifacts",
    "Agent Drift Detection",
    "Agent Content Parity (.claude/agents vs src/claude)",
    "Agent Source Parity",
    "Agent Tree Frontmatter (.claude/agents)",
    "Skill Tree Layout (.claude/skills)",
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
    "NL Structural Debt Ratchet",
    "Skill Routing Roles (metadata.routing)",
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
FAST_STAGE_DUPLICATES = frozenset(
    {
        "Count Ratchets",
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
        assert set(EXPECTED_ORDER) - emitted == FAST_STAGE_DUPLICATES
        assert state.total == state.skipped == len(FAST_STAGE_DUPLICATES)
        assert "count-ratchets" in out

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

        assert set(name for name, _ in recorded).isdisjoint(FAST_STAGE_DUPLICATES)
        assert state.total == state.skipped == len(FAST_STAGE_DUPLICATES)


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
