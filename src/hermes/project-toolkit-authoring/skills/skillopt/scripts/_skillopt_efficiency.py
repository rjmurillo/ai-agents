"""Efficiency gate: accept a pre-declared cost, latency, or token gain.

`pair-gate` rejects a candidate that adds no held-out pass, even when it is
cheaper. When the incumbent already passes every `sel` task, this gate decides
a pre-declared efficiency claim instead: correctness must hold and the gain
must beat a null control and the run-to-run spread.
"""

from __future__ import annotations

import math
import statistics

from _skillopt_gates import _assert_selection_usable, _split_task_ids
from _skillopt_patching import SkillOptError

EFFICIENCY_DIRECTIONS = ("lower", "higher")
SAFETY_KIND = "safety"
MEASUREMENT_ARMS = ("incumbent", "candidate", "null")
# With 2 repeats the median equals the mean, so one lucky repeat moves it.
# Three is the smallest count where the median ignores a single outlier.
MIN_REPEATS_FLOOR = 3
# Only a run on this split can support promotion, so every safety task must sit in it.
PROMOTION_SPLIT = "sel"


def _efficiency_spec(eval_set: dict) -> dict:
    """Validate the eval set's pre-declared `efficiency` objective.

    The objective lives in the frozen eval manifest so it is fixed before the
    candidate is authored. A missing or malformed declaration is a usage error,
    not a reject: without it there is no claim to gate.
    """
    spec = eval_set.get("efficiency")
    if not isinstance(spec, dict):
        raise SkillOptError("eval set has no 'efficiency' objective; declare it before gating")
    metric = spec.get("metric")
    if not isinstance(metric, str) or not metric:
        raise SkillOptError("efficiency.metric must be a nonempty string")
    if spec.get("direction") not in EFFICIENCY_DIRECTIONS:
        raise SkillOptError(f"efficiency.direction must be one of {EFFICIENCY_DIRECTIONS}")
    for key in ("min_relative_gain", "null_tolerance"):
        value = spec.get(key)
        if not _is_number(value) or not 0 < value < 1:
            raise SkillOptError(f"efficiency.{key} must be a number in (0, 1)")
    if spec["null_tolerance"] >= spec["min_relative_gain"]:
        raise SkillOptError(
            "efficiency.null_tolerance must be below efficiency.min_relative_gain; "
            "otherwise the null control cannot rule out noise at the claimed gain"
        )
    repeats = spec.get("min_repeats")
    if isinstance(repeats, bool) or not isinstance(repeats, int) or repeats < MIN_REPEATS_FLOOR:
        raise SkillOptError(f"efficiency.min_repeats must be an integer >= {MIN_REPEATS_FLOOR}")
    return spec


def _is_number(value: object) -> bool:
    """True for a finite int or float. bool is not a measurement.

    An int too large for a float (a 400-digit JSON integer) makes isfinite raise
    OverflowError. That is bad input, not a crash, so it is not a number.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _correctness_findings(
    eval_set: dict, task_ids: list[str], incumbent: dict, candidate: dict
) -> dict:
    """Unverified, below-ceiling, regressed, and failed-safety task ids, in split order.

    A task is below the ceiling when the incumbent has a real result and it is
    False. Efficiency is the claim for an incumbent that already passes every
    task, so a failing incumbent task means the claim does not apply.
    """
    kinds = eval_set.get("tasks", {})
    unverified = [
        tid
        for tid in task_ids
        if not isinstance(incumbent.get(tid), bool) or not isinstance(candidate.get(tid), bool)
    ]
    below_ceiling = [tid for tid in task_ids if incumbent.get(tid) is False]
    regressions = [
        tid for tid in task_ids if incumbent.get(tid) is True and candidate.get(tid) is not True
    ]
    safety_failures = [
        tid
        for tid in task_ids
        if isinstance(kinds.get(tid), dict)
        and kinds[tid].get("kind") == SAFETY_KIND
        and candidate.get(tid) is not True
    ]
    return {
        "unverified": unverified,
        "below_ceiling": below_ceiling,
        "regressions": regressions,
        "safety_failures": safety_failures,
    }


def _require_safety_tasks_in_split(eval_set: dict, task_ids: list[str]) -> None:
    """Refuse to gate when a kind "safety" task sits outside the promotion split.

    The gate checks only the tasks in the split. A safety task left out would
    never be checked, so promotion would pass with its failure unseen.
    """
    in_split = set(task_ids)
    missing = [
        tid
        for tid, task in eval_set.get("tasks", {}).items()
        if isinstance(task, dict) and task.get("kind") == SAFETY_KIND and tid not in in_split
    ]
    if missing:
        raise SkillOptError(
            f"safety tasks {sorted(missing)} are not in the '{PROMOTION_SPLIT}' split; "
            "the gate would not check them. Add them to the split"
        )


def _arm_summary(
    measurements: dict, arm: str, task_ids: list[str], min_repeats: int
) -> tuple[dict[str, dict[str, float]], str | None]:
    """Per-task stats for one arm, or (empty, reason) when the arm is untrusted.

    Each task maps to median, mean, min, max, and repeat count. The median
    resists one lucky repeat. The mean sees a heavy upper tail that the median
    hides. The min and max bound the spread, so the gate can tell a real gain
    from two overlapping ranges. Every stat is a float, so summed totals across
    tasks overflow to inf (caught by the caller) instead of raising on big ints.
    """
    arm_data = measurements.get(arm)
    if not isinstance(arm_data, dict):
        return {}, "measurements_missing"
    stats: dict[str, dict[str, float]] = {}
    short = False
    for tid in task_ids:
        values = arm_data.get(tid)
        if not isinstance(values, list) or not values:
            return {}, "measurements_missing"
        if not all(_is_number(v) and v >= 0 for v in values):
            return {}, "measurements_invalid"
        short = short or len(values) < min_repeats
        try:
            stats[tid] = {
                "median": float(statistics.median(values)),
                "mean": statistics.fmean(values),
                "min": float(min(values)),
                "max": float(max(values)),
                "repeats": len(values),
            }
        except OverflowError:
            return {}, "measurements_invalid"
    return stats, ("measurements_short" if short else None)


def _relative_gain(base: dict[str, float], other: dict[str, float], direction: str) -> float:
    """Relative gain of `other` over `base` on the summed per-task medians."""
    base_total = sum(base.values())
    other_total = sum(other.values())
    delta = base_total - other_total if direction == "lower" else other_total - base_total
    return delta / base_total


def _efficiency_reasons(
    spec: dict, task_ids: list[str], measurements: dict
) -> tuple[list[str], dict]:
    """Reason codes for the measurement half of the gate, plus the numbers behind them."""
    stats: dict[str, dict[str, dict[str, float]]] = {}
    reasons: list[str] = []
    for arm in MEASUREMENT_ARMS:
        stats[arm], problem = _arm_summary(measurements, arm, task_ids, spec["min_repeats"])
        if problem and problem not in reasons:
            reasons.append(problem)
    if reasons:
        return reasons, {}
    if any(len({stats[arm][tid]["repeats"] for arm in MEASUREMENT_ARMS}) > 1 for tid in task_ids):
        return ["measurements_unmatched"], {}

    def total(arm: str, key: str) -> float:
        return sum(stats[arm][tid][key] for tid in task_ids)

    keys = ("median", "mean", "min", "max")
    if not all(math.isfinite(total(arm, key)) for arm in MEASUREMENT_ARMS for key in keys):
        return ["measurements_invalid"], {}
    if total("incumbent", "median") <= 0 or total("incumbent", "mean") <= 0:
        return ["measurements_invalid"], {}
    direction = spec["direction"]
    medians = {arm: {tid: stats[arm][tid]["median"] for tid in task_ids} for arm in stats}
    means = {arm: {tid: stats[arm][tid]["mean"] for tid in task_ids} for arm in stats}
    gain = _relative_gain(medians["incumbent"], medians["candidate"], direction)
    null_gain = _relative_gain(medians["incumbent"], medians["null"], direction)
    mean_gain = _relative_gain(means["incumbent"], means["candidate"], direction)
    null_mean_gain = _relative_gain(means["incumbent"], means["null"], direction)
    worst_case_gain = _worst_case_gain(stats, task_ids, direction)
    noisy_null = _noisy_null_tasks(stats, task_ids, spec["null_tolerance"])
    if max(abs(null_gain), abs(null_mean_gain)) > spec["null_tolerance"] or noisy_null:
        reasons.append("null_too_wide")
    if gain < spec["min_relative_gain"]:
        reasons.append("gain_below_threshold")
    if gain <= abs(null_gain):
        reasons.append("gain_within_null")
    if gain >= spec["min_relative_gain"] and mean_gain < spec["min_relative_gain"]:
        reasons.append("mean_gain_below_threshold")
    if mean_gain <= abs(null_mean_gain):
        reasons.append("mean_gain_within_null")
    if worst_case_gain is None or worst_case_gain <= 0:
        reasons.append("gain_within_spread")
    per_task = {tid: _task_gain(medians, tid, direction) for tid in task_ids}
    regressed = [
        tid
        for tid, task_gain in per_task.items()
        if _task_regressed(medians, tid, task_gain, direction, spec["null_tolerance"])
    ]
    if regressed:
        reasons.append("task_cost_regression")
    return reasons, {
        "gain": gain,
        "mean_gain": mean_gain,
        "null_gain": null_gain,
        "null_mean_gain": null_mean_gain,
        "worst_case_gain": worst_case_gain,
        "per_task_gain": per_task,
        "task_cost_regressions": regressed,
        "null_wide_tasks": noisy_null,
    }


def _noisy_null_tasks(
    stats: dict[str, dict[str, dict[str, float]]], task_ids: list[str], tolerance: float
) -> list[str]:
    """Task ids where the null arm's median or mean strays from the incumbent's.

    The summed null check lets large offsetting outliers on different tasks
    cancel, so the noisy run passes. Bounding each task closes that. A zero
    incumbent has no relative scale, so any nonzero null value is too wide.
    """
    wide = []
    for tid in task_ids:
        base = stats["incumbent"][tid]
        null = stats["null"][tid]
        for key in ("median", "mean"):
            if base[key] == 0:
                off = null[key] != 0
            else:
                off = abs(null[key] - base[key]) / base[key] > tolerance
            if off:
                wide.append(tid)
                break
    return wide


def _worst_case_gain(
    stats: dict[str, dict[str, dict[str, float]]], task_ids: list[str], direction: str
) -> float | None:
    """Gain of the candidate's worst repeats over the incumbent's best repeats.

    Positive only when the two ranges do not overlap on the summed total, so a
    saving smaller than the run-to-run spread cannot pass. None when the
    incumbent's best total is 0, where a relative gain is undefined; the
    caller treats None as overlapping.
    """
    best, worst = ("min", "max") if direction == "lower" else ("max", "min")
    base = sum(stats["incumbent"][tid][best] for tid in task_ids)
    other = sum(stats["candidate"][tid][worst] for tid in task_ids)
    if base <= 0:
        return None
    delta = base - other if direction == "lower" else other - base
    return delta / base


def _task_regressed(
    medians: dict[str, dict[str, float]],
    tid: str,
    task_gain: float | None,
    direction: str,
    tolerance: float,
) -> bool:
    """True when one task got worse by more than the null tolerance.

    A zero incumbent median has no relative gain. For `lower` any positive
    candidate median is a regression from zero; for `higher` zero cannot fall.
    """
    if task_gain is None:
        return direction == "lower" and medians["candidate"][tid] > 0
    return task_gain < -tolerance


def _task_gain(medians: dict[str, dict[str, float]], tid: str, direction: str) -> float | None:
    """Relative candidate gain on one task, None when the incumbent median is zero."""
    base = medians["incumbent"][tid]
    if base == 0:
        return None
    return _relative_gain({tid: base}, {tid: medians["candidate"][tid]}, direction)


def efficiency_gate(
    eval_set: dict,
    incumbent_results: dict,
    candidate_results: dict,
    measurements: dict,
    split: str = "sel",
) -> dict:
    """Accept a pre-declared efficiency gain only when correctness holds and it beats noise.

    This is a separate path from pair_gate, which stays the default and still
    requires a new pass. Like pair_gate, on the "sel" split it refuses exposed
    or invalid tasks (`_assert_selection_usable`), so a leaked task cannot
    back an accept.
    Use it when the candidate sits at the accuracy ceiling and the claim is
    cost, latency, or tokens.

    Inputs:
      eval_set["efficiency"] : {metric, direction ("lower"|"higher"),
                                min_relative_gain, null_tolerance, min_repeats}
                               declared in the frozen manifest before the
                               candidate is authored;
      measurements           : {"incumbent": {task: [v, ...]}, "candidate": {...},
                                "null": {...}}, where "null" is a rerun of the
                               byte-identical incumbent, measured the same way.

    ACCEPT_EFFICIENCY needs all of:
      - every split task has a real boolean result in both result sets;
      - on the promotion split ("sel"), every task with kind "safety" is in
        the split, else SkillOptError (exit 2): a safety task outside the gated
        split would go unchecked;
      - the incumbent passes every split task (the accuracy ceiling), so the
        claim is cost and not a quiet trade of correctness;
      - zero regressions (no incumbent pass lost), so candidate passes >= incumbent;
      - every task with kind "safety" passes in the candidate;
      - at least min_repeats measurements per task, and the same count for a
        task in all three arms (else measurements_unmatched);
      - |null gain| and |null mean gain| <= null_tolerance, so a heavy tail in
        the byte-identical rerun also marks the metric as too noisy;
      - gain >= min_relative_gain and gain > |null gain|;
      - mean_gain >= min_relative_gain and mean_gain > |null mean gain|, so a
        heavy upper tail the median hides cannot pass as a saving;
      - worst_case_gain > 0: the candidate's worst repeats beat the
        incumbent's best repeats on the summed total, so a saving inside the
        run-to-run spread cannot pass;
      - no task got worse by more than null_tolerance (task_cost_regression),
        so one large task cannot hide a regression on a small one.
    Anything else is REJECT with the matching codes in "reasons". Gain is the
    relative change of the summed per-task medians; mean_gain and
    null_mean_gain are the same formula on the summed per-task means;
    worst_case_gain uses the summed per-task min (incumbent) and max
    (candidate) for direction "lower", swapped for "higher"; per_task_gain and
    task_cost_regressions name the tasks paying for the rest.
    """
    task_ids = _split_task_ids(eval_set, split)
    spec = _efficiency_spec(eval_set)
    if not isinstance(eval_set.get("tasks", {}), dict):
        raise SkillOptError("eval set 'tasks' must be an object keyed by task id")
    if split == PROMOTION_SPLIT:
        _assert_selection_usable(eval_set, task_ids)
        _require_safety_tasks_in_split(eval_set, task_ids)
    findings = _correctness_findings(eval_set, task_ids, incumbent_results, candidate_results)
    reasons: list[str] = []
    for code, key in (
        ("unverified_correctness", "unverified"),
        ("incumbent_below_ceiling", "below_ceiling"),
        ("correctness_regression", "regressions"),
        ("safety_failure", "safety_failures"),
    ):
        if findings[key]:
            reasons.append(code)
    measured, numbers = _efficiency_reasons(spec, task_ids, measurements)
    reasons.extend(measured)
    accepted = not reasons
    return {
        "accepted": accepted,
        "verdict": "ACCEPT_EFFICIENCY" if accepted else "REJECT",
        "reasons": reasons,
        "split": split,
        "metric": spec["metric"],
        "direction": spec["direction"],
        "min_relative_gain": spec["min_relative_gain"],
        "null_tolerance": spec["null_tolerance"],
        "min_repeats": spec["min_repeats"],
        "selection_tasks": len(task_ids),
        **findings,
        **numbers,
    }
