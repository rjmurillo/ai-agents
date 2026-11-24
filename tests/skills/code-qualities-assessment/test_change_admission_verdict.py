"""Review adapter checks on issue #7525 change admission records.

The adapter re-checks each record the scanner emits, so a malformed or
inconsistent record never turns a regression into WARN.
"""

from __future__ import annotations

import json

import pytest

from scripts.ai_review_common import adapt_local_axis_verdict

_AXIS = "code-qualities-assessment"


def _payload(regressions: list[object], admissions: object, **extra: object) -> str:
    quality = {"value": 9.0, "confidence": 0.6, "reasons": []}
    entry = {"file_path": "a.py", "category": "authored", "scoring_failed": False}
    entry.update(
        {
            q: dict(quality)
            for q in ("cohesion", "coupling", "encapsulation", "testability", "non_redundancy")
        }
    )
    comparison: dict[str, object] = {
        "file_path": "a.py",
        "is_new_file": False,
        "change_status": "M",
        "absolute_gate_reason": None,
        "regressions": regressions,
        "evidence_loss": [],
        "deltas": [],
        "change_admissions": admissions,
        **extra,
    }
    return json.dumps({"files": [entry], "summary": {"file_count": 1}, "comparisons": [comparison]})


_COUPLING = {
    "issue": 7525,
    "rule": "no_new_third_party_import",
    "baseThirdParty": ["yaml"],
    "headThirdParty": ["yaml"],
}
_NON_REDUNDANCY = {
    "issue": 7525,
    "rule": "no_new_duplicate_lines",
    "baseDuplicateLines": 3,
    "headDuplicateLines": 2,
}


@pytest.mark.parametrize(
    ("regressions", "admissions", "extra", "verdict"),
    [
        (["coupling"], {"coupling": _COUPLING}, {}, "WARN"),
        (
            ["coupling", "non_redundancy"],
            {"coupling": _COUPLING, "non_redundancy": _NON_REDUNDANCY},
            {},
            "WARN",
        ),
        (["coupling", "cohesion"], {"coupling": _COUPLING}, {}, "FAIL"),
        (["coupling"], {"coupling": _COUPLING}, {"evidence_loss": ["testability"]}, "FAIL"),
        (["coupling"], None, {}, "FAIL"),
        ([], {"coupling": _COUPLING}, {}, "UNKNOWN"),
        (["coupling"], {}, {}, "UNKNOWN"),
        (
            ["coupling"],
            {"coupling": {**_COUPLING, "headThirdParty": ["yaml", "requests"]}},
            {},
            "UNKNOWN",
        ),
        (["coupling"], {"coupling": {**_COUPLING, "issue": 7512}}, {}, "UNKNOWN"),
        (["coupling"], {"coupling": _NON_REDUNDANCY}, {}, "UNKNOWN"),
        (
            ["non_redundancy"],
            {"non_redundancy": {**_NON_REDUNDANCY, "headDuplicateLines": 4}},
            {},
            "UNKNOWN",
        ),
        (
            ["non_redundancy"],
            {"non_redundancy": {**_NON_REDUNDANCY, "baseDuplicateLines": True}},
            {},
            "UNKNOWN",
        ),
        (["coupling"], {"coupling": _COUPLING}, {"absolute_gate_reason": "new_file"}, "UNKNOWN"),
        (["cohesion"], {"cohesion": {**_NON_REDUNDANCY, "rule": None}}, {}, "UNKNOWN"),
        (
            ["cohesion"],
            {"cohesion": {"issue": 7525, "baseDuplicateLines": 0, "headDuplicateLines": 0}},
            {},
            "UNKNOWN",
        ),
        ([["coupling"]], {"coupling": _COUPLING}, {}, "UNKNOWN"),
        (
            ["coupling"],
            {"coupling": _COUPLING},
            {"csharp_parser_dependency_admission": {"issue": 7406}},
            "UNKNOWN",
        ),
    ],
    ids=[
        "coupling-admitted",
        "both-admitted",
        "unadmitted-sibling-regression",
        "evidence-loss",
        "no-admission",
        "admission-without-regression",
        "empty-admissions",
        "third-party-grew",
        "wrong-issue",
        "wrong-rule-for-quality",
        "duplicates-grew",
        "bool-count",
        "absolute-gate-file",
        "unadmittable-quality-null-rule",
        "unadmittable-quality-no-rule",
        "unhashable-regression",
        "parser-and-change-record",
    ],
)
def test_review_adapter_checks_every_change_admission(
    regressions: list[object], admissions: object, extra: dict[str, object], verdict: str
) -> None:
    payload = _payload(regressions, admissions, **extra)

    assert adapt_local_axis_verdict(_AXIS, payload, 0) == verdict
