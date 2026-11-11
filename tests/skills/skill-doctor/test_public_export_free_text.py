"""Free-text report fields never reach the public export (epic #7248, M4 privacy gate)."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import public_export
import pytest

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "audit" / "report.json"
SECRET = "alice acme-internal summary"


def report() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return copy.deepcopy(data)


@pytest.mark.parametrize("grade", [SECRET, "/HOME/ALICE/x", "A+ but see notes", ""])
def test_free_text_grade_is_refused(grade: str) -> None:
    data = {**report(), "grade": grade}

    with pytest.raises(public_export.CanaryError, match="grade"):
        public_export.export_public(data)


@pytest.mark.parametrize("grade", sorted(public_export.KNOWN_GRADES))
def test_every_scale_letter_is_exported(grade: str) -> None:
    data = {**report(), "grade": grade}

    assert public_export.export_public(data)["grade"] == grade


@pytest.mark.parametrize("grade", [None, 3, ["A"], {"x": SECRET}])
def test_non_string_grade_falls_back_to_the_score_letter(grade: Any) -> None:
    data = {**report(), "grade": grade}

    export = public_export.export_public(data)

    assert export["grade"] in public_export.KNOWN_GRADES
    assert SECRET not in json.dumps(export)


@pytest.mark.parametrize(
    "evaluation",
    [
        {"diagnosis": SECRET, "optimization": "not_run"},
        {"diagnosis": "static", "optimization": SECRET},
        {"diagnosis": "static", "optimization": 7},
        {"diagnosis": "x", "optimization": "run"},
    ],
)
def test_free_text_evaluation_is_refused(evaluation: dict[str, Any]) -> None:
    data = {**report(), "evaluation": evaluation}

    with pytest.raises(public_export.CanaryError, match="evaluation"):
        public_export.export_public(data)


def test_known_evaluation_values_render_unchanged() -> None:
    data = {**report(), "evaluation": {"diagnosis": "static", "optimization": "not_run"}}

    status = public_export.export_public(data)["evaluation_status"]

    assert status.startswith("Diagnosis: static. Optimization: not run.")


@pytest.mark.parametrize("suggestions", [["not a dict", 3, None], "text", {"status": "accepted"}])
def test_malformed_suggestions_do_not_crash_the_export(suggestions: Any) -> None:
    data = {**report(), "suggestions": suggestions}

    export = public_export.export_public(data)

    assert sum(export["suggestion_status_counts"].values()) == 0


@pytest.mark.parametrize(
    "override",
    [{"grade": SECRET}, {"evaluation": {"diagnosis": SECRET, "optimization": "not_run"}}],
)
def test_cli_exits_1_and_writes_nothing_for_free_text(
    tmp_path: Path, override: dict[str, Any]
) -> None:
    source = tmp_path / "report.json"
    source.write_text(json.dumps({**report(), **override}), encoding="utf-8")
    out = tmp_path / "public.json"

    code = public_export.main([str(source), "--out", str(out)])

    assert code == 1
    assert not out.exists()
