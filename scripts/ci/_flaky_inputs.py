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
    """Testcase totals from one JUnit report."""

    tests: int
    failed: int


def load_junit_counts(path: Path) -> JunitCounts:
    """Count testcases and failed testcases (a failure or error child).

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
    failed = sum(
        1 for case in cases if case.find("failure") is not None or case.find("error") is not None
    )
    return JunitCounts(tests=len(cases), failed=failed)


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
