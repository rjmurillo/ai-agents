#!/usr/bin/env python3
"""Fail loud when the real-CLI smoke did not actually run (issue #2231 item 4).

The smoke tests in ``tests/e2e/test_cli_hook_e2e.py`` carry
``@pytest.mark.skipif`` guards: without ``RUN_CLI_E2E=1`` and the CLIs on PATH
they SKIP. A skipped test reads as a pass in a green pytest summary, so "skipped
smoke must be loud" otherwise depends on a human reading skip reasons. This gate
removes that human step: it parses the JUnit XML pytest emits and exits non-zero
when a smoke test was skipped or when no smoke test was collected at all.

The nightly workflow (``.github/workflows/nightly-cli-smoke.yml``) runs the smoke
under ``RUN_CLI_E2E=1`` with ``--junitxml``, then calls this gate. A skip there
means the runtime contract was never exercised, which is exactly the silent pass
this gate is built to reject (see ``.claude/rules/generated-artifacts.md``: "a
skipped smoke MUST be loud, never silent").

Contract (JUnit XML, the format pytest's ``--junitxml`` writes):
- Each ``<testcase>`` is one test. A skipped case has a child ``<skipped>`` tag.
- A case with a child ``<failure>`` or ``<error>`` tag failed.
- This gate selects smoke cases by name substring (``--smoke-substr``, default
  ``test_cli_hook_e2e``) because JUnit XML does not record pytest markers. The
  default targets the file that holds the ``@pytest.mark.smoke`` tests, so the
  selection tracks the marked set without parsing pytest internals.
- The gate expects both real-CLI hook smoke cases by default
  (``--expected-count 2``), so losing either the Copilot or Claude case fails
  closed instead of passing on the remaining case.

Exit codes (per AGENTS.md / ADR-035):
- 0: at least one smoke test ran and none were skipped, failed, or errored.
- 1: a smoke test was skipped, failed, errored, or none were collected (logic).
- 2: usage or a malformed/missing report (config).
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


def _reject_doctype(text: str, report_path: Path) -> None:
    """Reject a report that declares a DTD or an entity.

    ``defusedxml`` is not a project dependency, so this is the dependency-free
    XXE / billion-laughs defense: pytest's JUnit writer never emits a DOCTYPE or
    an internal entity, so any report that contains one is either corrupt or
    tampered. Reject it before the stdlib parser can expand it (CWE-611,
    CWE-776). This is a fail-closed check: a malformed report is a config error,
    not a silent pass.
    """
    lowered = text.lower()
    if "<!doctype" in lowered or "<!entity" in lowered:
        raise SmokeReportError(
            f"report declares a DTD or entity, which a pytest JUnit report never "
            f"does; refusing to parse {report_path} (possible XXE/entity attack)."
        )


def _iter_testcases(report_path: Path) -> list[ElementTree.Element]:
    """Return every ``<testcase>`` element in a JUnit XML report.

    JUnit XML nests testcases under either a single ``<testsuite>`` root or a
    ``<testsuites>`` wrapper. ``iter`` walks both shapes without branching on the
    root tag.
    """
    try:
        text = report_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise SmokeReportError(f"report not found: {report_path}") from exc
    except OSError as exc:
        raise SmokeReportError(f"report could not be read: {report_path}: {exc}") from exc

    _reject_doctype(text, report_path)

    try:
        root = ElementTree.fromstring(text)
    except ElementTree.ParseError as exc:
        raise SmokeReportError(f"report is not valid XML: {report_path}: {exc}") from exc
    return list(root.iter("testcase"))


def _case_id(case: ElementTree.Element) -> str:
    classname = case.get("classname", "")
    name = case.get("name", "")
    return f"{classname}::{name}" if classname else name


def _is_smoke(case: ElementTree.Element, smoke_substr: str) -> bool:
    return smoke_substr in _case_id(case)


def _is_skipped(case: ElementTree.Element) -> bool:
    return case.find("skipped") is not None


def _is_failed(case: ElementTree.Element) -> bool:
    return case.find("failure") is not None or case.find("error") is not None


def evaluate(
    report_path: Path,
    smoke_substr: str,
    expected_count: int = _DEFAULT_EXPECTED_COUNT,
) -> tuple[int, str]:
    """Decide whether the smoke ran. Returns ``(exit_code, message)``.

    Raises ``SmokeReportError`` on a missing or malformed report.
    """
    cases = _iter_testcases(report_path)
    smoke_cases = [c for c in cases if _is_smoke(c, smoke_substr)]

    if expected_count < 1:
        raise SmokeReportError(f"expected smoke count must be positive: {expected_count}")

    if not smoke_cases:
        return (
            EXIT_NOT_RUN,
            f"no smoke test matched '{smoke_substr}' in {report_path}. "
            "The smoke was not collected, so the runtime contract never ran.",
        )

    if len(smoke_cases) < expected_count:
        return (
            EXIT_NOT_RUN,
            f"only {len(smoke_cases)} of {expected_count} expected smoke test(s) "
            "were collected. The smoke set is incomplete.",
        )

    skipped = [_case_id(c) for c in smoke_cases if _is_skipped(c)]
    failed = [_case_id(c) for c in smoke_cases if _is_failed(c)]

    if skipped:
        names = ", ".join(skipped)
        return (
            EXIT_NOT_RUN,
            f"{len(skipped)} smoke test(s) SKIPPED: {names}. "
            "A skipped smoke is not a passed smoke. Set RUN_CLI_E2E=1 and "
            "ensure the CLIs are installed and authenticated.",
        )

    if failed:
        names = ", ".join(failed)
        return (EXIT_NOT_RUN, f"{len(failed)} smoke test(s) FAILED: {names}.")

    ran = ", ".join(_case_id(c) for c in smoke_cases)
    return (EXIT_OK, f"{len(smoke_cases)} smoke test(s) ran and passed: {ran}.")


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fail loud when the real-CLI smoke did not run (issue #2231 item 4).",
    )
    parser.add_argument(
        "report",
        type=Path,
        help="Path to the JUnit XML report from the smoke pytest run.",
    )
    parser.add_argument(
        "--smoke-substr",
        default=_DEFAULT_SMOKE_SUBSTR,
        help=(
            "Substring that identifies smoke testcases in the JUnit report "
            f"(default: {_DEFAULT_SMOKE_SUBSTR!r})."
        ),
    )
    parser.add_argument(
        "--expected-count",
        type=int,
        default=_DEFAULT_EXPECTED_COUNT,
        help=f"Minimum expected smoke testcase count (default: {_DEFAULT_EXPECTED_COUNT}).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    try:
        exit_code, message = evaluate(args.report, args.smoke_substr, args.expected_count)
    except SmokeReportError as exc:
        print(f"::error::smoke gate: {exc}", file=sys.stderr)
        return EXIT_CONFIG

    if exit_code == EXIT_OK:
        print(f"smoke gate OK: {message}")
    else:
        print(f"::error::smoke gate: {message}", file=sys.stderr)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
