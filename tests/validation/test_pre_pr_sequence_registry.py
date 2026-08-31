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
- edge: ``--skip-tests`` drops Pester from the record list entirely (rather
  than recording it as a skip) and prints its own notice, which is the one
  place the sequence bypasses ``run_validation``.
"""

from __future__ import annotations

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

EXPECTED_ORDER: tuple[str, ...] = (
    'Python Syntax (compile gate)',
    'Count Ratchets',
    'Nested Test Detection',
    'Duplicate Test Helper Detection',
    'Unreachable Code Detection',
    'Subprocess Encoding Convention',
    'Test Working Tree Writes',
    'Push Lock Path Agreement',
    'Worktree Recipe Destinations',
    'Temp-filesystem Worktrees (advisory)',
    'Session End Validation',
    'Mypy Changed Files (ratchet)',
    'Markdown Linting',
    'Workflow YAML Validation',
    'Copilot CLI Version Pin',
    'CI Dependency Pins',
    'ADR Lifecycle Frontmatter (ratchet)',
    'ADR Link Resolution',
    'Design Review Frontmatter',
    'Build Command Exit Gates',
    'Stale Script References',
    'Citation Freshness (added lines)',
    'Documented Interpreter Portability',
    'Orphaned Build Deferrals',
    'Generated Artifact Staleness',
    'Spec ID Uniqueness',
    'Traceability',
    'Vendor Portability',
    'Skill Markdown Portability',
    'Skill Shell Detection',
    'Skill SKIP Clause Routing',
    'Skill Memory References',
    'Colocated Skill Tests',
    'Rule Activation Coverage',
    'Copilot Routing Exclusions',
    'Sync Registry Provenance',
    'Agent Catalog Drift',
    'Shipped Skill Routes',
    'Skill Routing Manifest',
    'Canonical Citation Check',
    'Orchestrator Citation Check',
    'Em/en-dash Prohibition',
    'Spec Contradiction Check',
    'Model Pin Governance (warn)',
    'Active Plan Closeout Advisory',
    'YAML Style Validation',
    'Path Normalization',
    'Planning Artifacts',
    'Agent Drift Detection',
    'Install Parity (agents and rules)',
    'Agent Content Parity (.claude/agents vs src/claude)',
    'Plugin Version Bump',
    'Hook Anchoring (Claude + Copilot)',
    'Copilot Agent Frontmatter',
    'Argument-Hint Frontmatter',
    'Git Hook Health (core.hooksPath)',
    'Lefthook Installed',
    'Workflow Local Run',
    'Review Marker (SHA-bound /review)',
    'Instruction Budget (always-on)',
    'Always-on Corpus Claims',
)

QUICK_SKIPPED: frozenset[str] = frozenset(
    {
        'YAML Style Validation',
        'Path Normalization',
        'Planning Artifacts',
        'Agent Drift Detection',
    }
)
FAST_STAGE_DUPLICATES = frozenset(
    {
        "Count Ratchets",
        "Unreachable Code Detection",
        "Path Normalization",
        "Planning Artifacts",
    }
)


@pytest.fixture(autouse=True)
def _clear_fast_stage_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(pre_pr_sequence.FAST_STAGE_RAN_ENV, raising=False)


def _record(**flags: bool) -> tuple[list[tuple[str, bool]], SimpleNamespace, str]:
    """Drive the real sequence with a fake runner and capture what it emits."""
    recorded: list[tuple[str, bool]] = []

    def fake_run_validation(
        name: str,
        _state: SimpleNamespace,
        _callback: object,
        skip: bool = False,
    ) -> bool:
        recorded.append((name, bool(skip)))
        return True

    defaults = {"quick": False, "skip_tests": False, "verbose": False}
    args = SimpleNamespace(**{**defaults, **flags})
    state = SimpleNamespace(total=0, passed=0, failed=0, skipped=0)
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        pre_pr_sequence.run_all_validations(
            REPO_ROOT, args, state, fake_run_validation
        )
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


class TestSkipTestsFlag:
    """--skip-tests is a no-op now that Pester is removed (issue #4661)."""

    def test_skip_tests_does_not_alter_the_gate_list(self) -> None:
        recorded, _state, _out = _record(skip_tests=True)
        names = [name for name, _ in recorded]
        assert tuple(names) == EXPECTED_ORDER

    def test_skip_tests_bumps_no_totals(self) -> None:
        _recorded, state, _out = _record(skip_tests=True)
        assert (state.total, state.skipped) == (0, 0)

    def test_default_run_leaves_the_totals_to_the_runner(self) -> None:
        _recorded, state, out = _record()
        assert (state.total, state.skipped, out) == (0, 0, "")


class TestFastStageDeferral:
    def test_flag_defers_exactly_the_duplicate_gates(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(pre_pr_sequence.FAST_STAGE_RAN_ENV, "1")
        recorded, state, out = _record()

        emitted = {name for name, _skip in recorded}
        assert set(EXPECTED_ORDER) - emitted == FAST_STAGE_DUPLICATES
        assert state.total == state.skipped == len(FAST_STAGE_DUPLICATES)
        assert "count-ratchets" in out

    def test_other_flag_values_run_every_gate(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
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


class TestPrePrReexportsTheAdrValidators:
    """``pre_pr.py``'s own docstring (issue #2223) says: 'the imports below
    keep ``from scripts.validation.pre_pr import X`` working for callers and
    tests', immediately followed by an explicit disclaimer that the facade is
    not exhaustive (issue #5272). The re-export promise still applies to
    whichever validators are wired into ``pre_pr_sequence._SEQUENCE``, so a
    validator run there without a matching re-export is a defect even though
    the module no longer claims full coverage.

    ``check_adr_links.py``'s ``validate_adr_links`` was wired into
    ``pre_pr_sequence._SEQUENCE`` without the matching re-export in
    ``pre_pr.py``, silently breaking that promise for one caller (Copilot, PR
    #5209 review). Pinned here for the two ADR validators this PR ships
    (``validate_adr_lifecycle``, ``validate_adr_links``), not repo-wide: a
    genuinely repo-wide version of this test, run once against the current
    tree, found 15 more validators already missing the same re-export
    (`validate_count_ratchets`, `validate_mypy_changed_files`,
    `validate_git_hook_health`, and others predating this PR). That gap is
    real but has nothing to do with ADR review tooling; filed as issue
    #5272 rather than fixed here, matching this campaign's own precedent
    (#5205, #5270) for a proven pre-existing defect found along the way.
    Widening this test's scope to the full namespace comparison belongs in
    whichever PR closes that issue, not this one.

    Identity comparison (``is``, not ``==``), so ``pre_pr.py`` defining a
    same-named but different function would not silently pass.
    """

    def test_adr_validators_pre_pr_sequence_imports_are_also_in_pre_pr(self) -> None:
        for name in ("validate_adr_lifecycle", "validate_adr_links"):
            assert getattr(pre_pr_sequence, name) is getattr(pre_pr, name), (
                f"pre_pr.py does not re-export {name} as the identical object "
                f"pre_pr_sequence.py imports"
            )
