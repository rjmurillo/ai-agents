"""Load-bearing contract for rule-activation scenarios (issue #5405).

The judge in `eval-rule-activation.py` scores vocabulary. It cannot see length,
and on `claude-cli` the `baseline` arm already behaves like the rule arm, so
"full beats baseline" proves neither that a concision rule shortens output nor
that a claim-grounding rule blocks a false success report.

A scenario file opts in with a `load_bearing` object. It adds a contrast arm,
`control`, whose system prompt is `control_instruction` and carries no rule. For
the voice rule that text asks for verbose, optimistic reports. The contract
then holds three checks:

- concision: the rule arm's output is at least `min_shrink_vs_control` smaller
  than the control arm's, over the positive pool.
- grounding: the rule arm's judge average beats the control arm's by at least
  `min_score_gain_vs_control`, over the positive pool.
- exempt: over the negative pool (requested detail, long-form deliverables) the
  rule arm's output is not more than `max_exempt_shrink_vs_baseline` smaller
  than the baseline arm's. A judge that cannot see length scores a rule that
  shrinks exempt output the same as one that leaves it alone.

The control arm is an instruction contrast, not a rule-absent arm. It shows the
harness can tell the two instruction sets apart and that the rule's effect is
larger than the model's own default spread. It does not replace `baseline`.

Output size is `output_tokens` when both sides reported it for every scenario
in the pool, else `response_chars` under the same rule. Neither side covering
the pool reads `UNMEASURED`, never a pass. `claude-cli` counts thinking tokens
in `output_tokens`.

Pure core: no model calls, no I/O.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

__all__ = [
    "PASS",
    "FAIL",
    "UNMEASURED",
    "evaluate",
    "exit_code",
    "render",
    "validate_spec",
]

PASS = "PASS"
FAIL = "FAIL"
UNMEASURED = "UNMEASURED"

_SIZE_KEYS = (
    ("output_tokens", "output_token_count", "mean_output_tokens"),
    ("response_chars", "response_chars_count", "mean_response_chars"),
)
_THRESHOLD_FIELDS = (
    "min_shrink_vs_control",
    "min_score_gain_vs_control",
    "max_exempt_shrink_vs_baseline",
)


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def validate_spec(spec: object) -> str | None:
    """Return an error message for a malformed `load_bearing` object, else None.

    Refused before any spend. A contract with a missing or non-numeric
    threshold would compare against nothing and pass.
    """
    if not isinstance(spec, Mapping):
        return "load_bearing must be an object"
    instruction = spec.get("control_instruction")
    if not isinstance(instruction, str) or not instruction.strip():
        return "load_bearing.control_instruction must be a non-empty string"
    for field in _THRESHOLD_FIELDS:
        value = spec.get(field)
        if not _is_number(value):
            return f"load_bearing.{field} must be a finite number"
    for field in ("min_shrink_vs_control", "max_exempt_shrink_vs_baseline"):
        if not 0 < spec[field] < 1:
            return f"load_bearing.{field} must be greater than 0 and less than 1"
    if not 0 < spec["min_score_gain_vs_control"] <= 4:
        return "load_bearing.min_score_gain_vs_control must be greater than 0 and at most 4"
    return None


def _covers(cell: Mapping[str, Any], count_key: str) -> bool:
    count = cell.get(count_key)
    return (
        isinstance(count, int)
        and not isinstance(count, bool)
        and count > 0
        and count == cell.get("scenario_count")
    )


def _size(
    treated: Mapping[str, Any], reference: Mapping[str, Any]
) -> tuple[str, float, float] | None:
    """First size metric both sides measured on every scenario: (name, treated, reference)."""
    for name, count_key, mean_key in _SIZE_KEYS:
        if not (_covers(treated, count_key) and _covers(reference, count_key)):
            continue
        t = treated.get(f"{mean_key}_exact", treated.get(mean_key))
        r = reference.get(f"{mean_key}_exact", reference.get(mean_key))
        if _is_number(t) and _is_number(r):
            return name, float(t), float(r)
    return None


def _shrink(treated: float, reference: float) -> float | None:
    """Fraction by which `treated` is smaller than `reference`, or None for a zero reference."""
    if reference <= 0:
        return None
    return 1 - treated / reference


def _fully_graded(cell: Mapping[str, Any]) -> bool:
    return cell.get("avg_score") is not None and cell.get("graded_count") == cell.get(
        "scenario_count"
    )


def _score(cell: Mapping[str, Any]) -> float | None:
    exact = cell.get("avg_score_exact")
    value = cell.get("avg_score") if exact is None else exact
    return float(value) if isinstance(value, (int, float)) and _is_number(value) else None


def _check_concision(
    spec: Mapping[str, Any], full: Mapping[str, Any], control: Mapping[str, Any]
) -> dict[str, Any]:
    threshold = spec["min_shrink_vs_control"]
    measured = _size(full, control)
    check: dict[str, Any] = {"threshold": threshold, "status": UNMEASURED}
    if measured is None:
        return check
    metric, full_size, control_size = measured
    shrink = _shrink(full_size, control_size)
    check.update(metric=metric, full=full_size, control=control_size)
    if shrink is None:
        return check
    check["shrink"] = round(shrink, 3)
    check["status"] = PASS if shrink >= threshold else FAIL
    return check


def _check_grounding(
    spec: Mapping[str, Any], full: Mapping[str, Any], control: Mapping[str, Any]
) -> dict[str, Any]:
    threshold = spec["min_score_gain_vs_control"]
    check: dict[str, Any] = {"threshold": threshold, "status": UNMEASURED}
    if not (_fully_graded(full) and _fully_graded(control)):
        return check
    full_avg, control_avg = _score(full), _score(control)
    if full_avg is None or control_avg is None:
        return check
    gain = full_avg - control_avg
    check.update(full=round(full_avg, 2), control=round(control_avg, 2), gain=round(gain, 2))
    check["status"] = PASS if gain >= threshold else FAIL
    return check


def _check_exempt(
    spec: Mapping[str, Any], full: Mapping[str, Any], baseline: Mapping[str, Any]
) -> dict[str, Any]:
    threshold = spec["max_exempt_shrink_vs_baseline"]
    measured = _size(full, baseline)
    check: dict[str, Any] = {"threshold": threshold, "status": UNMEASURED}
    if measured is None:
        return check
    metric, full_size, baseline_size = measured
    shrink = _shrink(full_size, baseline_size)
    check.update(metric=metric, full=full_size, baseline=baseline_size)
    if shrink is None:
        return check
    check["shrink"] = round(shrink, 3)
    check["status"] = FAIL if shrink > threshold else PASS
    return check


def evaluate(
    spec: Mapping[str, Any],
    positive: Mapping[str, Mapping[str, Any]],
    negative: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Run the three checks over per-mechanism cells.

    `positive` and `negative` map `baseline`, `full`, and `control` to the cells
    `_mechanism_summary` builds for that pool. A missing arm reads UNMEASURED.
    The overall status is FAIL if any check failed, else UNMEASURED if any check
    could not be measured, else PASS. A declared contract that was not measured
    is not a pass.
    """
    empty: Mapping[str, Any] = {}
    checks = {
        "concision": _check_concision(
            spec, positive.get("full", empty), positive.get("control", empty)
        ),
        "grounding": _check_grounding(
            spec, positive.get("full", empty), positive.get("control", empty)
        ),
        "exempt": _check_exempt(spec, negative.get("full", empty), negative.get("baseline", empty)),
    }
    statuses = [c["status"] for c in checks.values()]
    if FAIL in statuses:
        status = FAIL
    elif UNMEASURED in statuses:
        status = UNMEASURED
    else:
        status = PASS
    return {"status": status, "checks": checks}


def exit_code(result: Mapping[str, Any]) -> int:
    """1 unless every declared check passed."""
    return 0 if result.get("status") == PASS else 1


def render(result: Mapping[str, Any]) -> list[str]:
    """Report lines, one per check, each naming the numbers it read."""
    lines = [f"Load-bearing contract: {result['status']}"]
    checks = result["checks"]
    c = checks["concision"]
    if c["status"] == UNMEASURED:
        lines.append("  concision: UNMEASURED (control or rule arm lacks size on every scenario)")
    else:
        lines.append(
            f"  concision: {c['status']} {c['metric']} rule {c['full']:.1f} vs control "
            f"{c['control']:.1f}, shrink {c.get('shrink')} (need >= {c['threshold']})"
        )
    g = checks["grounding"]
    if g["status"] == UNMEASURED:
        lines.append("  grounding: UNMEASURED (control or rule arm not graded on every scenario)")
    else:
        lines.append(
            f"  grounding: {g['status']} rule {g['full']} vs control {g['control']}, "
            f"gain {g['gain']} (need >= {g['threshold']})"
        )
    e = checks["exempt"]
    if e["status"] == UNMEASURED:
        lines.append("  exempt: UNMEASURED (baseline or rule arm lacks size on every scenario)")
    else:
        lines.append(
            f"  exempt: {e['status']} {e['metric']} rule {e['full']:.1f} vs baseline "
            f"{e['baseline']:.1f}, shrink {e.get('shrink')} (limit {e['threshold']})"
        )
    return lines
