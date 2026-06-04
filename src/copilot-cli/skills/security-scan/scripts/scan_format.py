"""Console formatting for the security scanner.

Extracted from ``scan_vulnerabilities.py`` (issue #1848) and decomposed so the
public ``format_console_output`` sergeant stays under cyclomatic complexity 10.
The output text is byte-for-byte identical to the original inline implementation;
this is a behavior-preserving refactor, not a format change.

The formatter takes the scan result by duck typing (it reads ``result.errors``,
``result.vulnerabilities``, ``result.files_scanned``, ``result.suppressed`` and
each vuln's fields) so it does not import ``ScanResult``/``Vulnerability`` from
the main module, which would create an import cycle. Exit-code constants come
from the shared ``scan_constants`` module for the same reason.
"""

from __future__ import annotations

from typing import Any

from scan_constants import EXIT_VULNERABILITIES

_SEVERITY_ORDER = ["CRITICAL", "HIGH", "MEDIUM", "LOW"]


def format_console_output(result: Any) -> str:
    """Format scan result for console output."""
    output = ["=== Security Vulnerability Scan ===", ""]

    _append_errors(output, result)

    if not result.vulnerabilities:
        _append_no_vulnerabilities(output, result)
        return "\n".join(output)

    _append_vulnerability_details(output, result)
    _append_summary(output, result)

    return "\n".join(output)


def _append_errors(output: list[str], result: Any) -> None:
    """Append the error block, if any errors were collected."""
    if not result.errors:
        return
    output.append("Errors:")
    for error in result.errors:
        output.append(f"  {error}")
    output.append("")


def _append_no_vulnerabilities(output: list[str], result: Any) -> None:
    """Append the clean-scan summary used when no vulnerabilities were found."""
    output.append(f"Files scanned: {result.files_scanned}")
    output.append("No vulnerabilities found.")
    if result.suppressed:
        output.append(f"Suppressed findings: {len(result.suppressed)}")


def _append_vulnerability_details(output: list[str], result: Any) -> None:
    """Append per-vulnerability detail blocks, grouped by severity."""
    by_severity: dict[str, list[Any]] = {
        "CRITICAL": [], "HIGH": [], "MEDIUM": [], "LOW": []
    }
    for vuln in result.vulnerabilities:
        by_severity.get(vuln.severity, by_severity["MEDIUM"]).append(vuln)

    for severity in _SEVERITY_ORDER:
        for vuln in by_severity[severity]:
            output.append(f"[{vuln.cwe}] {vuln.title}")
            output.append(f"  File: {vuln.file}:{vuln.line}")
            output.append(f"  Pattern: {vuln.pattern}")
            output.append(f"  Code: {vuln.code}")
            output.append(f"  Severity: {vuln.severity}")
            output.append(f"  Recommendation: {vuln.recommendation}")
            output.append("")


def _append_summary(output: list[str], result: Any) -> None:
    """Append the summary block with counts and the exit-code line."""
    output.append("=== Summary ===")
    output.append(f"Files scanned: {result.files_scanned}")
    output.append(f"Vulnerabilities found: {len(result.vulnerabilities)}")

    cwe_counts: dict[str, int] = {}
    for vuln in result.vulnerabilities:
        cwe_counts[vuln.cwe] = cwe_counts.get(vuln.cwe, 0) + 1
    for cwe, count in sorted(cwe_counts.items()):
        output.append(f"  {cwe} (Command Injection): {count}")

    if result.suppressed:
        output.append(f"Suppressed findings: {len(result.suppressed)}")

    output.append("")
    output.append(f"Exit code: {EXIT_VULNERABILITIES} (vulnerabilities detected)")
