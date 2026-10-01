#!/usr/bin/env python3
"""Fail when the promotion exceptions file is invalid or holds a lapsed record.

Issue #5636, ADR-113 decision 8: "A malformed exceptions file fails the load,
which blocks every promotion until it is fixed." This gate moves that failure
to the pull request that edits the file, so the owner sees it before a release
does. It also fails on a record past its expiry, or past its remediation date,
so a lapsed exception is removed rather than left to block a later promotion.

It does not check approval. Approval is read from the GitHub API at promotion
time (decision 6) and cannot be proven offline.

Exit codes (ADR-035): 0 ok, 1 a record has lapsed, 2 the file is invalid.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.validation.evidence import WORKING_TREE, CheckOutcome, EvidenceState  # noqa: E402
from scripts.validation.promotion_exceptions import (  # noqa: E402
    EXCEPTIONS_RELATIVE_PATH,
    ExceptionsFileError,
    ExceptionStatus,
    PromotionException,
    exception_status,
    load_exceptions,
    utc_today,
)

VALIDATOR = "promotion_exceptions"
REASON_INVALID = "exceptions.invalid"
REASON_LAPSED = "exceptions.lapsed"
EXIT_OK, EXIT_LOGIC, EXIT_CONFIG = 0, 1, 2
_SCOPE = EXCEPTIONS_RELATIVE_PATH.as_posix()


def _no_approval_check(_record: PromotionException) -> bool:
    """Treat every record as approved, because approval is not this gate's question."""
    return True


def _lapsed(records: tuple[PromotionException, ...], today: date) -> list[str]:
    lapsed: list[str] = []
    for record in records:
        status = exception_status(record, today, _no_approval_check)
        if status is not ExceptionStatus.ACTIVE:
            lapsed.append(f"{record.fingerprint[:12]} {status.value}")
    return lapsed


def validate_promotion_exceptions(repo_root: Path, today: date | None = None) -> CheckOutcome:
    """Typed entry point for callers that hold a repository root."""
    try:
        records = load_exceptions(repo_root)
    except ExceptionsFileError as exc:
        return CheckOutcome.failed(
            VALIDATOR,
            reason=REASON_INVALID,
            scope=_SCOPE,
            revision=WORKING_TREE,
            findings=1,
            detail=str(exc),
        )
    lapsed = _lapsed(records, today or utc_today())
    if lapsed:
        return CheckOutcome.failed(
            VALIDATOR,
            reason=REASON_LAPSED,
            scope=_SCOPE,
            revision=WORKING_TREE,
            examined=len(records),
            findings=len(lapsed),
            detail="; ".join(lapsed),
        )
    return CheckOutcome.passed(
        VALIDATOR,
        revision=WORKING_TREE,
        scope=_SCOPE,
        examined=len(records),
        detail=f"{len(records)} exception record(s), none lapsed",
    )


def _exit_code(outcome: CheckOutcome) -> int:
    if outcome.state is EvidenceState.PASS:
        return EXIT_OK
    return EXIT_CONFIG if outcome.reason == REASON_INVALID else EXIT_LOGIC


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns an ADR-035 exit code."""
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--repo-root", type=Path, default=_PROJECT_ROOT)
    parser.add_argument("--today", type=date.fromisoformat, default=None, help="test seam")
    args = parser.parse_args(argv)
    outcome = validate_promotion_exceptions(args.repo_root, args.today)
    print(outcome.report_line())
    return _exit_code(outcome)


if __name__ == "__main__":
    raise SystemExit(main())
