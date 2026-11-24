"""Metrics, paired bootstrap, and report building for the actionability eval.

Plan task M1-T15. Called by the ``score`` subcommand of ``actionability_arms.py``.
The arm functions are passed in, so this module has no dependency on the arms
module and never rescores a comment: it reads only what the corpus and the
predictions files already hold (premortem R1).

Pass bar (spec, Eval method): arm C beats the better of A and B on held-out band
items by at least 10 points of accuracy, with the bootstrap CI lower bound above 0.
A gap of at least 10 points with a CI that reaches 0 is inconclusive, not a kill.
"""

from __future__ import annotations

import math
import random
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from scripts.eval.actionability_labels import (
    LABEL_TRUTH,
    LABEL_UNSURE,
    SPLIT_DEV,
    SPLIT_HELDOUT,
    SPLIT_OUTSIDE,
    STATUS_OK,
    STATUSES,
)

Arm = Callable[[dict[str, Any], dict[str, Any] | None], bool]

PROVENANCE_FIELDS = ("provider", "model", "prompt_sha256")
CORPUS_PROVENANCE_FIELDS = ("corpus_seed", "corpus_head_sha")

PASS_GAP = 0.10
ASSUMED_DISCORDANCE = (0.1, 0.2, 0.3)
# Two-sided alpha 0.05 and 80 percent power: z(0.975) + z(0.80).
Z_ALPHA_PLUS_Z_BETA = 1.96 + 0.8416

CI_LOW_PERCENTILE = 2.5
CI_HIGH_PERCENTILE = 97.5

BASELINES = ("A", "B")
SPLITS = (SPLIT_DEV, SPLIT_HELDOUT, SPLIT_OUTSIDE)


class ScoreInputError(ValueError):
    """The corpus or predictions cannot be scored. Maps to exit code 2."""


def metrics(predicted: Sequence[bool], truth: Sequence[bool]) -> dict[str, Any]:
    """Accuracy, precision, and recall with actionable as the positive class.

    A zero denominator gives None, not 0.
    """
    if len(predicted) != len(truth):
        raise ValueError(f"length mismatch: {len(predicted)} predicted, {len(truth)} truth")
    n = len(truth)
    pairs = list(zip(predicted, truth, strict=True))
    true_pos = sum(1 for p, t in pairs if p and t)
    false_pos = sum(1 for p, t in pairs if p and not t)
    false_neg = sum(1 for p, t in pairs if not p and t)
    correct = sum(1 for p, t in pairs if p == t)
    return {
        "n": n,
        "accuracy": correct / n if n else None,
        "precision": true_pos / (true_pos + false_pos) if true_pos + false_pos else None,
        "recall": true_pos / (true_pos + false_neg) if true_pos + false_neg else None,
    }


def _rank_value(ordered: Sequence[float], percentile: float) -> float:
    """Value at nearest rank ceil(p/100 * n) of a non-empty, sorted sequence."""
    rank = math.ceil(round(percentile * len(ordered) / 100, 9))
    return ordered[min(len(ordered), max(1, rank)) - 1]


def nearest_rank(values: Sequence[float], percentile: float) -> float | None:
    """Nearest-rank percentile: the value at rank ceil(p/100 * n). None when empty."""
    return _rank_value(sorted(values), percentile) if values else None


def min_detectable_gap(n: int, discordance: float) -> float | None:
    """Smallest accuracy gap a paired test of ``n`` rows detects at 80 percent power.

    ``discordance`` is the share of rows where the two arms differ in correctness.
    """
    if n <= 0:
        return None
    return Z_ALPHA_PLUS_Z_BETA * math.sqrt(discordance / n)


def gap_from_counts(correct_c: int, correct_best: int, n: int) -> float:
    """Accuracy gap from integer counts, so a 6-in-60 gap equals 0.1 with no float drift."""
    if n <= 0:
        raise ValueError("n must be positive")
    return (correct_c - correct_best) / n


def paired_bootstrap_ci(
    diffs: Sequence[int], seed: int, iterations: int
) -> tuple[float, float] | None:
    """95 percent CI on the mean of per-row C-minus-best correctness differences.

    The best baseline is chosen once, from the point estimate, before this runs.
    Each iteration resamples rows with replacement and recomputes the mean. The
    bounds are the nearest-rank 2.5th and 97.5th percentiles of those means.
    """
    return _bootstrap_bounds(diffs, seed, iterations) if diffs else None


def _bootstrap_bounds(diffs: Sequence[int], seed: int, iterations: int) -> tuple[float, float]:
    n = len(diffs)
    rng = random.Random(seed)
    means = sorted(sum(rng.choices(diffs, k=n)) / n for _ in range(iterations))
    return _rank_value(means, CI_LOW_PERCENTILE), _rank_value(means, CI_HIGH_PERCENTILE)


def verdict(gap: float, ci_low: float) -> str:
    """Apply the spec pass bar: pass, inconclusive, or fail."""
    if gap < PASS_GAP:
        return "fail"
    return "pass" if ci_low > 0 else "inconclusive"


def _finite_number(value: object) -> bool:
    """True for a real int or float that is finite. A bool is not a number here."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return False
    try:
        return math.isfinite(float(value))
    except OverflowError:
        return False


def _is_nonempty_str(value: object) -> bool:
    return isinstance(value, str) and bool(value)


def _is_str_or_none(value: object) -> bool:
    return value is None or isinstance(value, str)


def _is_bool_or_none(value: object) -> bool:
    return value is None or isinstance(value, bool)


def _is_number_or_none(value: object) -> bool:
    return value is None or _finite_number(value)


def _is_int_or_none(value: object) -> bool:
    return value is None or (isinstance(value, int) and not isinstance(value, bool))


# (key, predicate, description). Checked against ``record.get(key)``, so an absent key
# fails unless None is allowed. A label of None is handled later as "unlabeled".
_CORPUS_CHECKS = (
    ("id", _is_nonempty_str, "a non-empty string"),
    ("split", lambda v: v in SPLITS, f"one of {', '.join(SPLITS)}"),
    ("in_band", lambda v: isinstance(v, bool), "a bool"),
    ("heuristic_score", _finite_number, "a finite number"),
    ("label", _is_str_or_none, "a string or null"),
    ("corpus_seed", _is_int_or_none, "an int or null"),
    ("corpus_head_sha", _is_str_or_none, "a string or null"),
)
_PREDICTION_CHECKS = (
    ("id", _is_nonempty_str, "a non-empty string"),
    ("status", lambda v: isinstance(v, str), "a string"),
    ("is_actionable", _is_bool_or_none, "a bool or null"),
    ("confidence", _is_number_or_none, "a finite number or null"),
    ("latency_s", _is_number_or_none, "a finite number or null"),
    ("provider", _is_str_or_none, "a string or null"),
    ("model", _is_str_or_none, "a string or null"),
    ("prompt_sha256", _is_str_or_none, "a string or null"),
)


def _validate_records(
    records: list[dict[str, Any]],
    checks: Sequence[tuple[str, Callable[[object], bool], str]],
    where: str,
) -> None:
    """Raise ScoreInputError naming the first record and key that breaks a check."""
    for index, record in enumerate(records, start=1):
        for key, accepts, description in checks:
            if not accepts(record.get(key)):
                raise ScoreInputError(f"{where} row {index}: {key} must be {description}")


def _label_truth(rows: list[dict[str, Any]]) -> tuple[list[tuple[dict[str, Any], bool]], int]:
    """Return (row, truth) pairs with unsure rows dropped, plus the unsure count."""
    unlabeled = sum(1 for r in rows if r.get("label") is None)
    if unlabeled:
        raise ScoreInputError(f"{unlabeled} unlabeled rows; label every row before scoring")
    allowed = {*LABEL_TRUTH, LABEL_UNSURE}
    invalid = sum(1 for r in rows if r["label"] not in allowed)
    if invalid:
        raise ScoreInputError(f"{invalid} rows have an invalid label; use {sorted(allowed)}")
    kept = [(r, LABEL_TRUTH[r["label"]]) for r in rows if r["label"] != LABEL_UNSURE]
    if rows and not kept:
        raise ScoreInputError("every label is unsure; nothing to score")
    return kept, len(rows) - len(kept)


def _index_predictions(predictions: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    if not predictions:
        raise ScoreInputError("no predictions; arm C would silently equal arm A")
    by_id: dict[str, dict[str, Any]] = {}
    for record in predictions:
        if record["id"] in by_id:
            raise ScoreInputError(f"duplicate prediction for row {record['id']}")
        if record["status"] not in STATUSES:
            raise ScoreInputError(f"unknown prediction status {record['status'][:40]!r}")
        by_id[record["id"]] = record
    return by_id


def _provenance(predictions: list[dict[str, Any]]) -> dict[str, Any]:
    """Return the single provider, model, and prompt hash, or raise when they mix."""
    found: dict[str, Any] = {}
    for field in PROVENANCE_FIELDS:
        values = {record.get(field) for record in predictions}
        if len(values) > 1:
            raise ScoreInputError(f"predictions mix more than one {field}")
        found[field] = values.pop()
    return found


def _subset_arm_outputs(
    items: list[tuple[dict[str, Any], bool]],
    by_id: Mapping[str, dict[str, Any]],
    arms: Mapping[str, Arm],
) -> dict[str, list[bool]]:
    return {
        name: [arm(row, by_id.get(row["id"])) for row, _ in items] for name, arm in arms.items()
    }


def _subset_report(
    items: list[tuple[dict[str, Any], bool]],
    by_id: Mapping[str, dict[str, Any]],
    arms: Mapping[str, Arm],
) -> dict[str, Any]:
    truth = [t for _, t in items]
    outputs = _subset_arm_outputs(items, by_id, arms)
    return {
        "n": len(items),
        "arms": {name: metrics(out, truth) for name, out in outputs.items()},
    }


def _correct_counts(
    outputs: Mapping[str, list[bool]], truth: Sequence[bool]
) -> dict[str, list[int]]:
    return {
        name: [int(p == t) for p, t in zip(out, truth, strict=True)]
        for name, out in outputs.items()
    }


def _gap_section(
    items: list[tuple[dict[str, Any], bool]],
    by_id: Mapping[str, dict[str, Any]],
    arms: Mapping[str, Arm],
    seed: int,
    iterations: int,
) -> dict[str, Any]:
    n = len(items)
    truth = [t for _, t in items]
    correct = _correct_counts(_subset_arm_outputs(items, by_id, arms), truth)
    totals = {name: sum(flags) for name, flags in correct.items()}
    best = "B" if totals["B"] > totals["A"] else "A"
    gap = gap_from_counts(totals["C"], totals[best], n)
    diffs = [c - b for c, b in zip(correct["C"], correct[best], strict=True)]
    interval = _bootstrap_bounds(diffs, seed, iterations)
    discordance = sum(1 for d in diffs if d) / n
    return {
        "best_baseline": best,
        "gap": gap,
        "gap_ci": list(interval),
        "verdict": verdict(gap, interval[0]),
        "minimum_detectable_gap": {
            "assumed": {str(d): min_detectable_gap(n, d) for d in ASSUMED_DISCORDANCE},
            "observed": {"discordance": discordance, "gap": min_detectable_gap(n, discordance)},
        },
    }


def _prediction_counts(
    band: list[tuple[dict[str, Any], bool]], by_id: Mapping[str, dict[str, Any]]
) -> dict[str, int]:
    counts = {status: 0 for status in STATUSES}
    counts["missing"] = 0
    for row, _ in band:
        record = by_id.get(row["id"])
        if record is None:
            counts["missing"] += 1
        else:
            counts[record["status"]] += 1
    return counts


def _latency_section(predictions: list[dict[str, Any]]) -> dict[str, Any]:
    ok = [
        record["latency_s"]
        for record in predictions
        if record["status"] == STATUS_OK and record.get("latency_s") is not None
    ]
    return {"p50": nearest_rank(ok, 50), "p95": nearest_rank(ok, 95), "n_ok": len(ok)}


def _require_scorable_band(
    rows: list[dict[str, Any]],
    band: list[tuple[dict[str, Any], bool]],
    by_id: Mapping[str, dict[str, Any]],
) -> None:
    """Raise when the heldout band is empty, all unsure, or matches no prediction."""
    if not band:
        if any(r["split"] == SPLIT_HELDOUT and r["in_band"] for r in rows):
            raise ScoreInputError("every heldout band label is unsure; nothing to score")
        raise ScoreInputError("no heldout band rows to score")
    if not any(row["id"] in by_id for row, _ in band):
        raise ScoreInputError(
            "no prediction matches a heldout band row; the predictions may be for "
            "another split (dev) or another corpus"
        )


def _corpus_provenance(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Return the sampling seed and head every row agrees on, or raise when they differ.

    A row that lacks the field counts as a different value from a row that has it.
    """
    found: dict[str, Any] = {}
    for field in CORPUS_PROVENANCE_FIELDS:
        values = {row.get(field) for row in rows}
        if len(values) > 1:
            raise ScoreInputError(f"corpus rows disagree on {field}")
        found[field] = values.pop() if values else None
    return found


def build_report(
    rows: list[dict[str, Any]],
    predictions: list[dict[str, Any]],
    arms: Mapping[str, Arm],
    *,
    seed: int,
    iterations: int,
) -> dict[str, Any]:
    """Score the arms on labeled rows. Raises ScoreInputError when inputs cannot be scored."""
    _validate_records(rows, _CORPUS_CHECKS, "corpus")
    _validate_records(predictions, _PREDICTION_CHECKS, "predictions")
    corpus_provenance = _corpus_provenance(rows)
    labeled, unsure = _label_truth(rows)
    by_id = _index_predictions(predictions)
    provenance = _provenance(predictions)
    band = [(r, t) for r, t in labeled if r["split"] == SPLIT_HELDOUT and r["in_band"]]
    _require_scorable_band(rows, band, by_id)
    non_dev = [(r, t) for r, t in labeled if r["split"] in (SPLIT_HELDOUT, SPLIT_OUTSIDE)]
    return {
        "seed": seed,
        "bootstrap_iterations": iterations,
        **provenance,
        **corpus_provenance,
        "labels": {"unsure_dropped": unsure, "scored": len(labeled)},
        "heldout_band": _subset_report(band, by_id, arms),
        "non_dev": _subset_report(non_dev, by_id, arms),
        **_gap_section(band, by_id, arms, seed, iterations),
        "predictions": _prediction_counts(band, by_id),
        "latency_s": _latency_section(predictions),
    }
