"""Parity between the smoke gate and the quota report.

``assert_smoke_ran.py`` accepts a marker skip; ``smoke_quota_report.py`` counts
one. A skip the gate rejects (failure, error, no prefix) must never be counted,
or the run summary says "quota-skipped" for a leg that went red.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.lib import smoke_report as sr

gate = sr.load_gate()
report_script = sr.load_script("smoke_quota_report")

_SUBSTR = "test_cli_hook_e2e"


def _skipped(name: str, message: str, *children: str, classname: str = sr.SMOKE_CLASS) -> str:
    body = f'<skipped type="pytest.skip" message="{message}"></skipped>' + "".join(children)
    return f'<testcase classname="{classname}" name="{name}" time="0.0">{body}</testcase>'


_FAILURE = '<failure message="assert">boom</failure>'
_ERROR = '<error message="setup">boom</error>'

_CASES = {
    "prefixed": _skipped("t_prefixed", f"{sr.MARKER} Copilot quota exhausted"),
    "leading-space": _skipped("t_space", f"  {sr.MARKER} credit"),
    "unprefixed": _skipped("t_plain", "needs RUN_CLI_E2E=1"),
    "mid-message": _skipped("t_mid", f"flaky, see {sr.MARKER} in the log"),
    "prefixed-with-failure": _skipped("t_pf", f"{sr.MARKER} quota", _FAILURE),
    "prefixed-with-error": _skipped("t_pe", f"{sr.MARKER} quota", _ERROR),
    "failure": sr.failed_case(sr.SMOKE_CLASS, "t_fail"),
    "error": f'<testcase classname="{sr.SMOKE_CLASS}" name="t_err">{_ERROR}</testcase>',
    "passed": sr.passed_case(sr.SMOKE_CLASS, "t_pass"),
    "other-suite-prefixed": _skipped("t_other", f"{sr.MARKER} quota", classname="tests.other"),
}


def _gate_marker_skips(report: Path) -> list[str]:
    cases = [c for c in gate._iter_testcases(report) if _SUBSTR in gate._case_id(c)]
    return [gate._case_id(c) for c in cases if gate._outcome(c, sr.MARKER) == "allowed"]


def _reported_skips(report: Path) -> list[str]:
    found = report_script.quota_skips(report, _SUBSTR, sr.MARKER)
    return [entry.split(" (", 1)[0] for entry in found]


def test_report_counts_exactly_the_skips_the_gate_accepts(tmp_path: Path) -> None:
    report = sr.write_cases(tmp_path, *_CASES.values())

    assert _reported_skips(report) == _gate_marker_skips(report)
    assert _reported_skips(report) == [
        f"{sr.SMOKE_CLASS}::t_prefixed",
        f"{sr.SMOKE_CLASS}::t_space",
    ]


@pytest.mark.parametrize("label", list(_CASES))
def test_each_case_is_counted_only_when_the_gate_accepts_it(tmp_path: Path, label: str) -> None:
    report = sr.write_cases(tmp_path, _CASES[label])

    assert _reported_skips(report) == _gate_marker_skips(report), label
