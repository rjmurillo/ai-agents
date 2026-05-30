#!/usr/bin/env python3
"""Aggregate gate verdicts, requiring at least one externally-grounded signal.

Per issue #1855, no quality gate may pass solely on an LLM verdict. This
helper reads a list of ``signal=verdict`` pairs (one per ``--signal`` flag) and
emits a final gate verdict, refusing to return ``PASS`` if every passing
signal originated from an LLM judge.

Signal kinds (case-insensitive):

* ``external`` -- deterministic tools (pytest, lint, codeql, markdownlint,
  acceptance-criteria extractor, etc.).
* ``llm`` -- agent judgments (security agent, qa agent, critic, analyst...).

Verdicts (per existing ai_review_common.verdict vocabulary):
``PASS, WARN, FAIL, CRITICAL_FAIL, REJECTED, NEEDS_REVIEW, UNKNOWN``.

Exit codes (ADR-035):

* 0 - final verdict is PASS or WARN
* 1 - final verdict is FAIL/CRITICAL_FAIL/REJECTED/NEEDS_REVIEW, OR no
      external signal was provided (closed-loop refusal)
* 2 - bad invocation
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from typing import Iterable

_BLOCKING = {"CRITICAL_FAIL", "REJECTED", "FAIL"}
_WARNING = {"WARN", "NEEDS_REVIEW"}
_PASSING = {"PASS"}
_KNOWN = _BLOCKING | _WARNING | _PASSING | {"UNKNOWN"}

_VALID_KINDS = {"external", "llm"}


@dataclass(frozen=True)
class Signal:
    kind: str  # 'external' | 'llm'
    name: str
    verdict: str


def parse_signal(spec: str) -> Signal:
    """Parse ``kind:name=VERDICT`` (e.g. ``external:pytest=PASS``)."""

    if "=" not in spec or ":" not in spec.split("=", 1)[0]:
        raise ValueError(
            f"signal must be 'kind:name=VERDICT', got {spec!r}"
        )
    head, verdict = spec.split("=", 1)
    kind, name = head.split(":", 1)
    kind = kind.strip().lower()
    name = name.strip()
    verdict = verdict.strip().upper()
    if kind not in _VALID_KINDS:
        raise ValueError(f"unknown signal kind {kind!r}; expected one of {_VALID_KINDS}")
    if not name:
        raise ValueError(f"signal {spec!r} is missing a name")
    if verdict not in _KNOWN:
        raise ValueError(
            f"unknown verdict {verdict!r} for signal {name!r}; "
            f"expected one of {sorted(_KNOWN)}"
        )
    return Signal(kind=kind, name=name, verdict=verdict)


def aggregate(signals: Iterable[Signal]) -> tuple[str, str]:
    """Return ``(final_verdict, reason)`` from a collection of signals.

    Rules:

    1. Any blocking verdict (FAIL/CRITICAL_FAIL/REJECTED) -> that verdict wins
       (most severe). This holds regardless of signal kind.
    2. Otherwise, **at least one ``external`` signal must be present and
       passing/warning**. If every signal is an ``llm`` judgment, the result
       is forced to ``NEEDS_REVIEW`` with reason ``closed-loop``. This is the
       core rule from issue #1855.
    3. Any UNKNOWN verdict from any signal is treated as NEEDS_REVIEW. An
       UNKNOWN verdict means the tool could not determine a result; allowing it
       to silently resolve to PASS is a correctness and security risk.
    4. Any WARN/NEEDS_REVIEW downgrades a clean PASS to WARN.
    5. Otherwise PASS.
    """

    sigs = list(signals)
    if not sigs:
        return "NEEDS_REVIEW", "no-signals"

    # 1. Severity wins.
    for severity in ("CRITICAL_FAIL", "REJECTED", "FAIL"):
        bad = [s for s in sigs if s.verdict == severity]
        if bad:
            who = ",".join(f"{s.kind}:{s.name}" for s in bad)
            return severity, f"blocking-from:{who}"

    has_external = any(s.kind == "external" for s in sigs)
    if not has_external:
        return "NEEDS_REVIEW", "closed-loop:no-external-signal"

    # External signals must themselves not be UNKNOWN-only.
    external_known = [
        s for s in sigs if s.kind == "external" and s.verdict in (_PASSING | _WARNING)
    ]
    if not external_known:
        return "NEEDS_REVIEW", "closed-loop:external-signal-inconclusive"

    # Any UNKNOWN verdict (from any signal kind) is treated as NEEDS_REVIEW.
    # An UNKNOWN means the tool could not produce a definitive result; silently
    # ignoring it would allow a gate to PASS when a validator failed to run.
    unknown_sigs = [s for s in sigs if s.verdict == "UNKNOWN"]
    if unknown_sigs:
        who = ",".join(f"{s.kind}:{s.name}" for s in unknown_sigs)
        return "NEEDS_REVIEW", f"unknown-verdict-from:{who}"

    if any(s.verdict in _WARNING for s in sigs):
        return "WARN", "warnings-present"

    return "PASS", "all-clear"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(__doc__ or "").splitlines()[0] if __doc__ else ""
    )
    parser.add_argument(
        "--signal",
        action="append",
        default=[],
        metavar="KIND:NAME=VERDICT",
        help="Add a signal; repeat for multiple. e.g. external:pytest=PASS",
    )
    parser.add_argument("--json", action="store_true", help="JSON output.")
    args = parser.parse_args(argv)

    try:
        signals = [parse_signal(s) for s in args.signal]
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    verdict, reason = aggregate(signals)
    payload = {
        "verdict": verdict,
        "reason": reason,
        "signals": [
            {"kind": s.kind, "name": s.name, "verdict": s.verdict} for s in signals
        ],
    }
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"VERDICT: {verdict}")
        print(f"REASON: {reason}")
        for s in signals:
            print(f"  {s.kind}:{s.name}={s.verdict}")

    return 0 if verdict == "PASS" or verdict == "WARN" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
