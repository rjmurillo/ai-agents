#!/usr/bin/env python3
"""orphan-ref-validator output types + ADR-056 envelope rendering.

Owns the ``Finding``, ``ScanResult`` types and the ``render_envelope`` /
``render_error_envelope`` functions that produce the ADR-056 four-field
output (``Success``, ``Data``, ``Error``, ``Metadata``) plus the
``VERDICT:`` line.

Per ADR-056: ``Success`` reflects whether the scan ran successfully, not
whether findings exist. CRITICAL_FAIL is a successful scan that found
blocking issues; the verdict expresses that. Reserve ``Success: false``
+ populated ``Error{Message, Code}`` for configuration or runtime
failures that exit ``2``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

VERSION = "1.0.0"

Severity = Literal["critical", "warn"]
Kind = Literal[
    "skill_name",
    "script_path",
    "count_claim",
    "scan_truncated",
]
Verdict = Literal["PASS", "WARN", "CRITICAL_FAIL"]


@dataclass(frozen=True)
class Finding:
    kind: Kind
    severity: Severity
    target_file: str
    line: int
    referenced_entity: str
    recommendation: str
    expected: str | None = None
    actual: str | None = None
    suppressed: bool = False

    @property
    def key(self) -> str:
        """Stable baseline key: ``target_file:line:kind:referenced_entity``.

        Used to match a finding against a baseline of known pre-existing
        findings so a default repo-wide scan does not fail on debt that
        predates the gate (issue #2371).
        """
        return f"{self.target_file}:{self.line}:{self.kind}:{self.referenced_entity}"

    def to_dict(self) -> dict:
        d = {
            "kind": self.kind,
            "severity": self.severity,
            "target_file": self.target_file,
            "line": self.line,
            "referenced_entity": self.referenced_entity,
            "recommendation": self.recommendation,
        }
        if self.expected is not None:
            d["expected"] = self.expected
        if self.actual is not None:
            d["actual"] = self.actual
        if self.suppressed:
            d["suppressed"] = True
        return d


@dataclass
class ScanResult:
    findings: list[Finding] = field(default_factory=list)
    files_scanned: int = 0
    refs_checked: int = 0

    @property
    def verdict(self) -> Verdict:
        # Suppressed findings are known pre-existing debt matched against a
        # baseline (issue #2371). They never drive the verdict: a critical
        # finding that is suppressed does not fail the scan, and a scan whose
        # only findings are suppressed is PASS. A non-suppressed critical
        # (a new orphan ref not in the baseline) still fails.
        active = [f for f in self.findings if not f.suppressed]
        if any(f.severity == "critical" for f in active):
            return "CRITICAL_FAIL"
        if active:
            return "WARN"
        return "PASS"


ErrorType = Literal[
    "NotFound", "ApiError", "AuthError", "InvalidParams", "Timeout", "General"
]


def render_error_envelope(
    message: str, output: str, error_type: ErrorType = "InvalidParams"
) -> str:
    """Render a skill-output.schema.json envelope for config / runtime failures.

    Per ``.agents/schemas/skill-output.schema.json``: ``Code`` is the
    integer exit code (ADR-035: ``2`` for configuration error); ``Type``
    is the canonical enum; ``Message`` is the human-readable description.

    ``error_type`` defaults to ``InvalidParams`` (the original config-error
    behavior); pass ``General`` for an unhandled runtime exception caught by
    ``main()``'s catch-all guard.
    """
    envelope = {
        "Success": False,
        "Data": None,
        "Error": {
            "Message": message,
            "Code": 2,
            "Type": error_type,
        },
        "Metadata": {
            "Script": "scan.py",
            "Version": VERSION,
            "Timestamp": datetime.now(timezone.utc).isoformat(),
        },
    }
    if output == "human":
        return f"orphan-ref-validator {VERSION}\n  ERROR: {message}\nVERDICT: ERROR"
    return json.dumps(envelope, indent=2) + "\nVERDICT: ERROR"


def render_envelope(result: ScanResult, output: str) -> str:
    """Render the ADR-056 envelope for a completed scan."""
    suppressed_total = sum(1 for f in result.findings if f.suppressed)
    envelope = {
        "Success": True,
        "Data": {
            "findings": [f.to_dict() for f in result.findings],
            "verdict": result.verdict,
            "counts": {
                "files_scanned": result.files_scanned,
                "refs_checked": result.refs_checked,
                "findings_total": len(result.findings),
                "findings_suppressed": suppressed_total,
            },
        },
        "Error": None,
        "Metadata": {
            "Script": "scan.py",
            "Version": VERSION,
            "Timestamp": datetime.now(timezone.utc).isoformat(),
        },
    }
    if output == "human":
        lines = [
            f"orphan-ref-validator {VERSION}",
            f"  files_scanned: {result.files_scanned}",
            f"  refs_checked:  {result.refs_checked}",
            f"  findings:      {len(result.findings)}",
            f"  suppressed:    {suppressed_total}",
        ]
        for f in result.findings:
            tag = f.severity + " (suppressed)" if f.suppressed else f.severity
            lines.append(
                f"  [{tag}] {f.target_file}:{f.line} {f.kind} "
                f"`{f.referenced_entity}` -- {f.recommendation}"
            )
        return "\n".join(lines) + f"\nVERDICT: {result.verdict}"
    return json.dumps(envelope, indent=2) + f"\nVERDICT: {result.verdict}"
