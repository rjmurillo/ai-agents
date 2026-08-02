#!/usr/bin/env python3
"""Write the CodeQL integration test summary to GITHUB_STEP_SUMMARY.

Reads job results from environment variables (INSTALL_RESULT, LANGUAGE_RESULT,
JSON_RESULT), writes a markdown table to $GITHUB_STEP_SUMMARY, and exits 1 if
any test failed. Replaces the bash associative-array block in
test-codeql-integration.yml (Check job results step, issue #3526).

EXIT CODES (ADR-035):
  0  - All tests passed or skipped
  1  - One or more tests failed
  2  - Usage error (GITHUB_STEP_SUMMARY not set)
"""

from __future__ import annotations

import os
import sys

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2

# Ordered list of (display-name, env-var, usage-pattern).
_TESTS: list[tuple[str, str, str]] = [
    (
        "Install & Config",
        "INSTALL_RESULT",
        "`install_codeql.py` + `test_codeql_config.py`",
    ),
    (
        "Language Scans",
        "LANGUAGE_RESULT",
        "`invoke_codeql_scan.py --languages <lang>`",
    ),
    (
        "JSON Output",
        "JSON_RESULT",
        "`invoke_codeql_scan.py --format json`",
    ),
]


def _status_emoji(status: str) -> str:
    if status == "success":
        return "\u2713"
    if status == "skipped":
        return "\u23ed"
    return "\u2717"


def build_summary(
    results: dict[str, str],
) -> tuple[str, bool]:
    """Build the markdown summary and return (text, all_passed)."""
    rows: list[str] = []
    all_passed = True
    for test_name, env_key, pattern in _TESTS:
        status = results.get(env_key, "")
        emoji = _status_emoji(status)
        if status not in ("success", "skipped"):
            all_passed = False
        rows.append(f"| {test_name} | {emoji} {status} | {pattern} |")

    lines: list[str] = [
        "## CodeQL Integration Test Results",
        "",
        "These tests document how to use the CodeQL scripts locally:",
        "",
        "| Test | Status | Usage Pattern |",
        "|------|--------|---------------|",
        *rows,
        "",
    ]
    if all_passed:
        lines += [
            "> [!TIP]",
            "> All integration tests passed! See CONTRIBUTING.md for usage details.",
        ]
    else:
        lines += [
            "> [!CAUTION]",
            "> Some tests failed. Review logs above.",
        ]
    return "\n".join(lines) + "\n", all_passed


def main(argv: list[str] | None = None) -> int:
    summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_file:
        print("ERROR: GITHUB_STEP_SUMMARY is not set", file=sys.stderr)
        return EXIT_USAGE

    results = {env_key: os.environ.get(env_key, "") for _, env_key, _ in _TESTS}
    text, all_passed = build_summary(results)

    with open(summary_file, "a", encoding="utf-8") as f:
        f.write(text)

    if all_passed:
        print("All integration tests passed!")
        return EXIT_OK

    print("ERROR: One or more integration tests failed")
    return EXIT_FAILED


if __name__ == "__main__":
    sys.exit(main())
