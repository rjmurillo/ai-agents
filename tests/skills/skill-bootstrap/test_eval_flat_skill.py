"""bootstrap_eval score fails a skill whose cases are all flat (issue #6666, decision D18)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

_SCRIPTS = (
    Path(__file__).resolve().parents[3] / ".claude" / "skills" / "skill-bootstrap" / "scripts"
)
sys.path.insert(0, str(_SCRIPTS))
try:
    import bootstrap_eval
finally:
    sys.path.remove(str(_SCRIPTS))

Capsys = pytest.CaptureFixture[str]

# Outcome per condition for one case: the grader passes on "alpha" only.
GAIN = ("nope", "alpha")
NO_GAP = ("alpha", "alpha")
FLAT = ("nope", "nope")
REGRESSION = ("alpha", "nope")


def _case(case_id: str, skill: str) -> dict[str, Any]:
    return {
        "id": case_id,
        "skill": skill,
        "source": "lens:ops",
        "prompt": "p",
        "grader": {"kind": "contains_all", "terms": ["alpha"]},
    }


def _score(
    capsys: Capsys,
    tmp_path: Path,
    cases: list[tuple[str, str, tuple[str, str]]],
    *extra: str,
) -> tuple[int, dict[str, Any], str]:
    """Freeze (id, skill, outcomes) cases, score them, return code, payload, stderr."""
    cases_file = tmp_path / "cases.json"
    cases_file.write_text(
        json.dumps({"cases": [_case(cid, skill) for cid, skill, _ in cases]}), encoding="utf-8"
    )
    frozen = tmp_path / "out" / "frozen.json"
    assert bootstrap_eval.main(["freeze", "--cases", str(cases_file), "--out", str(frozen)]) == 0
    capsys.readouterr()
    rows = []
    for cid, _, (baseline, with_skill) in cases:
        rows.append({"case_id": cid, "condition": "baseline", "output": baseline})
        rows.append({"case_id": cid, "condition": "with_skill", "output": with_skill})
    results = tmp_path / "r.jsonl"
    results.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    code = bootstrap_eval.main(
        ["score", "--frozen", str(frozen), "--results", str(results), *extra]
    )
    captured = capsys.readouterr()
    return code, json.loads(captured.out), captured.err


def test_all_flat_skill_exits_1_with_message(capsys: Capsys, tmp_path: Path) -> None:
    code, payload, err = _score(capsys, tmp_path, [("C1", "acme", FLAT), ("C2", "acme", FLAT)])

    assert code == 1
    assert payload["flat_skills"] == ["acme"]
    assert payload["failing_cases"] == ["C1", "C2"]
    assert "every case is flat" in payload["message"]
    assert "acme" in payload["message"]
    assert payload["message"] in err


def test_single_flat_case_is_all_flat(capsys: Capsys, tmp_path: Path) -> None:
    code, payload, _ = _score(capsys, tmp_path, [("C1", "acme", FLAT)])

    assert code == 1
    assert payload["flat_skills"] == ["acme"]


def test_all_flat_fails_in_knowledge_mode_too(capsys: Capsys, tmp_path: Path) -> None:
    code, payload, _ = _score(
        capsys, tmp_path, [("C1", "acme", FLAT), ("C2", "acme", FLAT)], "--mode", "knowledge"
    )

    assert code == 1
    assert payload["flat_skills"] == ["acme"]


def test_flat_case_among_gains_is_unchanged(capsys: Capsys, tmp_path: Path) -> None:
    code, payload, err = _score(capsys, tmp_path, [("C1", "acme", GAIN), ("C2", "acme", FLAT)])

    assert code == 0
    assert payload["flat_skills"] == []
    assert payload["failing_cases"] == []
    assert "message" not in payload
    assert err == ""


def test_flat_case_among_no_gap_is_unchanged(capsys: Capsys, tmp_path: Path) -> None:
    code, payload, _ = _score(capsys, tmp_path, [("C1", "acme", NO_GAP), ("C2", "acme", FLAT)])

    assert code == 0
    assert payload["flat_skills"] == []


def test_none_flat_is_unchanged(capsys: Capsys, tmp_path: Path) -> None:
    code, payload, err = _score(capsys, tmp_path, [("C1", "acme", GAIN), ("C2", "acme", NO_GAP)])

    assert code == 0
    assert payload["flat_skills"] == []
    assert payload["failing_cases"] == []
    assert "message" not in payload
    assert err == ""


def test_regression_still_fails_and_is_not_reported_as_flat(capsys: Capsys, tmp_path: Path) -> None:
    code, payload, _ = _score(capsys, tmp_path, [("C1", "acme", REGRESSION), ("C2", "acme", FLAT)])

    assert code == 1
    assert payload["flat_skills"] == []
    assert payload["failing_cases"] == ["C1"]


def test_only_the_all_flat_skill_is_named(capsys: Capsys, tmp_path: Path) -> None:
    code, payload, _ = _score(
        capsys,
        tmp_path,
        [("C1", "alpha-skill", GAIN), ("C2", "beta-skill", FLAT), ("C3", "beta-skill", FLAT)],
    )

    assert code == 1
    assert payload["flat_skills"] == ["beta-skill"]
    assert payload["failing_cases"] == ["C2", "C3"]
    assert "alpha-skill" not in payload["message"]
