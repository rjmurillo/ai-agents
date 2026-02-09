"""Helper functions for test result generation in CI workflows.

Generates JUnit XML files when tests are skipped but required status
checks need a valid result artifact.
"""

from __future__ import annotations

import html
from pathlib import Path


def create_skipped_test_result(
    output_path: str | Path,
    test_suite_name: str = "Tests (Skipped)",
    skip_reason: str = "No testable files changed - tests skipped",
) -> Path:
    """Create an empty JUnit XML file for skipped test runs."""
    if not output_path:
        msg = "output_path must not be empty or None"
        raise ValueError(msg)
    if not test_suite_name:
        msg = "test_suite_name must not be empty"
        raise ValueError(msg)
    if not skip_reason:
        msg = "skip_reason must not be empty"
        raise ValueError(msg)

    # Escape XML-sensitive characters (CWE-91 prevention)
    escaped_name = html.escape(test_suite_name)
    escaped_reason = html.escape(skip_reason)

    # XML comments forbid "--" sequence per XML spec; replace with "- -"
    escaped_reason = escaped_reason.replace("--", "- -")

    xml_content = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<testsuites tests="0" failures="0" errors="0" time="0">\n'
        f'  <testsuite name="{escaped_name}" tests="0" failures="0" errors="0" time="0">\n'
        f"    <!-- {escaped_reason} -->\n"
        "  </testsuite>\n"
        "</testsuites>\n"
    )

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(xml_content, encoding="utf-8")
    return path
