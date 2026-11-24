#!/usr/bin/env python3
"""Score the three comment-actionability arms against labeled corpus rows.

Plan tasks M1-T13 to M1-T15 of
``.project-toolkit/plans/active/harness-agnostic-llm-fallback.md``. The eval
method is in ``.project-toolkit/specs/SPEC-harness-agnostic-llm-fallback.md``.

Arms:
    A  heuristic as shipped: ``heuristic_score >= 0.5``
    B  heuristic with the tie broken the other way: ``> 0.5``
    C  A, except that an in-band row takes the model verdict when the call
       succeeded and ``confidence >= 0.7``

Every arm reads the ``heuristic_score`` stored in the corpus row. Nothing here
rescores: the production heuristic reads the clock, so a rescore could move a
row in or out of the band (premortem R1).

Subcommands:
    predict  Call a model on the in-band rows of one split.
    score    Score the arms on a labeled corpus and report the gap with a bootstrap CI.

Usage:
    ANTHROPIC_API_KEY=... uv run python scripts/eval/actionability_arms.py predict \\
        --corpus corpus.jsonl --split dev --model MODEL --output predictions.jsonl

Exit codes (ADR-035):
    0 - Done
    2 - Bad argument, missing credential, unreadable input, or a corpus that cannot be scored
    3 - Model calls failed past --max-failure-rate (the output file is still written)
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.eval.actionability_io import atomic_write_text, load_jsonl  # noqa: E402
from scripts.eval.actionability_labels import (  # noqa: E402
    DEFAULT_SEED,
    STATUS_AUTH_ERROR,
    STATUS_CALL_ERROR,
    STATUS_OK,
    STATUS_PARSE_ERROR,
)
from scripts.eval.actionability_predict import register_predict_parser  # noqa: E402
from scripts.eval.actionability_score import ScoreInputError, build_report  # noqa: E402

logger = logging.getLogger(__name__)

HEURISTIC_THRESHOLD = 0.5
APPLY_CONFIDENCE = 0.7


@dataclass(frozen=True, slots=True)
class Prediction:
    """One record from ``predict``. A failed call carries no verdict."""

    id: str
    status: str
    is_actionable: bool | None
    confidence: float | None
    latency_s: float | None

    @classmethod
    def from_dict(cls, record: dict[str, Any]) -> Prediction:
        """Build a Prediction from a predictions JSONL record."""
        return cls(
            id=record["id"],
            status=record["status"],
            is_actionable=record.get("is_actionable"),
            confidence=record.get("confidence"),
            latency_s=record.get("latency_s"),
        )


def arm_a(row: dict[str, Any]) -> bool:
    """Heuristic as shipped: the 0.5 tie counts as actionable."""
    return bool(row["heuristic_score"] >= HEURISTIC_THRESHOLD)


def arm_b(row: dict[str, Any]) -> bool:
    """Heuristic with the tie broken the other way: 0.5 is not actionable."""
    return bool(row["heuristic_score"] > HEURISTIC_THRESHOLD)


def _applied_verdict(row: dict[str, Any], prediction: Prediction | None) -> bool | None:
    """Return the model verdict when arm C applies it, else None."""
    if not row["in_band"] or prediction is None or prediction.status != STATUS_OK:
        return None
    confidence = prediction.confidence
    if isinstance(confidence, bool) or not isinstance(confidence, int | float):
        return None
    if confidence < APPLY_CONFIDENCE:
        return None
    # Only a real bool is a verdict: a hand-edited "no" or 1 must not be applied.
    return prediction.is_actionable if isinstance(prediction.is_actionable, bool) else None


def arm_c(row: dict[str, Any], prediction: Prediction | None) -> bool:
    """Heuristic plus model fallback. Reads the stored score, never rescores."""
    verdict = _applied_verdict(row, prediction)
    return arm_a(row) if verdict is None else verdict


def _arm_c_from_record(row: dict[str, Any], record: dict[str, Any] | None) -> bool:
    return arm_c(row, None if record is None else Prediction.from_dict(record))


# Each arm takes the corpus row and the raw prediction record (or None) for that row.
ARM_FUNCTIONS = {
    "A": lambda row, _record: arm_a(row),
    "B": lambda row, _record: arm_b(row),
    "C": _arm_c_from_record,
}


# Share of heldout band rows without an ok prediction above which score warns.
NON_OK_WARN_SHARE = 0.10


def _auth_part(counts: dict[str, int]) -> str:
    """Name auth_error rows in the score line only when there are any."""
    return f", auth_error {counts[STATUS_AUTH_ERROR]}" if counts[STATUS_AUTH_ERROR] else ""


def _warn_non_ok(counts: dict[str, int], band_n: int) -> None:
    """Warn when more than 10 percent of band rows fell back to the heuristic."""
    non_ok = band_n - counts[STATUS_OK]
    if non_ok > NON_OK_WARN_SHARE * band_n:
        print(
            f"warning: {non_ok} of {band_n} heldout band rows ({non_ok / band_n:.0%}) "
            "have no ok prediction; arm C used the heuristic for them",
            file=sys.stderr,
        )


def cmd_score(args: argparse.Namespace) -> int:
    """Score the arms on a labeled corpus and write the report JSON."""
    if args.bootstrap < 1:
        print("error: --bootstrap must be at least 1", file=sys.stderr)
        return 2
    rows = load_jsonl(args.corpus)
    predictions = load_jsonl(args.predictions)
    if rows is None or predictions is None:
        return 2
    try:
        report = build_report(
            rows, predictions, ARM_FUNCTIONS, seed=args.seed, iterations=args.bootstrap
        )
    except ScoreInputError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    missing = report["predictions"]["missing"]
    if missing:
        print(
            f"warning: {missing} heldout band rows have no prediction; "
            "arm C used the heuristic for them",
            file=sys.stderr,
        )
    atomic_write_text(args.output, json.dumps(report, indent=2) + "\n")
    low, high = report["gap_ci"]
    counts = report["predictions"]
    band_n = report["heldout_band"]["n"]
    print(
        f"verdict {report['verdict']}: gap {report['gap']:.4f} "
        f"(95% CI {low:.4f} to {high:.4f}) over {band_n} heldout band rows, "
        f"best baseline {report['best_baseline']}; "
        f"predictions ok {counts[STATUS_OK]}, parse_error {counts[STATUS_PARSE_ERROR]}, "
        f"call_error {counts[STATUS_CALL_ERROR]}{_auth_part(counts)}, "
        f"missing {counts['missing']} of {band_n}"
    )
    _warn_non_ok(counts, band_n)
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    register_predict_parser(sub)

    score = sub.add_parser("score", help="Score the arms on a labeled corpus")
    score.add_argument("--corpus", type=Path, required=True, help="Labeled corpus JSONL")
    score.add_argument("--predictions", type=Path, required=True, help="predict output JSONL")
    score.add_argument("--output", type=Path, required=True, help="Report JSON to write")
    score.add_argument("--seed", type=int, default=DEFAULT_SEED)
    score.add_argument("--bootstrap", type=int, default=10000, help="Bootstrap iterations")
    score.set_defaults(handler=cmd_score)
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns an exit code."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s", stream=sys.stderr)
    args = _build_parser().parse_args(argv)
    return int(args.handler(args))


if __name__ == "__main__":
    sys.exit(main())
