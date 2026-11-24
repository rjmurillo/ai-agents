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
import hashlib
import importlib
import json
import logging
import math
import os
import re
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.eval.actionability_corpus import (  # noqa: E402
    DEFAULT_SEED,
    load_jsonl,
    write_jsonl,
)
from scripts.eval.actionability_io import atomic_write_text  # noqa: E402
from scripts.eval.actionability_labels import (  # noqa: E402
    SPLIT_DEV,
    SPLIT_HELDOUT,
    STATUS_CALL_ERROR,
    STATUS_OK,
    STATUS_PARSE_ERROR,
    STATUSES,
)
from scripts.eval.actionability_score import ScoreInputError, build_report  # noqa: E402

logger = logging.getLogger(__name__)

PROMPT_PATH = REPO_ROOT / "evals" / "comment-actionability" / "prompt-v1.md"

# Arm C apply rule: the caller keeps its current threshold
# (update_reviewer_signal_stats.py, spec Call contract).
HEURISTIC_THRESHOLD = 0.5
APPLY_CONFIDENCE = 0.7

# Spec Call contract limits.
MAX_BODY_CHARS = 4000
MAX_REPLIES = 3
MAX_REPLY_CHARS = 500
MAX_REASON_CHARS = 100
MAX_OUTPUT_TOKENS = 100

# Premortem R2: below this many calls a failure rate says nothing.
MIN_ATTEMPTS_FOR_FAILURE_EXIT = 5


API_KEY_ENV = "ANTHROPIC_API_KEY"

_FENCE = re.compile(r"\A```(?:json)?[ \t]*\n(.*)\n```\Z", re.DOTALL)

Complete = Callable[[str], str]


@dataclass(frozen=True, slots=True)
class Verdict:
    """A parsed model verdict."""

    is_actionable: bool
    confidence: float
    reason: str


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
    if prediction.confidence is None or prediction.confidence < APPLY_CONFIDENCE:
        return None
    return prediction.is_actionable


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


def _reject_constant(name: str) -> None:
    raise ValueError(f"non-finite JSON constant {name}")


def _clean_confidence(value: object) -> float | None:
    """Return ``value`` clamped to [0, 1], or None when it is not a finite real number."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    try:
        number = float(value)
    except OverflowError:
        return None
    if not math.isfinite(number):
        return None
    return min(1.0, max(0.0, number))


def _strip_one_fence(text: str) -> str:
    stripped = text.strip()
    match = _FENCE.match(stripped)
    return match.group(1).strip() if match else stripped


def parse_verdict(text: str) -> Verdict | None:
    """Parse a model reply into a Verdict, or None when it breaks the contract.

    Stricter than ``scripts/llm_classification/classifier.py``, which defaults a
    missing ``is_actionable`` to False and ``confidence`` to 0.5 (spec Call
    contract, Output). Here a malformed reply is a failure, not a verdict.
    ``reason`` is not part of the verdict, so a missing or non-string one
    becomes the empty string.
    """
    try:
        data = json.loads(_strip_one_fence(text), parse_constant=_reject_constant)
    except (ValueError, RecursionError):
        return None
    if not isinstance(data, dict):
        return None
    flag = data.get("is_actionable")
    confidence = _clean_confidence(data.get("confidence"))
    if not isinstance(flag, bool) or confidence is None:
        return None
    reason = data.get("reason")
    return Verdict(
        is_actionable=flag,
        confidence=confidence,
        reason=reason[:MAX_REASON_CHARS] if isinstance(reason, str) else "",
    )


def load_prompt() -> tuple[str, str]:
    """Return the system prompt text and the SHA-256 of the prompt file bytes."""
    raw = PROMPT_PATH.read_bytes()
    return raw.decode("utf-8").strip(), hashlib.sha256(raw).hexdigest()


def build_user_message(row: dict[str, Any]) -> str:
    """Build the model input. The heuristic score is logged, never sent."""
    parts = [
        f"File: {row.get('path') or ''}",
        "",
        "<comment>",
        (row.get("body") or "")[:MAX_BODY_CHARS],
        "</comment>",
    ]
    for reply in (row.get("thread_replies") or [])[:MAX_REPLIES]:
        parts += ["", "<reply>", reply[:MAX_REPLY_CHARS], "</reply>"]
    return "\n".join(parts)


def _load_call_api() -> Callable[..., str]:
    """Resolve the shared transport at call time, so importing this module stays cheap."""
    eval_dir = str(Path(__file__).resolve().parent)
    if eval_dir not in sys.path:
        sys.path.insert(0, eval_dir)
    return cast(Callable[..., str], importlib.import_module("_anthropic_api").call_api)


def _predict_one(
    row: dict[str, Any], complete: Complete, clock: Callable[[], float]
) -> dict[str, Any]:
    start = clock()
    try:
        text = complete(build_user_message(row))
    except (RuntimeError, OSError, ValueError) as exc:
        # The class name is recorded, never the message: provider text may carry secrets.
        return {
            "status": STATUS_CALL_ERROR,
            "is_actionable": None,
            "confidence": None,
            "reason": "",
            "latency_s": round(clock() - start, 4),
            "error_type": type(exc).__name__,
        }
    latency = round(clock() - start, 4)
    verdict = parse_verdict(text)
    if verdict is None:
        return {
            "status": STATUS_PARSE_ERROR,
            "is_actionable": None,
            "confidence": None,
            "reason": "",
            "latency_s": latency,
        }
    return {
        "status": STATUS_OK,
        "is_actionable": verdict.is_actionable,
        "confidence": verdict.confidence,
        "reason": verdict.reason,
        "latency_s": latency,
    }


def predict_rows(
    rows: list[dict[str, Any]],
    *,
    complete: Complete,
    provider: str,
    model: str,
    prompt_sha256: str,
    clock: Callable[[], float] = time.monotonic,
) -> list[dict[str, Any]]:
    """Call ``complete`` once per row and return one record per row, failures included."""
    records = []
    for row in rows:
        outcome = _predict_one(row, complete, clock)
        records.append(
            {
                "id": row["id"],
                "status": outcome.pop("status"),
                "is_actionable": outcome.pop("is_actionable"),
                "confidence": outcome.pop("confidence"),
                "reason": outcome.pop("reason"),
                "latency_s": outcome.pop("latency_s"),
                "provider": provider,
                "model": model,
                "prompt_sha256": prompt_sha256,
                **outcome,
            }
        )
    return records


def _effective_provider(provider: str | None) -> str:
    if provider is not None:
        return provider
    return os.environ.get("EVAL_PROVIDER") or "anthropic"


def _predict_config_error(args: argparse.Namespace, api_key: str) -> str | None:
    if not 0.0 <= args.max_failure_rate <= 1.0:
        return "--max-failure-rate must be between 0 and 1"
    if not args.model.strip():
        return "--model must not be empty"
    if not api_key and args.provider is None:
        return f"{API_KEY_ENV} is not set; set it or pass --provider"
    return None


def _failure_exit(records: list[dict[str, Any]], max_rate: float) -> int:
    failures = sum(1 for r in records if r["status"] != STATUS_OK)
    attempted = len(records)
    if attempted >= MIN_ATTEMPTS_FOR_FAILURE_EXIT and failures / attempted > max_rate:
        print(
            f"failure rate {failures}/{attempted} exceeds --max-failure-rate {max_rate}",
            file=sys.stderr,
        )
        return 3
    return 0


def cmd_predict(args: argparse.Namespace) -> int:
    """Call the model on in-band rows of one split and write one record per row."""
    api_key = (os.environ.get(API_KEY_ENV) or "").strip()
    config_error = _predict_config_error(args, api_key)
    if config_error is not None:
        print(f"error: {config_error}", file=sys.stderr)
        return 2
    rows = load_jsonl(args.corpus)
    if rows is None:
        return 2
    selected = [r for r in rows if r.get("in_band") and r.get("split") == args.split]
    if not selected:
        logger.error("no in_band rows in split %r of %s", args.split, args.corpus)
        return 2

    system, digest = load_prompt()
    call_api = _load_call_api()

    def complete(user_message: str) -> str:
        return call_api(
            api_key,
            [{"role": "user", "content": user_message}],
            system=system,
            model=args.model,
            max_tokens=MAX_OUTPUT_TOKENS,
            temperature=0.0,
            provider=args.provider,
        )

    records = predict_rows(
        selected,
        complete=complete,
        provider=_effective_provider(args.provider),
        model=args.model,
        prompt_sha256=digest,
    )
    write_jsonl(args.output, records)
    counts = {s: sum(1 for r in records if r["status"] == s) for s in STATUSES}
    print(
        f"attempted {len(records)}: ok {counts[STATUS_OK]}, "
        f"parse_error {counts[STATUS_PARSE_ERROR]}, call_error {counts[STATUS_CALL_ERROR]}"
    )
    return _failure_exit(records, args.max_failure_rate)


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
    print(
        f"verdict {report['verdict']}: gap {report['gap']:.4f} "
        f"(95% CI {low:.4f} to {high:.4f}) over {report['heldout_band']['n']} heldout band rows, "
        f"best baseline {report['best_baseline']}"
    )
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    predict = sub.add_parser("predict", help="Call a model on the in-band rows of one split")
    predict.add_argument("--corpus", type=Path, required=True, help="Corpus JSONL")
    predict.add_argument("--split", choices=(SPLIT_DEV, SPLIT_HELDOUT), required=True)
    predict.add_argument("--provider", default=None, help="Provider name passed to call_api")
    predict.add_argument("--model", required=True, help="Model id (no default)")
    predict.add_argument("--output", type=Path, required=True, help="Predictions JSONL to write")
    predict.add_argument("--max-failure-rate", type=float, default=0.5)
    predict.set_defaults(handler=cmd_predict)

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
