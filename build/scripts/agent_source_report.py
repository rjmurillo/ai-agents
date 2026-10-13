"""Findings, reconciliation against the pins, and report output for the source-parity gate.

Split from ``check_agent_source_parity.py`` to keep that module under the
500-line taste limit. The gate re-exports every name here.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

KIND_DIVERGED = "DIVERGED"
KIND_CHANGED = "PIN-CHANGED"
KIND_STALE = "PIN-STALE"
KIND_MISSING = "MISSING-MEMBER"

MAX_REPORT_LINES = 100

Key = tuple[str, str, str]


@dataclass(frozen=True)
class Finding:
    """One reason the gate fails."""

    kind: str
    agent: str
    pair: str
    unit: str
    detail: str = ""


def reconcile(found: dict[Key, str], pinned: dict[Key, str]) -> list[Finding]:
    """Compare live divergence to the pins and return every failure."""
    findings: list[Finding] = []
    for key in sorted(found):
        agent, pair, unit = key
        if key not in pinned:
            findings.append(Finding(KIND_DIVERGED, agent, pair, unit))
        elif pinned[key] != found[key]:
            findings.append(
                Finding(
                    KIND_CHANGED, agent, pair, unit, "edited since pinned; review, then re-record"
                )
            )
    for key in sorted(set(pinned) - set(found)):
        findings.append(Finding(KIND_STALE, key[0], key[1], key[2], "now agrees; remove the pin"))
    return findings


def print_text(findings: list[Finding], examined: int, pinned: int) -> None:
    """Print the human-readable report."""
    print(f"Examined {examined} agents; {pinned} divergences pinned in the baseline.")
    for finding in findings[:MAX_REPORT_LINES]:
        tail = f" ({finding.detail})" if finding.detail else ""
        print(f"  {finding.kind}: {finding.agent} {finding.pair} {finding.unit}{tail}")
    hidden = len(findings) - MAX_REPORT_LINES
    if hidden > 0:
        print(f"  ... and {hidden} more")
    if findings:
        print(f"FAIL: {len(findings)} source parity issue(s). Contract: GENERATOR-FILES.md.")
    else:
        print("OK: agent sources agree under the normalization contract.")


def print_json(findings: list[Finding], examined: int, pinned: int) -> None:
    """Print the machine-readable report."""
    report = {
        "agents_examined": examined,
        "pinned": pinned,
        "findings": [vars(f) for f in findings],
    }
    print(json.dumps(report, indent=2))
