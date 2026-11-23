"""Change-scoped admissions for issue #7493 (ADR-122 item 10)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from scripts.ai_review_common import adapt_local_axis_verdict

from .test_assess import (
    _SPRAWLING,
    _commit,
    _mod,
    _regression_argv,
    _repo_with_change,
    _write,
    main,
)
from .test_parser_admission import _PARSER_IMPORTS
from .test_typescript_admission import _TYPESCRIPT_IMPORTS

_RECORDS = list(_mod._CHANGE_ADMISSIONS)
_LIB_MIRROR = "build/scripts/lib_mirror.py"
_SEARCH = "scripts/memory_enhancement/search.py"
_AUTHORIZATION = (
    "Maintainer decisions D1 and D2, choice A: "
    "admit all 8 transitions as fixed records in one ADR-122 item."
)
_BODY = "def alpha():\n    return 1\n"


def _record(file: str, quality: str) -> dict[str, Any]:
    return next(r for r in _RECORDS if r["file"] == file and r["quality"] == quality)


def _comparison(file: str, moves: dict[str, tuple[float, float]], **overrides: Any) -> Any:
    deltas = [
        _mod.QualityDelta(q, base, head, round(head - base, 4), "compared")
        for q, (base, head) in moves.items()
    ]
    fields: dict[str, Any] = {
        "file_path": file,
        "is_new_file": False,
        "deltas": deltas,
        "regressions": list(moves),
        "evidence_loss": [],
    }
    fields.update(overrides)
    return _mod.FileComparison(**fields)


_REAL_BLOB_IDS = _mod._blob_ids


def _pinned_blobs(path: str, base_revision: str | None) -> tuple[str | None, str | None]:
    """Return the record blobs for *path*, so fixture files match their pins."""
    record = next((r for r in _RECORDS if r["file"] == path), None)
    return (record["baseBlob"], record["headBlob"]) if record else (None, None)


@pytest.fixture(autouse=True)
def _use_pinned_blobs(monkeypatch: pytest.MonkeyPatch) -> None:
    # Fixture files cannot carry the real repository blobs. Tests of the blob
    # gate itself restore the real lookup with monkeypatch.setattr.
    monkeypatch.setattr(_mod, "_blob_ids", _pinned_blobs)


def _admit(comparison: Any) -> Any:
    _mod._apply_change_admissions([comparison], {"changeAdmissions": list(_RECORDS)})
    return comparison


# --- the fixed records ----------------------------------------------------------


def test_the_scanner_holds_the_eight_records_from_adr_122_item_10() -> None:
    table = [(r["file"], r["quality"], r["baseScore"], r["headScore"]) for r in _RECORDS]

    assert table == [
        (_LIB_MIRROR, "coupling", 8.0, 7.0),
        ("scripts/memory_enhancement/hooks/user_prompt_submit_memory.py", "cohesion", 6.3, 4.2),
        ("scripts/memory_enhancement/hooks/user_prompt_submit_memory.py", "coupling", 6.0, 3.0),
        (_SEARCH, "cohesion", 4.2, 2.1),
        (_SEARCH, "coupling", 5.0, 3.0),
        ("templates/hooks/UserPromptSubmit/invoke_memory_recall.py", "cohesion", 9.2, 7.7),
        ("templates/hooks/invoke_dispatch_claude.py", "cohesion", 5.7, 4.6),
        ("tests/build_scripts/test_lib_mirror.py", "coupling", 7.0, 6.0),
    ]
    for record in _RECORDS:
        assert record["issue"] == 7493
        assert record["authorizedBy"] == "rjmurillo"
        if record["file"] == _SEARCH:
            assert record["authorizedOn"] == "2026-11-22"
            assert record["authorization"] == _AUTHORIZATION + (
                " Maintainer decision D5 renewed this head pin on 2026-11-22"
                " (issue #7493 comment 7086682234)."
            )
        else:
            assert record["authorizedOn"] == "2026-11-20"
            assert record["authorization"] == _AUTHORIZATION


def test_the_repository_config_carries_the_same_list_in_the_same_order() -> None:
    root = Path(__file__).resolve().parents[3]
    config = json.loads((root / ".qualityrc.json").read_text(encoding="utf-8"))

    assert config["changeAdmissions"] == _RECORDS


# --- matching -------------------------------------------------------------------


def test_an_exact_match_attaches_the_record() -> None:
    comparison = _admit(_comparison(_LIB_MIRROR, {"coupling": (8.0, 7.0)}))

    assert comparison.change_admissions == [_record(_LIB_MIRROR, "coupling")]


def test_a_file_with_both_records_admits_both_qualities() -> None:
    comparison = _admit(_comparison(_SEARCH, {"cohesion": (4.2, 2.1), "coupling": (5.0, 3.0)}))

    assert comparison.change_admissions == [
        _record(_SEARCH, "cohesion"),
        _record(_SEARCH, "coupling"),
    ]


def test_only_the_regressed_quality_needs_a_record() -> None:
    comparison = _admit(_comparison(_SEARCH, {"coupling": (5.0, 3.0)}))

    assert comparison.change_admissions == [_record(_SEARCH, "coupling")]


@pytest.mark.parametrize(("base", "head"), [(8.1, 7.0), (7.9, 7.0), (8.0, 7.1), (8.0, 6.9)])
def test_a_base_or_head_off_by_a_tenth_is_refused(
    base: float, head: float, capsys: pytest.CaptureFixture[str]
) -> None:
    comparison = _admit(_comparison(_LIB_MIRROR, {"coupling": (base, head)}))

    assert comparison.change_admissions is None
    assert "NOT ADMITTED: build/scripts/lib_mirror.py: coupling:" in capsys.readouterr().err


def test_a_delta_that_is_not_head_minus_base_is_refused() -> None:
    comparison = _comparison(_LIB_MIRROR, {"coupling": (8.0, 7.0)})
    comparison.deltas[0].delta = -0.5

    assert _admit(comparison).change_admissions is None


def test_a_status_other_than_compared_is_refused() -> None:
    comparison = _comparison(_LIB_MIRROR, {"coupling": (8.0, 7.0)})
    comparison.deltas[0].status = "newly_scored"

    assert _admit(comparison).change_admissions is None


def test_two_regressed_qualities_with_one_matching_record_stay_blocking(
    capsys: pytest.CaptureFixture[str],
) -> None:
    comparison = _admit(_comparison(_SEARCH, {"cohesion": (4.0, 2.1), "coupling": (5.0, 3.0)}))

    assert comparison.change_admissions is None
    err = capsys.readouterr().err
    assert "NOT ADMITTED: scripts/memory_enhancement/search.py: cohesion:" in err
    assert "coupling:" not in err.replace("cohesion:", "")


def test_a_quality_with_no_record_keeps_the_whole_file_blocking(
    capsys: pytest.CaptureFixture[str],
) -> None:
    comparison = _admit(_comparison(_LIB_MIRROR, {"coupling": (8.0, 7.0), "cohesion": (9.0, 5.0)}))

    assert comparison.change_admissions is None
    assert "cohesion: no record for this file and quality" in capsys.readouterr().err


def test_a_record_for_a_file_not_in_the_diff_is_inert(capsys: pytest.CaptureFixture[str]) -> None:
    comparison = _admit(_comparison("src/other.py", {"coupling": (8.0, 7.0)}))

    assert comparison.change_admissions is None
    assert capsys.readouterr().err == ""


@pytest.mark.parametrize("status", ["A", "R", "D"])
def test_only_a_modified_file_is_admitted(status: str) -> None:
    comparison = _comparison(_LIB_MIRROR, {"coupling": (8.0, 7.0)}, change_status=status)

    assert _admit(comparison).change_admissions is None


def test_a_new_file_is_not_admitted() -> None:
    comparison = _comparison(_LIB_MIRROR, {"coupling": (8.0, 7.0)}, is_new_file=True)

    assert _admit(comparison).change_admissions is None


def test_an_absolute_gate_reason_is_not_admitted() -> None:
    comparison = _comparison(_LIB_MIRROR, {"coupling": (8.0, 7.0)}, absolute_gate_reason="x")

    assert _admit(comparison).change_admissions is None


def test_evidence_loss_is_not_admitted() -> None:
    comparison = _comparison(_LIB_MIRROR, {"coupling": (8.0, 7.0)}, evidence_loss=["testability"])

    assert _admit(comparison).change_admissions is None


def test_evidence_loss_still_blocks_even_when_records_are_attached(
    capsys: pytest.CaptureFixture[str],
) -> None:
    comparison = _comparison(_LIB_MIRROR, {"coupling": (8.0, 7.0)}, evidence_loss=["testability"])
    comparison.change_admissions = [_record(_LIB_MIRROR, "coupling")]

    assert _mod.check_regression([comparison], [], {}, None) == 10
    assert "evidence loss" in capsys.readouterr().err


def test_no_changeadmissions_key_means_nothing_is_admitted() -> None:
    comparison = _comparison(_LIB_MIRROR, {"coupling": (8.0, 7.0)})

    _mod._apply_change_admissions([comparison], {})

    assert comparison.change_admissions is None


# --- config equality -------------------------------------------------------------


def _mutations() -> list[tuple[str, list[dict[str, Any]]]]:
    cases: list[tuple[str, list[dict[str, Any]]]] = []
    for field, value in [
        ("issue", 7494),
        ("file", "x.py"),
        ("quality", "cohesion"),
        ("baseScore", 8.1),
        ("headScore", 6.9),
        ("authorizedBy", "someone"),
        ("authorizedOn", "2026-11-21"),
        ("authorization", "anything"),
    ]:
        records = [dict(r) for r in _RECORDS]
        records[0][field] = value
        cases.append((f"field {field}", records))
    extra = [dict(r) for r in _RECORDS]
    extra[0]["extra"] = True
    cases.append(("extra key", extra))
    cases.append(("reordered", [dict(r) for r in reversed(_RECORDS)]))
    cases.append(("dropped", [dict(r) for r in _RECORDS[:-1]]))
    cases.append(("duplicated", [dict(r) for r in [*_RECORDS, _RECORDS[0]]]))
    cases.append(("empty", []))
    return cases


@pytest.mark.parametrize(
    ("label", "records"), _mutations(), ids=lambda v: v if isinstance(v, str) else ""
)
def test_a_config_list_that_differs_in_any_way_raises(
    label: str, records: list[dict[str, Any]]
) -> None:
    with pytest.raises(ValueError, match="Invalid changeAdmissions"):
        _mod._apply_change_admissions([], {"changeAdmissions": records})


def test_a_config_that_is_not_a_list_raises() -> None:
    with pytest.raises(ValueError, match="Invalid changeAdmissions"):
        _mod._apply_change_admissions([], {"changeAdmissions": _RECORDS[0]})


# --- report and exit code ---------------------------------------------------------


def test_each_admitted_quality_prints_one_admitted_line_and_does_not_block(
    capsys: pytest.CaptureFixture[str],
) -> None:
    comparison = _admit(_comparison(_SEARCH, {"cohesion": (4.2, 2.1), "coupling": (5.0, 3.0)}))

    rc = _mod.check_regression([comparison], [], {}, None)

    err = capsys.readouterr().err
    assert rc == 0
    assert err.count("ADMITTED: issue #7493, authorized by rjmurillo on 2026-11-22:") == 2
    assert err.count("issue #7493 comment 7086682234") == 2
    assert "Raw cohesion regression remains reported." in err
    assert "Raw coupling regression remains reported." in err
    assert "❌ scripts/memory_enhancement/search.py: cohesion regressed 4.2 -> 2.1" in err


def test_without_records_the_same_regressions_block(capsys: pytest.CaptureFixture[str]) -> None:
    comparison = _comparison(_SEARCH, {"cohesion": (4.2, 2.1), "coupling": (5.0, 3.0)})

    assert _mod.check_regression([comparison], [], {}, None) == 10
    assert "ADMITTED" not in capsys.readouterr().err


# --- end to end through main -------------------------------------------------------


def _build_lib_mirror_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Base scores coupling 8.0 with two parser imports, head 7.0 with three."""
    (tmp_path / _LIB_MIRROR).parent.mkdir(parents=True)
    _repo_with_change(
        tmp_path, monkeypatch, _PARSER_IMPORTS + _BODY, _TYPESCRIPT_IMPORTS + _BODY, _LIB_MIRROR
    )
    return tmp_path


@pytest.fixture
def lib_mirror_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    return _build_lib_mirror_repo(tmp_path, monkeypatch)


def _run(tmp_path: Path, config: dict[str, Any]) -> int:
    path = _write(tmp_path, ".qualityrc.json", json.dumps(config))
    result = main([*_regression_argv(), "--config", str(path)])
    assert isinstance(result, int)
    return result


def test_exit_zero_with_the_record_and_ten_without(
    lib_mirror_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    admitted = _run(lib_mirror_repo, {"thresholds": {}, "changeAdmissions": _RECORDS})
    admitted_err = capsys.readouterr().err
    blocked = _run(lib_mirror_repo, {"thresholds": {}})
    blocked_err = capsys.readouterr().err

    assert (admitted, blocked) == (0, 10)
    assert "ADMITTED: issue #7493" in admitted_err
    assert "ADMITTED" not in blocked_err


def test_the_json_report_carries_change_admissions(
    lib_mirror_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = _run(lib_mirror_repo, {"thresholds": {}, "changeAdmissions": _RECORDS})

    comparison = json.loads(capsys.readouterr().out)["comparisons"][0]
    coupling = next(d for d in comparison["deltas"] if d["quality"] == "coupling")
    assert rc == 0
    assert (coupling["base"], coupling["head"], coupling["delta"]) == (8.0, 7.0, -1.0)
    assert comparison["regressions"] == ["coupling"]
    assert comparison["change_admissions"] == [_record(_LIB_MIRROR, "coupling")]


def test_the_report_has_a_null_field_when_nothing_is_admitted(
    lib_mirror_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _run(lib_mirror_repo, {"thresholds": {}})

    assert json.loads(capsys.readouterr().out)["comparisons"][0]["change_admissions"] is None


def test_the_review_adapter_reports_warn_for_the_admitted_run(
    lib_mirror_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = _run(lib_mirror_repo, {"thresholds": {}, "changeAdmissions": _RECORDS})

    assert (
        adapt_local_axis_verdict("code-qualities-assessment", capsys.readouterr().out, rc) == "WARN"
    )


def test_a_config_that_differs_is_refused_with_exit_one(
    lib_mirror_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    changed = [dict(r) for r in _RECORDS]
    changed[0]["headScore"] = 6.0

    assert _run(lib_mirror_repo, {"thresholds": {}, "changeAdmissions": changed}) == 1
    assert "ERROR: Invalid changeAdmissions" in capsys.readouterr().err


def test_a_record_for_another_file_is_inert_end_to_end(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _repo_with_change(
        tmp_path, monkeypatch, _PARSER_IMPORTS + _BODY, _TYPESCRIPT_IMPORTS + _BODY, "other.py"
    )

    rc = _run(tmp_path, {"thresholds": {}, "changeAdmissions": _RECORDS})

    err = capsys.readouterr().err
    assert rc == 10
    assert "ADMITTED" not in err and "NOT ADMITTED" not in err


def test_the_parser_admission_still_admits_its_own_transition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    scanner = "src/claude/skills/code-qualities-assessment/scripts/assess.py"
    (tmp_path / scanner).parent.mkdir(parents=True)
    _repo_with_change(tmp_path, monkeypatch, _BODY, _PARSER_IMPORTS + _BODY, scanner)
    record = _mod._CSHARP_PARSER_DEPENDENCY_ADMISSION

    rc = _run(
        tmp_path,
        {"thresholds": {}, "csharpParserDependencyAdmission": record, "changeAdmissions": _RECORDS},
    )

    comparison = json.loads(capsys.readouterr().out)["comparisons"][0]
    assert rc == 0
    assert comparison["csharp_parser_dependency_admission"] == record
    assert comparison["change_admissions"] is None


def test_a_new_file_threshold_failure_still_blocks_an_admitted_change(
    lib_mirror_repo: Path,
) -> None:
    _commit(lib_mirror_repo, "new.py", _SPRAWLING, "new module")
    config = {
        "minConfidence": 0.0,
        "thresholds": {
            "cohesion": {"min": 10},
            "coupling": {},
            "encapsulation": {},
            "testability": {},
            "nonRedundancy": {},
        },
        "changeAdmissions": _RECORDS,
    }

    assert _run(lib_mirror_repo, config) == 11
