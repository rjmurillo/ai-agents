#!/usr/bin/env python3
"""Verdict reporting for the pre-PR runner (extracted from ``pre_pr.py``).

Holds the three reporters that read only an :class:`AggregateOutcome`: the
RESULT line, the blocking guidance, and the machine-readable summary. Extracted
because ``pre_pr.py`` sits under a 500-line ceiling (issue #3073, pinned by
``tests/validation/test_pre_pr_model_pin_wiring.py``) and the RESULT-line fix
for issue #5646 crossed it. The ceiling exists to force exactly this split
rather than to be raised, so the split is the fix and not a workaround.

``_print_summary`` stays in ``pre_pr`` because it reads ``ValidationState``,
which lives there; moving it would need a Protocol and a back-reference for no
gain. The seam here is "reads the aggregate" versus "reads the runner's own
records", which is where the dependency already falls.

Import discipline: standard library plus the contract module by its PACKAGE
path. A flat ``import evidence`` and a package
``import scripts.validation.evidence`` yield two distinct ``EvidenceState``
enums, and every ``is`` comparison across that seam returns False. ``pre_pr``
resolves this module by its package path for the same reason.

Related: issue #5646. Caller: ``scripts/validation/pre_pr.py``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from scripts.validation.evidence import (
    AggregateOutcome,
    CheckOutcome,
    EvidenceState,
)


def _licensed_non_pass(summary: AggregateOutcome) -> tuple[CheckOutcome, ...]:
    """Return the outcomes that did not prove their contract but do not block.

    These are the rows a :class:`PolicyException` licenses: a SKIP that did not
    apply, a BLOCKED whose optional linter is not installed. They are real gaps
    in the run's evidence, and the exit code deliberately ignores them.
    """
    return tuple(
        outcome
        for outcome in summary.outcomes
        if outcome.state is not EvidenceState.PASS
    )


def print_result_line(summary: AggregateOutcome) -> None:
    """Print the RESULT line, distinguishing a degraded run from a clean one.

    ``RESULT: All validations passed`` used to print whenever nothing blocked,
    so a machine with neither actionlint nor yamllint installed was
    indistinguishable, at the line most readers stop at, from a machine that
    checked everything. The per-gate rows above already differ; this is the
    summary catching up to them (issue #5646 item 3).

    The clean-run wording is unchanged on purpose: it is quoted in
    ``.agents/governance/GOTCHAS.md`` and in several Serena memories, and a
    reader grepping for it should still find the state it has always named.
    A degraded run gets its own line instead of a qualified version of that
    one, so a grep for the clean string cannot match a degraded run.
    """
    licensed = _licensed_non_pass(summary)
    if not licensed:
        print("RESULT: All validations passed")
        return
    counts = summary.counts()
    breakdown = ", ".join(
        f"{label}: {counts[label]}"
        for label in ("FAIL", "UNKNOWN", "BLOCKED", "SKIP")
        if counts[label]
    )
    print(
        f"RESULT: No validation blocked the gate, but {len(licensed)} of "
        f"{len(summary.outcomes)} did not prove their contract ({breakdown})"
    )
    for outcome in licensed:
        print(f"  {outcome.summary_line()}")
    print("  Licensed by the pre-PR policy; see .agents/devops/SHIFT-LEFT.md")


def print_blocking_guidance(summary: AggregateOutcome) -> None:
    """Name every gate that blocked and why, then how to act on each state."""
    print(f"RESULT: {len(summary.rejected)} validation(s) blocked the gate")
    print()
    for outcome in summary.rejected:
        print(f"  {outcome.summary_line()}")
        if outcome.detail:
            print(f"    {outcome.detail}")
    print()
    print("Fix suggestions:")
    print("  FAIL: review the error above and fix the violation it names")
    print("  BLOCKED: install or authenticate the dependency named in the reason")
    print("  UNKNOWN: the evidence was unreadable; re-run and read the gate's output")
    print("  See .agents/devops/SHIFT-LEFT.md for workflow documentation")
    print()


def write_summary_json(summary: AggregateOutcome, destination: str) -> None:
    """Write the machine-readable summary when a destination was given.

    A write failure is reported and does not change the gate's verdict: the
    summary is a report of the run, not part of it.
    """
    if not destination:
        return
    try:
        Path(destination).write_text(
            json.dumps(summary.to_dict(), indent=2) + "\n", encoding="utf-8"
        )
    except OSError as exc:
        print(f"[WARNING] could not write summary JSON to {destination}: {exc}", file=sys.stderr)
        return
    print(f"Machine-readable summary written to {destination}")
