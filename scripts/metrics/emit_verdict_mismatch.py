#!/usr/bin/env python3
"""K4 emission point: record a local-vs-CI /review verdict mismatch.

K4 (REQ-008-09) fires when the local ``/review`` verdict and the CI
verdict on the same commit disagree. 3+ such mismatches in 30 days mean
the convergence claim is false (local and CI silently diverged). This
script compares two verdict strings for one commit and emits a single K4
kill-criteria event through the canonical emitter only when they differ.

Verdict comparison is case-insensitive and trims surrounding whitespace,
so ``PASS`` and ``pass`` are treated as equal. The commit SHA is recorded
in the event ``detail`` so the read-time tally can group by commit.

Exit Codes (ADR-035):
    0 = verdicts match (no K4 emitted)
    1 = verdicts differ (K4 emitted)
    2 = usage error (missing arguments)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parents[1]
sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.ai_review_common.verdict import merge_verdicts  # noqa: E402
from scripts.metrics.kill_criteria import emit_event  # noqa: E402


def verdicts_match(local: str, ci: str) -> bool:
    """Return True when two verdicts collapse to the same canonical outcome."""
    return _canonical_verdict(local) == _canonical_verdict(ci)


def _canonical_verdict(verdict: str) -> str:
    """Return a non-secret verdict label for telemetry detail."""
    token = verdict.strip().upper()
    return merge_verdicts([token])


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="emit_verdict_mismatch",
        description="Emit a K4 event when local and CI /review verdicts disagree.",
    )
    parser.add_argument("--commit", required=True, help="Commit SHA under review.")
    parser.add_argument("--local", required=True, help="Local /review verdict.")
    parser.add_argument("--ci", required=True, help="CI /review verdict.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Compare verdicts; emit K4 and fail when they diverge."""
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    if verdicts_match(args.local, args.ci):
        print("verdicts match; no K4 event emitted.")
        return 0
    detail = (
        f"verdict mismatch commit={args.commit} "
        f"local={_canonical_verdict(args.local)} ci={_canonical_verdict(args.ci)}"
    )
    try:
        emit_event("K4", detail)
    except OSError as exc:
        print(f"warning: verdict mismatch; could not emit K4 event: {exc}", file=sys.stderr)
        return 1
    print("verdict MISMATCH; K4 kill-criteria event emitted.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
