"""Human-readable reports for context output validation."""

from __future__ import annotations

import sys

from context_output_manifest import ManifestReport


def _count_label(count: int, singular: str) -> str:
    """Format a count for a concise CLI report."""
    plural = "indexes" if singular == "index" else f"{singular}s"
    label = singular if count == 1 else plural
    return f"{count} {label}"


def print_manifest_report(report: ManifestReport) -> None:
    """Print manifest counts and any detected drift."""
    print(
        f"Checked {_count_label(report.sources_checked, 'source')}, "
        f"{_count_label(report.indexes_checked, 'index')}, "
        f"{_count_label(report.details_checked, 'expected detail file')}; "
        f"{_count_label(report.details_found, 'detail file')} found.",
        file=sys.stderr,
    )
    if report.issues:
        print("Context output drift detected:", file=sys.stderr)
        for issue in report.issues:
            print(f"- {issue}", file=sys.stderr)
