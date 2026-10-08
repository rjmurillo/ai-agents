#!/usr/bin/env python3
"""Fail loud when the real-CLI smoke did not actually run (issue #2231 item 4).

The smoke tests in ``tests/e2e/test_cli_hook_e2e.py`` carry
``@pytest.mark.skipif`` guards: without ``RUN_CLI_E2E=1`` and the CLIs on PATH
they SKIP. A skipped test reads as a pass in a green pytest summary, so "skipped
smoke must be loud" otherwise depends on a human reading skip reasons. This gate
removes that human step: it parses the JUnit XML pytest emits and exits non-zero
when a smoke test was skipped or when no smoke test was collected at all.

The CLI smoke workflow (``.github/workflows/plugin-cli-smoke.yml``) runs the smoke
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
- The default ``--expected-count`` is 2, one hook smoke case per CLI. The
  plugin-cli-smoke.yml workflow runs one leg per CLI and passes ``--expected-count 1``, so
  each leg fails closed when its own case is lost.

- ``--allow-skip-marker MARKER`` lets a skip whose ``message`` STARTS WITH
  MARKER count as accounted for (owner decisions D25 and D26: prompt-based checks
  are best-effort and skip with ``QUOTA_SKIP:`` only when the provider budget is
  spent). A marker quoted later in the message or only in the body does not
  count. Each such skip is printed. Any other skip, any failure, and a short set
  still fail. Without the flag the gate stays strict.
- ``--require-pass SUBSTR`` (repeatable) names a test id that must PASS, not skip,
  even when the marker is allowed. Each leg passes its zero-token load test, so a
  leg whose only passing signal is a quota skip cannot go green.

Exit codes (per AGENTS.md / ADR-035):
- 0: at least one smoke test ran and none were skipped, failed, or errored.
- 1: a smoke test was skipped, failed, errored, or none were collected (logic).
- 2: usage or a malformed/missing report (config).
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from xml.etree import ElementTree

EXIT_OK = 0
EXIT_NOT_RUN = 1
EXIT_CONFIG = 2

_DEFAULT_SMOKE_SUBSTR = "test_cli_hook_e2e"
_DEFAULT_EXPECTED_COUNT = 2
_ALLOWED_SKIP_PHRASE = "best-effort test(s) quota-skipped by marker"


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


def _skip_message(case: ElementTree.Element) -> str:
    skipped = case.find("skipped")
    if skipped is None:
        return ""
    return f"{skipped.get('message', '')} {skipped.text or ''}"


def _is_marker_skipped(case: ElementTree.Element, marker: str | None) -> bool:
    """True when the case skipped and its skip ``message`` attribute starts with ``marker``.

    Prefix, not substring: pytest writes the skip reason to ``message``, so a
    reason that leads with the marker is the test's own budget-exhaustion skip.
    A marker quoted mid-message or only in the element body is not accepted.
    """
    skipped = case.find("skipped")
    if not marker or skipped is None:
        return False
    return skipped.get("message", "").lstrip().startswith(marker)


def _required_pass_problem(
    smoke_cases: list[ElementTree.Element], required: str
) -> str | None:
    """Describe why ``required`` did not PASS, or None when every match passed."""
    matches = [c for c in smoke_cases if required in _case_id(c)]
    if not matches:
        return f"no smoke test matched required-pass {required!r}"
    not_passed = [_case_id(c) for c in matches if _is_skipped(c) or _is_failed(c)]
    if not_passed:
        return f"{', '.join(not_passed)} must PASS (matched {required!r}) but did not"
    return None


def evaluate(
    report_path: Path,
    smoke_substr: str,
    expected_count: int = _DEFAULT_EXPECTED_COUNT,
    allow_skip_marker: str | None = None,
    require_pass: Sequence[str] = (),
) -> tuple[int, str]:
    """Decide whether the smoke ran. Returns ``(exit_code, message)``.

    A skip whose message contains ``allow_skip_marker`` is reported but does not
    fail the gate. The collected count includes those skips; a failed or
    otherwise-skipped case fails the gate regardless, so the count of accounted
    tests is the count of passed plus marker-skipped cases.

    Every ``require_pass`` substring must match a smoke case that PASSED, so a
    marker skip never satisfies it.

    Raises ``SmokeReportError`` on a missing or malformed report, a blank marker,
    or a blank required-pass substring.
    """
    if allow_skip_marker is not None and not allow_skip_marker.strip():
        raise SmokeReportError("--allow-skip-marker must not be blank")
    if any(not required.strip() for required in require_pass):
        raise SmokeReportError("--require-pass must not be blank")
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

    allowed = [c for c in smoke_cases if _is_marker_skipped(c, allow_skip_marker)]
    skipped = [_case_id(c) for c in smoke_cases if _is_skipped(c) and c not in allowed]
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

    problems = [p for r in require_pass if (p := _required_pass_problem(smoke_cases, r))]
    if problems:
        return (EXIT_NOT_RUN, "required smoke test(s) did not pass: " + "; ".join(problems) + ".")

    passed = [_case_id(c) for c in smoke_cases if c not in allowed]
    message = f"{len(passed)} smoke test(s) ran and passed: {', '.join(passed)}."
    if allowed:
        notes = "; ".join(f"{_case_id(c)} ({_skip_message(c).strip()[:200]})" for c in allowed)
        message += f" {len(allowed)} {_ALLOWED_SKIP_PHRASE} {allow_skip_marker!r}: {notes}."
    return (EXIT_OK, message)


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
    parser.add_argument(
        "--allow-skip-marker",
        default=None,
        help=(
            "A skip whose message starts with this text is reported but does not "
            "fail the gate (for best-effort tests). Default: every skip fails."
        ),
    )
    parser.add_argument(
        "--require-pass",
        action="append",
        default=[],
        metavar="SUBSTR",
        help=(
            "Test-id substring that must match a smoke case that PASSED, never a "
            "skip. Repeatable."
        ),
    )
    return parser.parse_args(argv)


def _report_allowed_skips(message: str) -> None:
    """Surface marker skips as an annotation and in the job summary.

    The gate passes when only best-effort tests skipped, so the skip must stay
    visible in the run (D25, D26). ``GITHUB_STEP_SUMMARY`` is absent locally.
    """
    if _ALLOWED_SKIP_PHRASE not in message:
        return
    print(f"::notice::smoke gate: {message}")
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as handle:
            handle.write(f"Prompt checks were quota-skipped. {message}\n")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    try:
        exit_code, message = evaluate(
            args.report,
            args.smoke_substr,
            args.expected_count,
            args.allow_skip_marker,
            args.require_pass,
        )
    except SmokeReportError as exc:
        print(f"::error::smoke gate: {exc}", file=sys.stderr)
        return EXIT_CONFIG

    if exit_code == EXIT_OK:
        print(f"smoke gate OK: {message}")
        _report_allowed_skips(message)
    else:
        print(f"::error::smoke gate: {message}", file=sys.stderr)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
