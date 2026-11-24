"""Metrics, paired bootstrap, and report building for the actionability eval.

Plan task M1-T15. Called by the ``score`` subcommand of ``actionability_arms.py``.
The arm functions are passed in, so this module has no dependency on the arms
module and never rescores a comment: it reads only what the corpus and the
predictions files already hold (premortem R1).

Verdict rule (owner decision D1; spec, Eval method and kill criterion 2):

* pass:         gap >= 0.10 and ci_low > 0
* fail:         ci_high < 0.10. Only this proves the gain is below the bar.
* inconclusive: everything else, including a gap under 0.10 whose interval still
  reaches 0.10, and a gap of 0.10 or more whose interval reaches 0.

The one-time extension is look 2. It widens the interval from 95 to 97.5 percent
(1.25th to 98.75th percentile, Bonferroni over two looks). An inconclusive result at look 2
is final and does not fire kill criterion 2.
"""

from __future__ import annotations

import math
import random
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from scripts.eval.actionability_labels import (
    LABEL_TRUTH,
    LABEL_UNSURE,
    PROVENANCE_FIELDS,
    SPLIT_HELDOUT,
    SPLIT_OUTSIDE,
    STATUS_OK,
    STATUSES,
)
from scripts.eval.actionability_validate import (
    PREDICTION_CHECKS,
    SCORE_CORPUS_CHECKS,
    Check,
    RecordError,
    validate_records,
)

Arm = Callable[[dict[str, Any], dict[str, Any] | None], bool]

CORPUS_PROVENANCE_FIELDS = ("corpus_seed", "corpus_head_sha")

PASS_GAP = 0.10
ASSUMED_DISCORDANCE = (0.1, 0.2, 0.3)
# Two-sided alpha 0.05 and 80 percent power: z(0.975) + z(0.80).
Z_ALPHA_PLUS_Z_BETA = 1.96 + 0.8416

# Bootstrap percentile cuts per look. Look 2 splits alpha 0.05 over two looks, so each look
# gets 0.025 two-sided: the 1.25th to 98.75th percentile, a 97.5 percent interval.
LOOKS = (1, 2)
CI_PERCENTILES = {1: (2.5, 97.5), 2: (1.25, 98.75)}
CI_LEVELS = {1: 0.95, 2: 0.975}

BASELINES = ("A", "B")


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


def ci_percentiles(look: int) -> tuple[float, float]:
    """Return the (low, high) percentile cuts for ``look``. Raises ValueError otherwise."""
    if look not in CI_PERCENTILES:
        raise ValueError(f"look must be one of {LOOKS}, got {look!r}")
    return CI_PERCENTILES[look]


def paired_bootstrap_ci(
    diffs: Sequence[int], seed: int, iterations: int, look: int = 1
) -> tuple[float, float] | None:
    """CI on the mean of per-row C-minus-best correctness differences.

    The best baseline is chosen once, from the point estimate, before this runs.
    Each iteration resamples rows with replacement and recomputes the mean. The
    bounds are nearest-rank percentiles of those means: 2.5th and 97.5th at look 1,
    1.25th and 98.75th at look 2. The same seed gives the same means at both looks, so
    the look-2 interval always contains the look-1 interval.
    """
    return _bootstrap_bounds(diffs, seed, iterations, look) if diffs else None


def _bootstrap_bounds(
    diffs: Sequence[int], seed: int, iterations: int, look: int = 1
) -> tuple[float, float]:
    low_pct, high_pct = ci_percentiles(look)
    n = len(diffs)
    rng = random.Random(seed)
    means = sorted(sum(rng.choices(diffs, k=n)) / n for _ in range(iterations))
    return _rank_value(means, low_pct), _rank_value(means, high_pct)


def verdict(gap: float, ci_low: float, ci_high: float) -> str:
    """Apply the verdict rule: pass, fail, or inconclusive.

    Fail needs ``ci_high < PASS_GAP``: only an interval that lies wholly under the bar proves
    the gain is below it. A small gap whose interval still reaches the bar is inconclusive.
    """
    if gap >= PASS_GAP and ci_low > 0:
        return "pass"
    if ci_high < PASS_GAP:
        return "fail"
    return "inconclusive"


def kill_criterion_2(result: str, look: int) -> str:
    """fired only on fail. Inconclusive is pending at look 1 and not fired at look 2."""
    if result == "fail":
        return "fired"
    if result == "inconclusive" and look == LOOKS[0]:
        return "pending"
    return "not_fired"


def is_final(result: str, look: int) -> bool:
    """A result is final unless it is inconclusive at look 1, which may take the one extension."""
    return result != "inconclusive" or look == LOOKS[-1]


def _validate(records: list[dict[str, Any]], checks: Sequence[Check], where: str) -> None:
    try:
        validate_records(records, checks, where)
    except RecordError as exc:
        raise ScoreInputError(str(exc)) from None


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
    look: int,
) -> dict[str, Any]:
    n = len(items)
    truth = [t for _, t in items]
    correct = _correct_counts(_subset_arm_outputs(items, by_id, arms), truth)
    totals = {name: sum(flags) for name, flags in correct.items()}
    best = "B" if totals["B"] > totals["A"] else "A"
    gap = gap_from_counts(totals["C"], totals[best], n)
    diffs = [c - b for c, b in zip(correct["C"], correct[best], strict=True)]
    interval = _bootstrap_bounds(diffs, seed, iterations, look)
    discordance = sum(1 for d in diffs if d) / n
    result = verdict(gap, interval[0], interval[1])
    return {
        "best_baseline": best,
        "gap": gap,
        "gap_ci": list(interval),
        "gap_ci_level": CI_LEVELS[look],
        "look": look,
        "verdict": result,
        "final": is_final(result, look),
        "kill_criterion_2": kill_criterion_2(result, look),
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


def _latency_section(predictions: list[dict[str, Any]], scored_ids: set[str]) -> dict[str, Any]:
    """p50 and p95 of ok calls made for the scored heldout band rows only."""
    ok = [
        record["latency_s"]
        for record in predictions
        if record["id"] in scored_ids
        and record["status"] == STATUS_OK
        and record.get("latency_s") is not None
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
    look: int = 1,
) -> dict[str, Any]:
    """Score the arms on labeled rows. Raises ScoreInputError when inputs cannot be scored."""
    if look not in LOOKS:
        raise ScoreInputError(f"look must be one of {LOOKS}, got {look!r}")
    _validate(rows, SCORE_CORPUS_CHECKS, "corpus")
    _validate(predictions, PREDICTION_CHECKS, "predictions")
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
        **_gap_section(band, by_id, arms, seed, iterations, look),
        "predictions": _prediction_counts(band, by_id),
        "latency_s": _latency_section(predictions, {row["id"] for row, _ in band}),
    }
