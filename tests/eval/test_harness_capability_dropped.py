"""A dropped harness is nobody's peer, and a lone harness is never "matched" (issue #5423).

Owner direction 2026-10-03: Copilot is out of eval support. The matrix keeps its
cells as history behind `"dropped": true`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tests.eval._harness_capability_test_support import MATRIX, capability


def _document() -> dict[str, Any]:
    return json.loads(MATRIX.read_text(encoding="utf-8"))


def _load(tmp_path: Path, document: dict[str, Any]) -> list[Any]:
    path = tmp_path / "matrix.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return capability.load_matrix(path)


def _eligibility(records: list[Any]) -> dict[str, dict[str, str]]:
    rows = capability.build_report(records)["arm_eligibility"]
    return {row["arm"]: row["eligibility"] for row in rows}


def _codex(document: dict[str, Any]) -> dict[str, Any]:
    return next(h for h in document["harnesses"] if h["harness"] == "codex")


def test_the_checked_in_matrix_drops_copilot_and_leaves_codex_unmatched() -> None:
    table = _eligibility(capability.load_matrix(MATRIX))

    assert {row["copilot"] for row in table.values()} == {"UNSUPPORTED"}
    assert {row["codex"] for row in table.values()} == {"ELIGIBLE_UNMATCHED"}


def test_the_dropped_flag_round_trips_into_the_report() -> None:
    report = capability.build_report(capability.load_matrix(MATRIX))

    flags = {h["harness"]: h.get("dropped") for h in report["harnesses"]}
    assert flags == {"codex": None, "copilot": True}


@pytest.mark.parametrize("bad", ["yes", 1, None, []])
def test_a_non_boolean_dropped_flag_is_refused(tmp_path: Path, bad: object) -> None:
    document = _document()
    document["harnesses"][1]["dropped"] = bad

    with pytest.raises(capability.HarnessCapabilityError, match="dropped must be a boolean"):
        _load(tmp_path, document)


def test_a_lone_harness_with_an_unverified_cell_is_not_promoted(tmp_path: Path) -> None:
    document = _document()
    _codex(document)["capabilities"]["concurrency_limit"]["status"] = "UNVERIFIED"

    table = _eligibility(_load(tmp_path, document))

    assert table["A"]["codex"] == "UNVERIFIED"


def test_a_lone_harness_missing_a_model_family_is_not_promoted(tmp_path: Path) -> None:
    document = _document()
    _codex(document)["supported_models"] = ["gpt-6-luna"]

    table = _eligibility(_load(tmp_path, document))

    assert table["A"]["codex"] == "UNVERIFIED"


def test_two_active_harnesses_can_still_be_matched(tmp_path: Path) -> None:
    document = _document()
    twin = json.loads(json.dumps(_codex(document)))
    twin["harness"] = "copilot"
    document["harnesses"][1] = twin

    table = _eligibility(_load(tmp_path, document))

    assert {row["codex"] for row in table.values()} == {"ELIGIBLE_MATCHED"}


def test_a_dropped_peer_does_not_hold_an_active_harness_back(tmp_path: Path) -> None:
    document = _document()
    document["harnesses"][1]["capabilities"]["effort_override"]["status"] = "UNVERIFIED"

    table = _eligibility(_load(tmp_path, document))

    assert table["A"]["codex"] == "ELIGIBLE_UNMATCHED"
