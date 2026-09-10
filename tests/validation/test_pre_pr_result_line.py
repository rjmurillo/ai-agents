"""The RESULT line must not call a degraded run clean (issue #5646 item 3).

``main`` guarded its success line on ``summary.blocking``, which is
``bool(self.rejected)``. Outcomes a :class:`PolicyException` licenses never
enter ``rejected``, so a run on a machine with neither actionlint nor yamllint
printed two ``[BLOCKED]`` rows and then::

    RESULT: All validations passed

The exit code (0) is correct under the declared policy, so this is an accuracy
defect rather than a fail-open. It still contradicts the #5641 retrospective's
own Impact table, which claims the change fixed "a degraded run and a clean run
printed the same line": the per-gate rows differ now, and the line most readers
stop at did not.

These drive ``main`` through the real sequence and read its stdout, so what is
pinned is the process's own output rather than a helper's return value
(``.claude/rules/testing.md`` MUST 8).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from scripts.validation.evidence import (
    REASON_SCRIPT_ABSENT,
    REASON_TOOL_ABSENT,
    WORKING_TREE,
    CheckOutcome,
)
from scripts.validation.pre_pr import main, run_all_validations

_SEQUENCE_MODULE = run_all_validations.__globals__
_GATE = _SEQUENCE_MODULE["_Gate"]

_CLEAN_LINE = "RESULT: All validations passed"


def _sequence(*outcomes: Any) -> tuple[Any, ...]:
    """Return a sequence of one gate per outcome, named for its index."""
    return tuple(
        _GATE(f"Gate {index}", lambda _root, _args, value=outcome: value)
        for index, outcome in enumerate(outcomes)
    )


def _run(capsys: pytest.CaptureFixture[str], *outcomes: Any) -> tuple[int, str]:
    """Drive the real ``main`` over ``outcomes`` and return its code and stdout."""
    with patch("pre_pr_sequence._SEQUENCE", _sequence(*outcomes)):
        code = main(["--quick"])
    return code, capsys.readouterr().out


def _passing() -> CheckOutcome:
    return CheckOutcome.passed(
        "clean_gate", revision=WORKING_TREE, scope="the tree", examined=3
    )


def _licensed_blocked() -> CheckOutcome:
    """The exact row the pre-PR policy licenses for a missing actionlint."""
    return CheckOutcome.blocked(
        "validate_workflow_yaml",
        reason=REASON_TOOL_ABSENT,
        scope=".github/workflows",
        detail="actionlint is not on PATH, so no workflow file was examined",
    )


class TestResultLine:
    """A reader who stops at RESULT must learn whether anything went unchecked."""

    def test_an_all_pass_run_still_says_all_validations_passed(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Positive control, and the wording contract.

        The string is quoted in ``.agents/governance/GOTCHAS.md`` and in several
        Serena memories, so a reader grepping for it must still find the state
        it has always named.
        """
        code, out = _run(capsys, _passing())

        assert code == 0
        assert _CLEAN_LINE in out

    def test_a_licensed_blocked_run_does_not_say_all_validations_passed(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """The discriminating case: this printed the clean line before the fix."""
        code, out = _run(capsys, _passing(), _licensed_blocked())

        assert code == 0
        assert _CLEAN_LINE not in out

    def test_the_degraded_line_reports_both_counts(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """``ci-scripts.md`` MUST 12: the examined count sits beside the finding.

        "1 of 2" is verifiable. "some gates were skipped" is not, and neither is
        a bare qualifier on the success line.
        """
        _, out = _run(capsys, _passing(), _licensed_blocked())

        assert "1 of 2 did not prove their contract" in out
        assert "BLOCKED: 1" in out

    def test_the_degraded_line_names_the_gate_and_its_reason(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A count with no names sends the reader back up the log to find them."""
        _, out = _run(capsys, _passing(), _licensed_blocked())

        assert "validate_workflow_yaml" in out
        assert f"reason={REASON_TOOL_ABSENT}" in out

    def test_a_licensed_skip_also_suppresses_the_clean_line(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Edge: SKIP is licensed for every gate, so it is the common case.

        A downstream install lacking scripts this repository ships hits this on
        every push, and it is the state most likely to be read as "fine".
        """
        skipped = CheckOutcome.skipped(
            "validate_pester", reason=REASON_SCRIPT_ABSENT, scope="PowerShell tests"
        )

        code, out = _run(capsys, _passing(), skipped)

        assert code == 0
        assert _CLEAN_LINE not in out
        assert "SKIP: 1" in out

    def test_both_licensed_states_are_counted_separately(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Edge: a run can be degraded two different ways at once.

        Collapsing them into one number would tell the reader something went
        unchecked without saying whether to install a tool or ignore a gate
        that does not apply.
        """
        skipped = CheckOutcome.skipped("validate_pester", reason=REASON_SCRIPT_ABSENT)

        _, out = _run(capsys, _passing(), _licensed_blocked(), skipped)

        assert "2 of 3 did not prove their contract" in out
        assert "BLOCKED: 1" in out
        assert "SKIP: 1" in out

    def test_a_blocking_run_prints_neither_result_line(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Negative control on both branches.

        A run that blocks takes the guidance path, so neither the clean line nor
        the degraded one may appear. Without this, a degraded line printed on
        every path would still pass the two tests above.
        """
        failing = CheckOutcome.failed("v", reason="lint.violation", findings=2)

        code, out = _run(capsys, _passing(), failing)

        assert code == 1
        assert _CLEAN_LINE not in out
        assert "did not prove their contract" not in out
        assert "validation(s) blocked the gate" in out
