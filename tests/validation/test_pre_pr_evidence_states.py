"""The pre-PR runner records typed evidence states, not a boolean (issue #5635).

Before this change ``run_validation`` mapped a validator's ``bool`` onto
``PASS``/``FAIL`` and recorded ``MissingScriptSkip`` as ``SKIP``. A validator
had no way to say "I could not run" or "what came back was unreadable", so both
arrived as ``True`` and the gate reported success. These tests drive the real
runner and the real ``main`` entry point, and each one names the state the old
runner could not have produced.

``main`` is exercised through ``pre_pr_sequence._SEQUENCE``, patched to a single
gate, so the exit code is measured on the process's own return value rather
than on a helper's (``.claude/rules/testing.md`` MUST 8).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

from scripts.validation import pre_pr
from scripts.validation.evidence import (
    REASON_ALREADY_RUN,
    REASON_BASE_REF_UNRESOLVED,
    REASON_DIFF_FAILED,
    REASON_MALFORMED_OUTPUT,
    REASON_QUICK_MODE,
    REASON_SCRIPT_ABSENT,
    REASON_TOOL_ABSENT,
    REASON_VALIDATOR_RAISED,
    CheckOutcome,
    EvidenceState,
    aggregate,
)
from scripts.validation.pre_pr import (
    MissingScriptSkip,
    ValidationState,
    main,
    run_all_validations,
    run_validation,
)

_SEQUENCE_MODULE = run_all_validations.__globals__
_GATE = _SEQUENCE_MODULE["_Gate"]
_FAST_STAGE_ENV = _SEQUENCE_MODULE["FAST_STAGE_RAN_ENV"]


def _run(callback: Any, *, skip: bool = False) -> tuple[ValidationState, bool]:
    """Drive the real runner once and return the state plus its verdict."""
    state = ValidationState()
    accepted = run_validation("Gate Under Test", state, callback, skip=skip)
    return state, accepted


def _only(state: ValidationState) -> CheckOutcome:
    """Return the single outcome the runner recorded."""
    (outcome,) = state.outcomes()
    return outcome


class TestRunValidationRecordsTheState:
    """One recorded outcome per gate, carrying the state the validator reported."""

    def test_a_true_returning_validator_records_pass(self) -> None:
        """The unmigrated boolean contract still reaches PASS."""
        state, accepted = _run(lambda: True)

        assert _only(state).state is EvidenceState.PASS
        assert accepted is True
        assert state.passed == 1

    def test_a_false_returning_validator_records_fail(self) -> None:
        """A boolean failure still blocks."""
        state, accepted = _run(lambda: False)

        assert _only(state).state is EvidenceState.FAIL
        assert accepted is False
        assert state.failed == 1

    def test_a_blocked_outcome_is_recorded_and_blocks(self) -> None:
        """The behavior change: an unrunnable check no longer reads as success.

        NEGATIVE CONTROL for issue #5635. The pre-change runner had no BLOCKED
        state, so a validator in this position returned ``True`` and the row was
        counted under ``passed``.
        """
        blocked = CheckOutcome.blocked(
            "validate_session_end", reason=REASON_BASE_REF_UNRESOLVED, detail="no base ref"
        )

        state, accepted = _run(lambda: blocked)

        assert _only(state).state is EvidenceState.BLOCKED
        assert accepted is False
        assert state.blocked == 1
        assert state.passed == 0

    def test_an_unknown_outcome_is_recorded_and_blocks(self) -> None:
        """Incomplete evidence blocks rather than passing."""
        unknown = CheckOutcome.unknown("v", reason=REASON_DIFF_FAILED)

        state, accepted = _run(lambda: unknown)

        assert _only(state).state is EvidenceState.UNKNOWN
        assert accepted is False
        assert state.unknown == 1

    def test_a_validator_returning_none_records_unknown(self) -> None:
        """A gate that told the runner nothing is not a gate that passed."""
        state, accepted = _run(lambda: None)

        outcome = _only(state)
        assert outcome.state is EvidenceState.UNKNOWN
        assert outcome.reason == REASON_MALFORMED_OUTPUT
        assert accepted is False

    def test_missing_script_skip_records_skip_and_does_not_block(self) -> None:
        """The documented SHIFT-LEFT.md exception, now with a reason code."""

        def absent() -> bool:
            raise MissingScriptSkip("validate_x.py not present (downstream install)")

        state, accepted = _run(absent)

        outcome = _only(state)
        assert outcome.state is EvidenceState.SKIP
        assert outcome.reason == REASON_SCRIPT_ABSENT
        assert "downstream install" in outcome.detail
        assert accepted is True
        assert state.skipped == 1

    def test_a_raising_validator_records_fail_with_a_crash_reason(self) -> None:
        """A crash still blocks, and says it was a crash, not a finding."""

        def explode() -> bool:
            raise RuntimeError("boom")

        state, accepted = _run(explode)

        outcome = _only(state)
        assert outcome.state is EvidenceState.FAIL
        assert outcome.reason == REASON_VALIDATOR_RAISED
        assert "boom" in outcome.detail
        assert accepted is False

    def test_quick_mode_skip_records_its_own_reason(self) -> None:
        """A deliberate skip is distinguishable from an absent script."""
        state, accepted = _run(lambda: True, skip=True)

        outcome = _only(state)
        assert outcome.state is EvidenceState.SKIP
        assert outcome.reason == REASON_QUICK_MODE
        assert accepted is True

    def test_the_runner_times_the_validator(self) -> None:
        """The runner owns the clock, so every row carries a duration."""
        state, _ = _run(lambda: True)

        assert _only(state).duration_seconds >= 0.0


class TestValidationStateRecord:
    """Counters move with the recorded state, and no row is lost."""

    @pytest.mark.parametrize(
        ("outcome", "counter"),
        [
            (CheckOutcome.passed("v", revision="HEAD", scope="tree"), "passed"),
            (CheckOutcome.failed("v", reason="lint.violation"), "failed"),
            (CheckOutcome.skipped("v", reason=REASON_SCRIPT_ABSENT), "skipped"),
            (CheckOutcome.blocked("v", reason=REASON_TOOL_ABSENT), "blocked"),
            (CheckOutcome.unknown("v", reason=REASON_DIFF_FAILED), "unknown"),
        ],
    )
    def test_each_state_increments_its_own_counter(
        self, outcome: CheckOutcome, counter: str
    ) -> None:
        """BLOCKED and UNKNOWN have counters of their own, not passed."""
        state = ValidationState()

        state.record("Gate", outcome)

        assert getattr(state, counter) == 1
        assert state.total == 1

    def test_the_record_keeps_both_the_label_and_the_typed_outcome(self) -> None:
        """Callers reading ``record.status`` keep working; the evidence is there too."""
        state = ValidationState()
        outcome = CheckOutcome.blocked("v", reason=REASON_TOOL_ABSENT, detail="actionlint absent")

        state.record("Workflow Validation", outcome)

        (record,) = state.results
        assert record.status == "BLOCKED"
        assert record.name == "Workflow Validation"
        assert record.outcome is outcome
        assert record.message == "actionlint absent"

    def test_outcomes_returns_the_recorded_evidence_in_run_order(self) -> None:
        """The aggregate reads this; order is what a reader follows."""
        state = ValidationState()
        state.record("A", CheckOutcome.passed("a", revision="HEAD", scope="tree"))
        state.record("B", CheckOutcome.failed("b", reason="lint.violation"))

        assert [outcome.validator for outcome in state.outcomes()] == ["a", "b"]


def _sequence_returning(outcome: Any) -> tuple[Any, ...]:
    """Return a one-gate sequence whose gate returns ``outcome``."""
    return (_GATE("Gate Under Test", lambda _root, _args: outcome),)


class TestMainExitCode:
    """The process exit code follows the worst state that blocked the gate."""

    def _main_with(self, outcome: Any, argv: list[str] | None = None) -> int:
        with patch("pre_pr_sequence._SEQUENCE", _sequence_returning(outcome)):
            return main(argv if argv is not None else ["--quick"])

    def test_a_passing_gate_exits_zero(self) -> None:
        """Positive control for the three failing cases below."""
        assert self._main_with(True) == 0

    def test_a_failing_gate_exits_one(self) -> None:
        """A logic error, unchanged from before issue #5635."""
        assert self._main_with(False) == 1

    def test_a_blocked_gate_exits_three(self) -> None:
        """ADR-035 external. The pre-change runner exited 0 here."""
        blocked = CheckOutcome.blocked("v", reason=REASON_TOOL_ABSENT, detail="actionlint absent")

        assert self._main_with(blocked) == 3

    def test_an_unknown_gate_exits_one(self) -> None:
        """Unreadable evidence is a logic error, not a pass."""
        unknown = CheckOutcome.unknown("v", reason=REASON_DIFF_FAILED, detail="git diff failed")

        assert self._main_with(unknown) == 1

    def test_a_skipped_gate_exits_zero_under_the_documented_policy(self) -> None:
        """SHIFT-LEFT.md says a gate that does not apply does not block."""

        def absent(_root: Path, _args: argparse.Namespace) -> bool:
            raise MissingScriptSkip("validate_x.py not present (downstream install)")

        with patch("pre_pr_sequence._SEQUENCE", (_GATE("Gate Under Test", absent),)):
            assert main(["--quick"]) == 0


class TestMainSummaryJson:
    """The machine-readable summary preserves every child state."""

    def test_summary_json_is_written_with_child_states_and_policy(
        self, tmp_path: Path
    ) -> None:
        """Acceptance criterion: aggregators produce a machine-readable summary."""
        destination = tmp_path / "summary.json"
        assert not destination.exists()
        blocked = CheckOutcome.blocked("v", reason=REASON_TOOL_ABSENT, detail="actionlint absent")

        with patch("pre_pr_sequence._SEQUENCE", _sequence_returning(blocked)):
            exit_code = main(["--quick", "--summary-json", str(destination)])

        payload = json.loads(destination.read_text(encoding="utf-8"))
        assert exit_code == 3
        assert payload["state"] == "BLOCKED"
        assert payload["blocking"] is True
        assert payload["exit_code"] == 3
        assert payload["counts"]["BLOCKED"] == 1
        assert payload["results"][0]["reason"] == "tool.absent"
        assert payload["rejected"][0]["validator"] == "v"
        assert payload["policy"]["exceptions"][0]["states"] == ["SKIP"]

    def test_no_summary_is_written_when_no_destination_is_given(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The flag is opt-in; the default run writes nothing.

        The chdir is load-bearing. Without it ``main`` is never told about
        ``tmp_path``, so an assertion that the directory stayed empty holds no
        matter what the writer does, which is the vacuous shape
        ``.claude/rules/testing.md`` MUST 12 and SHOULD 14 forbid. Standing in
        ``tmp_path`` is what makes a stray relative write land where this test
        is looking.
        """
        monkeypatch.chdir(tmp_path)

        with patch("pre_pr_sequence._SEQUENCE", _sequence_returning(True)):
            main(["--quick"])

        assert list(tmp_path.iterdir()) == []

    def test_the_writer_is_handed_the_empty_destination_on_a_default_run(self) -> None:
        """Pin the contract at the call, not only at its observable effect."""
        with patch.object(pre_pr, "_write_summary_json") as writer:
            with patch("pre_pr_sequence._SEQUENCE", _sequence_returning(True)):
                main(["--quick"])

        assert writer.call_args.args[1] == ""

    def test_write_summary_json_creates_nothing_for_an_empty_destination(
        self, tmp_path: Path
    ) -> None:
        """The guard itself, driven directly."""
        summary = aggregate("g", [CheckOutcome.passed("v", revision="HEAD", scope="tree")])

        pre_pr._write_summary_json(summary, "")

        assert list(tmp_path.iterdir()) == []

    def test_an_unwritable_destination_warns_without_changing_the_verdict(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """The summary reports the run; it is not part of it."""
        unwritable = tmp_path / "missing-dir" / "summary.json"

        with patch("pre_pr_sequence._SEQUENCE", _sequence_returning(True)):
            exit_code = main(["--quick", "--summary-json", str(unwritable)])

        assert exit_code == 0
        assert "could not write summary JSON" in capsys.readouterr().err
        assert not unwritable.exists()


class TestFastStageSkipIsRecorded:
    """A row the sequence short-circuits still appears in the summary."""

    @staticmethod
    def _run_fast_stage_sequence(monkeypatch: pytest.MonkeyPatch) -> ValidationState:
        monkeypatch.setenv(_FAST_STAGE_ENV, "1")
        state = ValidationState()
        args = SimpleNamespace(quick=True)
        gate = _GATE(
            "Already Run Gate",
            lambda _root, _args: True,
            already_run_by="python-tests",
        )
        with patch("pre_pr_sequence._SEQUENCE", (gate,)):
            run_all_validations(Path.cwd(), args, state, run_validation)
        return state

    def test_the_short_circuited_gate_records_a_skip_row(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """It used to bump two counters and append no record at all."""
        state = self._run_fast_stage_sequence(monkeypatch)

        (outcome,) = state.outcomes()
        assert outcome.state is EvidenceState.SKIP
        assert outcome.reason == REASON_ALREADY_RUN
        assert "python-tests" in outcome.detail
        assert state.total == 1
        assert state.skipped == 1

    def test_the_gate_still_runs_when_the_fast_stage_did_not(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Control: the skip is conditional on the environment variable."""
        monkeypatch.delenv(_FAST_STAGE_ENV, raising=False)
        state = ValidationState()
        args = SimpleNamespace(quick=True)
        gate = _GATE(
            "Already Run Gate",
            lambda _root, _args: True,
            already_run_by="python-tests",
        )

        with patch("pre_pr_sequence._SEQUENCE", (gate,)):
            run_all_validations(Path.cwd(), args, state, run_validation)

        (outcome,) = state.outcomes()
        assert outcome.state is EvidenceState.PASS
