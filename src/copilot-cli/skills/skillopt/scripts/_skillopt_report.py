"""Read-only run report: per-task evidence, benchmark spread, and case signals.

`pair-gate` decides. This report explains. It never changes a verdict and is
not an acceptance input.

It mirrors `bootstrap_eval.py score` in the skill-bootstrap skill: the same
`n`, `mean`, `stdev` spread, the same `with_skill`-minus-`baseline` delta (here
candidate minus incumbent), and the same `never_passes` signal name. The two
skills ship separately, so this module cannot import that script. Parity is
pinned by `tests/skills/skillopt/test_skillopt_report_parity.py`, which feeds
both implementations the same inputs.

Observation units: pass rate has one value per verified task (1.0 or 0.0).
Measurements read the same file `efficiency-gate` reads, one metric per file,
with every repeat of every `sel` task pooled per arm.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Sequence
from typing import Any

from _skillopt_gates import _assert_selection_usable, _split_task_ids
from _skillopt_patching import SkillOptError

ARMS = ("incumbent", "candidate")
ROUND_PLACES = 4


def is_measurement(value: object, *, integer: bool = False) -> bool:
    """True for a finite, non-negative number. A bool is not a measurement."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    if integer and not isinstance(value, int):
        return False
    try:
        return math.isfinite(value) and value >= 0
    except OverflowError:
        return False


def spread(values: Sequence[float]) -> dict[str, Any]:
    """Return `n`, `mean`, and sample `stdev` (null below two observations)."""
    if not values:
        return {"n": 0, "mean": None, "stdev": None}
    return {
        "n": len(values),
        "mean": round(statistics.fmean(values), ROUND_PLACES),
        "stdev": round(statistics.stdev(values), ROUND_PLACES) if len(values) > 1 else None,
    }


def _object(value: Any, what: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise SkillOptError(f"{what} must be an object")
    return value


def _evidence(source: dict[str, Any], arm: str, task_ids: list[str]) -> dict[str, str | None]:
    per_arm = _object(source.get(arm), f"evidence.{arm}")
    found: dict[str, str | None] = {}
    for tid in task_ids:
        text = per_arm.get(tid)
        if text is not None and (not isinstance(text, str) or not text.strip()):
            raise SkillOptError(f"evidence.{arm}.{tid} must be a nonempty string")
        found[tid] = text
    return found


def _repeats(source: dict[str, Any], arm: str, task_ids: list[str]) -> list[float]:
    """Every repeat of one arm over the split, in the `efficiency-gate` measurements shape."""
    per_arm = _object(source.get(arm), f"measurements.{arm}")
    pooled: list[float] = []
    for tid in task_ids:
        values = per_arm.get(tid, [])
        if not isinstance(values, list) or not all(is_measurement(v) for v in values):
            raise SkillOptError(f"measurements.{arm}.{tid} must be a list of numbers, 0 or more")
        pooled.extend(values)
    return pooled


def _signals(
    tid: str,
    inc: object,
    cand: object,
    null: dict[str, Any] | None,
    evidence: dict[str, dict[str, str | None]],
) -> list[str]:
    signals: list[str] = []
    if not isinstance(inc, bool) or not isinstance(cand, bool):
        return ["unverified"]
    if inc and cand:
        signals.append("always_passes")
    if not inc and not cand:
        signals.append("never_passes")
    if null is not None and isinstance(null.get(tid), bool) and null[tid] != inc:
        signals.append("unstable")
    for arm, passed in (("incumbent", inc), ("candidate", cand)):
        if passed and evidence[arm][tid] is None:
            signals.append(f"pass_without_evidence_{arm}")
    return signals


def _change(inc: object, cand: object) -> str:
    if not isinstance(inc, bool) or not isinstance(cand, bool):
        return "unverified"
    if cand and not inc:
        return "gain"
    if inc and not cand:
        return "regression"
    return "same"


def mean_delta(base: Sequence[float], other: Sequence[float]) -> float | None:
    """Mean of `other` minus mean of `base`, rounded once from the raw values."""
    if not base or not other:
        return None
    return round(statistics.fmean(other) - statistics.fmean(base), ROUND_PLACES)


def _pass_rates(task_ids: list[str], results: dict[str, Any]) -> list[float]:
    return [1.0 if results[t] else 0.0 for t in task_ids if isinstance(results.get(t), bool)]


def _benchmark(
    task_ids: list[str],
    results: dict[str, dict[str, Any]],
    measured: dict[str, list[float]] | None,
    metric: str | None,
) -> dict[str, Any]:
    rates = {arm: _pass_rates(task_ids, results[arm]) for arm in ARMS}
    stats = {arm: {"pass_rate": spread(rates[arm])} for arm in ARMS}
    bench: dict[str, Any] = {
        **stats,
        "delta": {"pass_rate": mean_delta(rates["incumbent"], rates["candidate"])},
    }
    if measured is not None:
        bench["measurements"] = {
            "metric": metric,
            **{arm: spread(measured[arm]) for arm in ARMS},
            "delta": mean_delta(measured["incumbent"], measured["candidate"]),
        }
    return bench


def _declared_metric(eval_set: dict[str, Any]) -> str | None:
    spec = eval_set.get("efficiency")
    metric = spec.get("metric") if isinstance(spec, dict) else None
    return metric if isinstance(metric, str) and metric else None


def run_report(
    eval_set: dict[str, Any],
    incumbent: dict[str, Any],
    candidate: dict[str, Any],
    split: str = "sel",
    *,
    null_results: dict[str, Any] | None = None,
    evidence: dict[str, Any] | None = None,
    measurements: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Explain one pair of result files over a split. Never gates.

    evidence     : {"incumbent": {task: "one line"}, "candidate": {...}}
    measurements : the `efficiency-gate` measurements.json shape,
                   {"incumbent": {task: [n, ...]}, "candidate": {...}}; the metric
                   name comes from the manifest's `efficiency.metric` when declared.

    Signals per task: `always_passes` (non-discriminating, a ceiling when it
    holds for the whole split), `never_passes` (suspect the verifier or the
    task before the edit), `unstable` (a byte-identical rerun flipped it),
    `unverified`, and `pass_without_evidence_<arm>`.
    """
    task_ids = _split_task_ids(eval_set, split)
    if split == "sel":
        _assert_selection_usable(eval_set, task_ids)
    ev = {arm: _evidence(_object(evidence, "evidence"), arm, task_ids) for arm in ARMS}
    measured = None
    if measurements is not None:
        source = _object(measurements, "measurements")
        measured = {arm: _repeats(source, arm, task_ids) for arm in ARMS}
    results = {"incumbent": incumbent, "candidate": candidate}
    tasks = [
        {
            "id": tid,
            "incumbent": incumbent.get(tid),
            "candidate": candidate.get(tid),
            "change": _change(incumbent.get(tid), candidate.get(tid)),
            "signals": _signals(tid, incumbent.get(tid), candidate.get(tid), null_results, ev),
            "evidence": {arm: ev[arm][tid] for arm in ARMS},
        }
        for tid in task_ids
    ]
    bench = _benchmark(task_ids, results, measured, _declared_metric(eval_set))
    return {"split": split, "tasks": tasks, "benchmark": bench}
