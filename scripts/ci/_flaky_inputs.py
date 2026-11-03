"""Read the files a flaky test report depends on, failing closed.

``scripts/ci/flaky_test_report.py`` reads two kinds of pytest output: a JUnit
XML report (testcase and failure counts) and a ``lastfailed`` cache file (the
node ids that failed). A missing, unreadable, or malformed file raises
``InputError``, which the CLI maps to exit 3. A missing cache file is the one
exception: pytest writes no ``lastfailed`` file when nothing failed, so it
reads as an empty list.
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path


class InputError(Exception):
    """An input file is missing or malformed. Maps to exit 3."""


@dataclass(frozen=True)
class JunitCounts:
    """Testcase totals from one JUnit report.

    ``passed`` is the only count that can prove a test ran and passed, so it
    requires a named testcase with no failure, error, or skipped child. A
    hand-built value must set it: the default of 0 makes a verdict
    inconclusive, which fails closed.
    """

    tests: int
    failed: int
    skipped: int = 0
    passed: int = 0


def load_junit_counts(path: Path) -> JunitCounts:
    """Count testcases, failed testcases, and testcases that provably passed.

    ``defusedxml`` is not a project dependency, so a report declaring a DTD or
    an entity is rejected before the stdlib parser can expand it (CWE-611,
    CWE-776). Same fail-closed guard as ``scripts/testing/slow_test_report.py``.
    """
    if not path.is_file():
        raise InputError(f"JUnit report not found: {path}")
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise InputError(f"could not read JUnit report {path}: {exc}") from exc
    lowered = text.lower()
    if "<!doctype" in lowered or "<!entity" in lowered:
        raise InputError(f"{path}: report declares a DTD or entity; refusing to parse it")
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise InputError(f"malformed JUnit report {path}: {exc}") from exc
    if root.tag not in {"testsuites", "testsuite"}:
        raise InputError(f"{path}: root element <{root.tag}> is not a JUnit report")
    cases = list(root.iter("testcase"))

    def has(case: ET.Element, child: str) -> bool:
        return case.find(child) is not None

    failed = sum(1 for case in cases if has(case, "failure") or has(case, "error"))
    # A skipped case (including an xfail run as a skip) did not execute, so it
    # can never prove a test passed on the rerun.
    skipped = sum(1 for case in cases if has(case, "skipped"))
    # Only a named case with no outcome child proves an executed pass. pytest
    # writes a nameless case when a session aborts, and a module-level case for
    # a collection error, so requiring a name keeps both out of this count.
    passed = sum(
        1
        for case in cases
        if case.get("name")
        and not any(has(case, child) for child in ("failure", "error", "skipped"))
    )
    return JunitCounts(tests=len(cases), failed=failed, skipped=skipped, passed=passed)


def load_lastfailed(path: Path) -> list[str]:
    """Return the sorted node ids in a pytest ``lastfailed`` cache file."""
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InputError(f"malformed pytest cache file {path}: {exc}") from exc
    if not isinstance(data, dict) or not all(isinstance(key, str) for key in data):
        raise InputError(f"{path}: expected a JSON object keyed by node id")
    return sorted(key for key, value in data.items() if value)
