"""Review adapter handling of change admissions (ADR-122 item 10, issue #7493)."""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

from scripts.ai_review_common import adapt_local_axis_verdict
from scripts.ai_review_common import verdict as verdict_module

_ROOT = Path(__file__).resolve().parents[1]
_SCANNER = (
    _ROOT / "src" / "claude" / "skills" / "code-qualities-assessment" / "scripts" / "assess.py"
)
_AXIS = "code-qualities-assessment"
_SEARCH = "scripts/memory_enhancement/search.py"
_LIB_MIRROR = "build/scripts/lib_mirror.py"
_RECORDS = list(verdict_module._CHANGE_ADMISSIONS)


def _record(file: str, quality: str) -> dict[str, Any]:
    return copy.deepcopy(next(r for r in _RECORDS if r["file"] == file and r["quality"] == quality))


def _comparison(file: str, moves: dict[str, tuple[float, float]], **extra: Any) -> dict[str, Any]:
    comparison: dict[str, Any] = {
        "file_path": file,
        "is_new_file": False,
        "change_status": "M",
        "absolute_gate_reason": None,
        "regressions": list(moves),
        "evidence_loss": [],
        "deltas": [
            {"quality": q, "base": b, "head": h, "delta": round(h - b, 4), "status": "compared"}
            for q, (b, h) in moves.items()
        ],
        "change_admissions": [_record(file, q) for q in moves],
    }
    first = _record(file, next(iter(moves)))
    comparison["base_blob"], comparison["head_blob"] = first["baseBlob"], first["headBlob"]
    comparison.update(extra)
    return comparison


def _payload(*comparisons: dict[str, Any]) -> str:
    scored = {"value": 5.0, "confidence": 0.9, "reasons": []}
    return json.dumps(
        {
            "files": [
                {"file_path": c["file_path"], "category": "authored", "coupling": scored}
                for c in comparisons
            ],
            "summary": {"file_count": len(comparisons)},
            "comparisons": list(comparisons),
        }
    )


def _verdict(comparison: dict[str, Any], exit_code: int = 0) -> str:
    return adapt_local_axis_verdict(_AXIS, _payload(comparison), exit_code)


def test_the_adapter_copy_is_the_eight_records() -> None:
    assert len(_RECORDS) == 8
    assert {r["issue"] for r in _RECORDS} == {7493}


def test_a_valid_single_record_is_warn() -> None:
    assert _verdict(_comparison(_LIB_MIRROR, {"coupling": (8.0, 7.0)})) == "WARN"


def test_a_valid_file_with_two_records_is_warn() -> None:
    assert (
        _verdict(_comparison(_SEARCH, {"cohesion": (4.2, 2.0), "coupling": (5.0, 3.0)})) == "WARN"
    )


def test_a_valid_record_is_never_pass() -> None:
    assert _verdict(_comparison(_LIB_MIRROR, {"coupling": (8.0, 7.0)})) != "PASS"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("issue", 7494),
        ("file", "other.py"),
        ("baseScore", 8.1),
        ("headScore", 6.9),
        ("authorizedBy", "someone"),
        ("authorizedOn", "2026-11-21"),
        ("authorization", "anything"),
    ],
)
def test_a_tampered_record_is_unknown(field: str, value: object) -> None:
    comparison = _comparison(_LIB_MIRROR, {"coupling": (8.0, 7.0)})
    comparison["change_admissions"][0][field] = value

    assert _verdict(comparison) == "UNKNOWN"


def test_an_extra_key_on_a_record_is_unknown() -> None:
    comparison = _comparison(_LIB_MIRROR, {"coupling": (8.0, 7.0)})
    comparison["change_admissions"][0]["extra"] = True

    assert _verdict(comparison) == "UNKNOWN"


@pytest.mark.parametrize("malformed", [[], {}, 1])
def test_malformed_quality_names_make_admission_unknown(malformed: object) -> None:
    comparison = _comparison(_LIB_MIRROR, {"coupling": (8.0, 7.0)})
    regressions = {**comparison, "regressions": [malformed]}
    assert _verdict(regressions) == "UNKNOWN"

    comparison["change_admissions"][0]["quality"] = malformed
    assert _verdict(comparison) == "UNKNOWN"


def test_a_record_for_a_different_file_is_unknown() -> None:
    comparison = _comparison(_LIB_MIRROR, {"coupling": (8.0, 7.0)})
    comparison["file_path"] = "tests/build_scripts/test_lib_mirror.py"

    assert _verdict(comparison) == "UNKNOWN"


def test_a_windows_separator_in_the_file_path_still_matches() -> None:
    comparison = _comparison(_LIB_MIRROR, {"coupling": (8.0, 7.0)})
    comparison["file_path"] = "build\\scripts\\lib_mirror.py"

    assert _verdict(comparison) == "WARN"


def test_a_record_for_a_quality_that_did_not_regress_is_unknown() -> None:
    comparison = _comparison(_SEARCH, {"coupling": (5.0, 3.0)})
    comparison["change_admissions"].append(_record(_SEARCH, "cohesion"))

    assert _verdict(comparison) == "UNKNOWN"


def test_a_regression_with_no_record_is_unknown() -> None:
    comparison = _comparison(_SEARCH, {"cohesion": (4.2, 2.0), "coupling": (5.0, 3.0)})
    comparison["change_admissions"] = [_record(_SEARCH, "coupling")]

    assert _verdict(comparison) == "UNKNOWN"


def test_a_duplicated_record_is_unknown() -> None:
    comparison = _comparison(_LIB_MIRROR, {"coupling": (8.0, 7.0)})
    comparison["change_admissions"].append(_record(_LIB_MIRROR, "coupling"))

    assert _verdict(comparison) == "UNKNOWN"


@pytest.mark.parametrize("value", [[], {}, "x", 1])
def test_a_malformed_change_admissions_field_is_unknown(value: object) -> None:
    comparison = _comparison(_LIB_MIRROR, {"coupling": (8.0, 7.0)})
    comparison["change_admissions"] = value

    assert _verdict(comparison) == "UNKNOWN"


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("evidence_loss", ["testability"]),
        ("is_new_file", True),
        ("change_status", "A"),
        ("change_status", None),
        ("absolute_gate_reason", "below threshold"),
    ],
)
def test_a_comparison_that_is_not_a_clean_modification_is_unknown(key: str, value: object) -> None:
    comparison = _comparison(_LIB_MIRROR, {"coupling": (8.0, 7.0)}, **{key: value})

    assert _verdict(comparison) == "UNKNOWN"


@pytest.mark.parametrize(("base", "head"), [(8.1, 7.0), (8.0, 7.1)])
def test_a_delta_that_differs_from_the_record_is_unknown(base: float, head: float) -> None:
    comparison = _comparison(_LIB_MIRROR, {"coupling": (base, head)})

    assert _verdict(comparison) == "UNKNOWN"


def test_a_delta_whose_status_is_not_compared_is_unknown() -> None:
    comparison = _comparison(_LIB_MIRROR, {"coupling": (8.0, 7.0)})
    comparison["deltas"][0]["status"] = "newly_scored"

    assert _verdict(comparison) == "UNKNOWN"


def test_a_delta_for_the_quality_that_is_missing_is_unknown() -> None:
    comparison = _comparison(_LIB_MIRROR, {"coupling": (8.0, 7.0)})
    comparison["deltas"] = []

    assert _verdict(comparison) == "UNKNOWN"


def test_both_admission_kinds_on_one_comparison_are_unknown() -> None:
    comparison = _comparison(_LIB_MIRROR, {"coupling": (8.0, 7.0)})
    comparison["csharp_parser_dependency_admission"] = {"issue": 7406}

    assert _verdict(comparison) == "UNKNOWN"


def test_change_and_rule_admissions_on_one_comparison_are_unknown() -> None:
    # A valid change record must not vouch for a rule record the adapter never
    # checked (issue #7525 rule admissions use a separate field).
    comparison = _comparison(_LIB_MIRROR, {"coupling": (8.0, 7.0)})
    assert _verdict(comparison) == "WARN"
    comparison["rule_admissions"] = {
        "coupling": {
            "issue": 7525,
            "rule": "no_new_third_party_import",
            "baseThirdParty": [],
            "headThirdParty": [],
        }
    }

    assert _verdict(comparison) == "UNKNOWN"


def test_a_null_change_admissions_field_keeps_the_old_behavior() -> None:
    comparison = _comparison(_LIB_MIRROR, {"coupling": (8.0, 7.0)}, change_admissions=None)

    assert _verdict(comparison) == "FAIL"


@pytest.mark.parametrize("exit_code", [10, 11])
def test_exits_ten_and_eleven_stay_fail_even_with_valid_records(exit_code: int) -> None:
    comparison = _comparison(_LIB_MIRROR, {"coupling": (8.0, 7.0)})

    assert _verdict(comparison, exit_code) == "FAIL"


def test_a_clean_comparison_beside_an_admitted_one_is_warn() -> None:
    clean = {
        "file_path": "ok.py",
        "is_new_file": False,
        "change_status": "M",
        "regressions": [],
        "evidence_loss": [],
        "deltas": [],
    }
    payload = _payload(clean, _comparison(_LIB_MIRROR, {"coupling": (8.0, 7.0)}))

    assert adapt_local_axis_verdict(_AXIS, payload, 0) == "WARN"


def test_an_admitted_comparison_beside_an_unadmitted_regression_is_fail() -> None:
    bad = _comparison(_LIB_MIRROR, {"coupling": (8.0, 7.0)})
    bad["file_path"] = "src/other.py"
    bad["change_admissions"] = None
    payload = _payload(_comparison(_LIB_MIRROR, {"coupling": (8.0, 7.0)}), bad)

    assert adapt_local_axis_verdict(_AXIS, payload, 0) == "FAIL"


# --- conformance: scanner, adapter, and config hold one list -------------------------


def _scanner_records() -> list[dict[str, Any]]:
    spec = importlib.util.spec_from_file_location("assess_for_conformance", _SCANNER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return list(module._CHANGE_ADMISSIONS)


def _copies_agree(adapter: list[Any], scanner: list[Any], config: list[Any]) -> bool:
    """The conformance rule: all three copies hold the same records in the same order."""
    return len(scanner) == 8 and adapter == scanner == config


def test_scanner_adapter_and_config_hold_the_same_list_in_the_same_order() -> None:
    config = json.loads((_ROOT / ".qualityrc.json").read_text(encoding="utf-8"))

    assert _copies_agree(_RECORDS, _scanner_records(), config["changeAdmissions"])


def test_the_conformance_check_would_notice_a_drifted_adapter_copy() -> None:
    """Negative control: the same check fails when one adapter field drifts."""
    config = json.loads((_ROOT / ".qualityrc.json").read_text(encoding="utf-8"))
    drifted = copy.deepcopy(_RECORDS)
    drifted[0]["headBlob"] = "f" * 40

    assert not _copies_agree(drifted, _scanner_records(), config["changeAdmissions"])


def test_a_head_blob_mismatch_is_unknown() -> None:
    comparison = _comparison(_LIB_MIRROR, {"coupling": (8.0, 7.0)}, head_blob="0" * 40)

    assert _verdict(comparison) == "UNKNOWN"


def test_missing_blob_ids_are_unknown() -> None:
    comparison = _comparison(_LIB_MIRROR, {"coupling": (8.0, 7.0)})
    del comparison["base_blob"], comparison["head_blob"]

    assert _verdict(comparison) == "UNKNOWN"


def test_an_integer_score_record_is_unknown_not_an_error() -> None:
    comparison = _comparison(_LIB_MIRROR, {"coupling": (8.0, 7.0)})
    comparison["change_admissions"][0]["baseScore"] = 8

    assert _verdict(comparison) == "UNKNOWN"


def test_a_drifted_adapter_copy_turns_a_real_record_into_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    comparison = _comparison(_LIB_MIRROR, {"coupling": (8.0, 7.0)})
    drifted = copy.deepcopy(list(verdict_module._CHANGE_ADMISSIONS))
    drifted[0]["headBlob"] = "f" * 40
    monkeypatch.setattr(verdict_module, "_CHANGE_ADMISSIONS", tuple(drifted))

    assert _verdict(comparison) == "UNKNOWN"
