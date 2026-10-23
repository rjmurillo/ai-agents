"""A standalone harness is no peer, and Claude role families (issue #5426, Amendment 3).

Owner decision 2026-10-23: results per harness are never pooled. The Claude record is
`"standalone": true`, so it is classified against itself and Codex keeps the classes it had
with no peer. Claude model ids fill the Sol, Luna, and Terra roles through
`_model_family_tokens`, a mapping of roles and not of capability.
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


def _harness(document: dict[str, Any], name: str) -> dict[str, Any]:
    return next(h for h in document["harnesses"] if h["harness"] == name)


def test_the_checked_in_matrix_classifies_claude_alone_and_leaves_codex_unchanged() -> None:
    table = _eligibility(capability.load_matrix(MATRIX))

    assert {row["codex"] for row in table.values()} == {"ELIGIBLE_UNMATCHED"}
    assert {arm: table[arm]["claude"] for arm in "ABCDEF"} == {
        "A": "UNVERIFIED",
        "B": "ELIGIBLE_UNMATCHED",
        "C": "UNVERIFIED",
        "D": "UNVERIFIED",
        "E": "UNVERIFIED",
        "F": "ELIGIBLE_UNMATCHED",
    }


def test_the_arms_claude_misses_are_exactly_the_arms_that_need_a_verified_effort() -> None:
    record = next(r for r in capability.load_matrix(MATRIX) if r.harness == "claude")
    needs_effort = {a.arm_id for a in capability.ARMS if "effort_override" in a.required}
    table = _eligibility([record])

    assert record.capabilities["effort_override"].status is capability.CapabilityStatus.UNVERIFIED
    assert {arm for arm, row in table.items() if row["claude"] == "UNVERIFIED"} == needs_effort


def test_the_standalone_flag_round_trips_into_the_report() -> None:
    report = capability.build_report(capability.load_matrix(MATRIX))

    flags = {h["harness"]: h.get("standalone") for h in report["harnesses"]}
    assert flags == {"codex": None, "copilot": None, "claude": True}


@pytest.mark.parametrize("bad", ["yes", 1, None, []])
def test_a_non_boolean_standalone_flag_is_refused(tmp_path: Path, bad: object) -> None:
    document = _document()
    _harness(document, "claude")["standalone"] = bad

    with pytest.raises(capability.HarnessCapabilityError, match="standalone must be a boolean"):
        _load(tmp_path, document)


def _twin_of_codex(document: dict[str, Any], *, standalone: bool) -> list[Any]:
    """Codex plus an identical second active harness, optionally standalone."""
    document["harnesses"] = [_harness(document, "codex")]
    twin = json.loads(json.dumps(document["harnesses"][0]))
    twin["harness"] = "twin"
    if standalone:
        twin["standalone"] = True
    document["harnesses"].append(twin)
    return document["harnesses"]


def test_two_active_harnesses_are_matched_without_the_flag(tmp_path: Path) -> None:
    document = _document()
    _twin_of_codex(document, standalone=False)

    table = _eligibility(_load(tmp_path, document))

    assert {row["codex"] for row in table.values()} == {"ELIGIBLE_MATCHED"}


def test_a_standalone_harness_is_no_peer_so_nothing_is_matched(tmp_path: Path) -> None:
    document = _document()
    _twin_of_codex(document, standalone=True)

    table = _eligibility(_load(tmp_path, document))

    assert {row["codex"] for row in table.values()} == {"ELIGIBLE_UNMATCHED"}
    assert {row["twin"] for row in table.values()} == {"ELIGIBLE_UNMATCHED"}


def test_a_standalone_harness_does_not_hold_a_peer_back(tmp_path: Path) -> None:
    document = _document()
    harnesses = _twin_of_codex(document, standalone=True)
    harnesses[1]["capabilities"]["concurrency_limit"]["status"] = "UNVERIFIED"

    table = _eligibility(_load(tmp_path, document))

    assert table["A"]["codex"] == "ELIGIBLE_UNMATCHED"
    assert table["A"]["twin"] == "UNVERIFIED"


def test_a_standalone_harness_is_not_promoted_past_its_own_unverified_cell(
    tmp_path: Path,
) -> None:
    document = _document()
    _harness(document, "claude")["capabilities"]["reviewer_isolation"]["status"] = "UNVERIFIED"

    table = _eligibility(_load(tmp_path, document))

    assert table["B"]["claude"] == "UNVERIFIED"


# --- Claude ids fill the Sol, Luna, and Terra roles ---------------------------------


@pytest.mark.parametrize(
    ("model", "role"),
    [("claude-opus-5-5", "sol"), ("claude-haiku-5-5", "luna"), ("claude-sonnet-5-5", "terra")],
)
def test_a_claude_id_carries_its_role_and_keeps_its_own_segments(model: str, role: str) -> None:
    tokens = capability._model_family_tokens(model)

    assert role in tokens
    assert {"claude", model.split("-")[1]} <= tokens
    assert len({"sol", "luna", "terra"} & tokens) == 1


@pytest.mark.parametrize("model", ["opus-5-5", "haiku-5-5", "claude", "claude-solar-1"])
def test_an_id_without_the_claude_prefix_or_a_known_segment_gets_no_role(model: str) -> None:
    assert not {"sol", "luna", "terra"} & capability._model_family_tokens(model)


def test_codex_ids_split_exactly_as_before() -> None:
    assert capability._model_family_tokens("gpt-5.6-sol") == frozenset({"gpt", "5.6", "sol"})


def test_claude_missing_the_haiku_model_cannot_run_the_luna_arm(tmp_path: Path) -> None:
    document = _document()
    _harness(document, "claude")["supported_models"] = ["claude-opus-5-5", "claude-sonnet-5-5"]

    table = _eligibility(_load(tmp_path, document))

    assert table["F"]["claude"] == "ELIGIBLE_UNMATCHED" and table["B"]["claude"] == (
        "ELIGIBLE_UNMATCHED"
    )
    claude = next(r for r in _load(tmp_path, document) if r.harness == "claude")
    luna_arm = next(a for a in capability.ARMS if a.arm_id == "C")
    assert not capability._satisfies_model_groups(claude, luna_arm.required_models)
