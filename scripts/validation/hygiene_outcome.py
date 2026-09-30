"""Typed result for the advisory worktree hygiene gates (issue #5636).

``check_tmp_worktrees``, ``check_in_root_worktrees``, and
``check_serena_memory_worktree_scope`` each scanned machine state, printed a
report, and returned ``True``. A run with findings, a run whose
``git worktree list`` failed, and a clean run all returned the same value, so
neither ``--summary-json`` nor the pre-PR summary could count them.

This module maps one scan to one :class:`CheckOutcome`. The three gates stay
advisory: the matching rows in ``evidence._ADVISORY_LICENCES`` license the
non-``PASS`` states this function can return, one validator and one reason at a
time.

A missing observation is ``BLOCKED``, not ``UNKNOWN``. ``UNKNOWN`` is licensed
by nothing in the pre-PR policy (issue #5646), so an advisory gate that could not
finish its scan reports the precondition it lacked instead.

Import discipline: package-path import of ``evidence``, the same rule
``checks_tooling`` states, so the ``EvidenceState`` the runner compares against
is the one built here.
"""

from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.validation.evidence import (  # noqa: E402
    REASON_ADVISORY_FINDINGS,
    REASON_ENTRIES_UNREADABLE,
    REASON_LISTING_FAILED,
    WORKING_TREE,
    CheckOutcome,
)

__all__ = ["hygiene_outcome"]


def hygiene_outcome(
    validator: str,
    *,
    scope: str,
    examined: int,
    findings: int,
    listing_failed: bool = False,
    unreadable: int = 0,
    detail: str = "",
) -> CheckOutcome:
    """Return the typed result of one hygiene scan.

    Precedence, worst first, matching ``evidence._PRECEDENCE``: findings are a
    proven violation and win. Otherwise a failed listing or an unreadable entry
    means the clean verdict cannot be claimed, so the result is ``BLOCKED``.
    Only a scan with none of those is ``PASS``.
    """
    if findings:
        return CheckOutcome.failed(
            validator,
            reason=REASON_ADVISORY_FINDINGS,
            revision=WORKING_TREE,
            scope=scope,
            examined=examined,
            findings=findings,
            detail=detail,
        )
    if listing_failed:
        return CheckOutcome.blocked(
            validator,
            reason=REASON_LISTING_FAILED,
            scope=scope,
            detail="git worktree list failed; the registered half of the scan is incomplete",
        )
    if unreadable:
        return CheckOutcome.blocked(
            validator,
            reason=REASON_ENTRIES_UNREADABLE,
            scope=scope,
            detail=f"{unreadable} item(s) could not be read and were not examined",
        )
    return CheckOutcome.passed(
        validator,
        revision=WORKING_TREE,
        scope=scope,
        examined=examined,
        detail=detail,
    )
