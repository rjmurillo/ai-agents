"""Report gate and cross-artifact checks for metric artifacts (#5639).

``report_line`` is the only sanctioned way for a report to print a metric: a
PASS prints the number, a WARN prints it labeled provisional, and a BLOCKED or
INVALID prints no number. ``check_combinable`` refuses to put artifacts with
different units, repositories, kinds, windows, or source revisions side by side
unless the caller passes a scope declaration.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from scripts.metrics.metric_artifact import ValidationResult
from scripts.metrics.metric_artifact_checks import Finding

_DIMENSIONS = ("unit", "repository", "kind", "window", "source_revision")


def _value(payload: Mapping[str, Any]) -> str:
    numerator, denominator = payload.get("numerator"), payload.get("denominator")
    return f"{numerator}/{denominator}" if denominator is not None else f"{numerator}"


def report_line(payload: object, result: ValidationResult) -> str:
    """One report line for ``payload``: number, provisional number, or a withheld notice."""
    data: Mapping[str, Any] = payload if isinstance(payload, Mapping) else {}
    metric = data.get("metric", "unknown")
    if result.status == "PASS":
        return f"{metric}: {_value(data)}"
    reasons = "; ".join(f"{f.field}: {f.message}" for f in result.findings)
    if result.status == "WARN":
        limits = "; ".join(data.get("limitations", []))
        detail = "; ".join(part for part in (limits, reasons) if part)
        return f"[PROVISIONAL] {metric}: {_value(data)} ({detail})"
    return f"[{result.status}] {metric}: withheld ({reasons})"


def _dimension(payload: Mapping[str, Any], name: str) -> str:
    value = payload.get(name)
    if name == "window" and isinstance(value, Mapping):
        return f"{value.get('start')}..{value.get('end')}"
    return str(value)


def check_combinable(
    payloads: Sequence[Mapping[str, Any]], *, declared_scope: str | None = None
) -> list[Finding]:
    """Return INVALID findings for each dimension that differs, unless a scope is declared."""
    if declared_scope is not None and declared_scope.strip():
        return []
    findings = []
    for name in _DIMENSIONS:
        seen = sorted({_dimension(payload, name) for payload in payloads})
        if len(seen) > 1:
            findings.append(
                Finding(
                    "INVALID", name, f"mixed {name} without a scope declaration: {', '.join(seen)}"
                )
            )
    return findings
