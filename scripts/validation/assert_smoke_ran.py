#!/usr/bin/env python3
"""Fail loud when the real-CLI smoke did not actually run (issue #2231 item 4).

The smoke tests in ``tests/e2e/`` carry ``@pytest.mark.skipif`` guards: without
``RUN_CLI_E2E=1`` and the CLIs on PATH they SKIP, and a skip reads as a pass in
a green pytest summary. This gate parses the JUnit XML pytest emits and exits
non-zero when a smoke test was skipped, failed, or was never collected
(``.claude/rules/generated-artifacts.md``: a skipped smoke MUST be loud).

JUnit XML (pytest ``--junitxml``) carries no markers, so smoke cases are
selected by name substring (``--smoke-substr``, default ``test_cli_hook_e2e``).
A ``<skipped>`` child marks a skip; ``<failure>`` or ``<error>`` marks a failure.
``--expected-count`` (default 2, one hook smoke per CLI) is the minimum number
of smoke cases; each workflow leg passes its own.

``--allow-skip-marker MARKER`` accepts a skip whose ``message`` STARTS WITH
MARKER (prompt-based checks skip with ``QUOTA_SKIP:`` only when the provider
budget is spent; owner decisions D25, D26). Any other skip, any failure, and a
short set still fail. ``--require-pass SUBSTR`` (repeatable) names a test id
that must PASS even when the marker is allowed, so a leg whose only passing
signal is a quota skip cannot go green.

The quota-skip count and job summary live in ``smoke_quota_report.py``.

Exit codes (ADR-035): 0 the smoke ran and nothing failed, 1 a smoke test was
skipped, failed, errored, or missing, 2 usage or a malformed or missing report.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from xml.etree import ElementTree

EXIT_OK = 0
EXIT_NOT_RUN = 1
EXIT_CONFIG = 2

_DEFAULT_SMOKE_SUBSTR = "test_cli_hook_e2e"
_DEFAULT_EXPECTED_COUNT = 2


class SmokeReportError(Exception):
    """The JUnit report could not be read or parsed."""


def _iter_testcases(report_path: Path) -> list[ElementTree.Element]:
    """Return every ``<testcase>`` in a JUnit report (``<testsuite>`` or ``<testsuites>``).

    ``defusedxml`` is not a project dependency, so a report that declares a DTD
    or entity is rejected before the stdlib parser can expand it (CWE-611,
    CWE-776): pytest never writes one, so it is corrupt or tampered.
    """
    try:
        text = report_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise SmokeReportError(f"report not found: {report_path}") from exc
    except OSError as exc:
        raise SmokeReportError(f"report could not be read: {report_path}: {exc}") from exc
    if "<!doctype" in text.lower() or "<!entity" in text.lower():
        raise SmokeReportError(
            f"report declares a DTD or entity, which a pytest JUnit report never "
            f"does; refusing to parse {report_path} (possible XXE/entity attack)."
        )
    try:
        return list(ElementTree.fromstring(text).iter("testcase"))
    except ElementTree.ParseError as exc:
        raise SmokeReportError(f"report is not valid XML: {report_path}: {exc}") from exc


def _case_id(case: ElementTree.Element) -> str:
    classname = case.get("classname", "")
    name = case.get("name", "")
    return f"{classname}::{name}" if classname else name


def _outcome(case: ElementTree.Element, marker: str | None) -> str:
    """Return ``failed``, ``allowed`` (marker skip), ``skipped``, or ``passed``.

    The marker is a prefix of the skip ``message``, not a substring: a marker
    quoted mid-message or only in the element body is not the test's own
    budget-exhaustion skip.
    """
    skipped = case.find("skipped")
    if case.find("failure") is not None or case.find("error") is not None:
        return "failed"
    if skipped is None:
        return "passed"
    if marker and skipped.get("message", "").lstrip().startswith(marker):
        return "allowed"
    return "skipped"


def _required_problem(ids: list[str], outcomes: list[str], required: str) -> str | None:
    """Describe why ``required`` did not PASS, or None when every match passed."""
    matches = [(i, o) for i, o in zip(ids, outcomes, strict=True) if required in i]
    if not matches:
        return f"no smoke test matched required-pass {required!r}"
    not_passed = [i for i, o in matches if o != "passed"]
    if not_passed:
        return f"{', '.join(not_passed)} must PASS (matched {required!r}) but did not"
    return None


def _first_problem(ids: list[str], outcomes: list[str], require_pass: list[str]) -> str | None:
    """Describe the first skip, failure, or unmet require-pass, or None when clean."""
    skipped = [i for i, o in zip(ids, outcomes, strict=True) if o == "skipped"]
    if skipped:
        return (
            f"{len(skipped)} smoke test(s) SKIPPED: {', '.join(skipped)}. "
            "A skipped smoke is not a passed smoke. Set RUN_CLI_E2E=1 and "
            "ensure the CLIs are installed and authenticated."
        )
    failed = [i for i, o in zip(ids, outcomes, strict=True) if o == "failed"]
    if failed:
        return f"{len(failed)} smoke test(s) FAILED: {', '.join(failed)}."
    problems = [p for r in require_pass if (p := _required_problem(ids, outcomes, r))]
    if problems:
        return "required smoke test(s) did not pass: " + "; ".join(problems) + "."
    return None


def evaluate(
    report_path: Path,
    smoke_substr: str,
    expected_count: int = _DEFAULT_EXPECTED_COUNT,
    allow_skip_marker: str | None = None,
    require_pass: list[str] | tuple[str, ...] = (),
) -> tuple[int, str]:
    """Decide whether the smoke ran. Returns ``(exit_code, message)``.

    Raises ``SmokeReportError`` on a missing or malformed report, a blank marker
    or required-pass substring, or a non-positive expected count.
    """
    if allow_skip_marker is not None and not allow_skip_marker.strip():
        raise SmokeReportError("--allow-skip-marker must not be blank")
    if any(not required.strip() for required in require_pass):
        raise SmokeReportError("--require-pass must not be blank")
    if expected_count < 1:
        raise SmokeReportError(f"expected smoke count must be positive: {expected_count}")
    cases = [c for c in _iter_testcases(report_path) if smoke_substr in _case_id(c)]
    if not cases:
        return EXIT_NOT_RUN, (
            f"no smoke test matched '{smoke_substr}' in {report_path}. "
            "The smoke was not collected, so the runtime contract never ran."
        )
    if len(cases) < expected_count:
        return EXIT_NOT_RUN, (
            f"only {len(cases)} of {expected_count} expected smoke test(s) "
            "were collected. The smoke set is incomplete."
        )
    ids = [_case_id(c) for c in cases]
    outcomes = [_outcome(c, allow_skip_marker) for c in cases]
    problem = _first_problem(ids, outcomes, list(require_pass))
    if problem:
        return EXIT_NOT_RUN, problem
    ran = [i for i, o in zip(ids, outcomes, strict=True) if o == "passed"]
    message = f"{len(ran)} smoke test(s) ran and passed" + (f": {', '.join(ran)}." if ran else ".")
    return EXIT_OK, message


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("report", type=Path, help="JUnit XML report from the smoke pytest run.")
    parser.add_argument("--smoke-substr", default=_DEFAULT_SMOKE_SUBSTR)
    parser.add_argument("--expected-count", type=int, default=_DEFAULT_EXPECTED_COUNT)
    parser.add_argument("--allow-skip-marker", default=None, help="Accept skips with this prefix.")
    parser.add_argument("--require-pass", action="append", default=[], metavar="SUBSTR")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    try:
        code, message = evaluate(
            args.report,
            args.smoke_substr,
            args.expected_count,
            args.allow_skip_marker,
            args.require_pass,
        )
    except SmokeReportError as exc:
        print(f"::error::smoke gate: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    if code == EXIT_OK:
        print(f"smoke gate OK: {message}")
    else:
        print(f"::error::smoke gate: {message}", file=sys.stderr)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
