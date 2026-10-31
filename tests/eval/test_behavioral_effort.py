"""Behavioral effort evidence for Claude only (issue #5426, Amendment 4, owner decision D12)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tests.eval._harness_capability_test_support import MATRIX, capability

VERSION = "2.1.309 (Claude Code)"
Status = capability.CapabilityStatus


def _evidence(counts: dict[str, dict[str, int]], version: str = VERSION) -> Any:
    import _behavioral_effort as be

    return be.BehavioralEffort(version, "fixed prompt", counts)


def _verdict(counts: dict[str, dict[str, int]], *, version: str = VERSION, pinned: str = VERSION):
    models = list(counts)
    return capability.classify_behavioral_effort(_evidence(counts, version), pinned, models)


MONOTONIC = {"claude-opus-5-5": {"low": 100, "medium": 106, "high": 134}}


def test_strictly_increasing_thinking_tokens_verify() -> None:
    assert _verdict(MONOTONIC) is Status.VERIFIED


@pytest.mark.parametrize(
    "counts",
    [
        {"low": 100, "medium": 100, "high": 134},
        {"low": 100, "medium": 134, "high": 134},
        {"low": 105, "medium": 105, "high": 105},
        {"low": 105, "medium": 103, "high": 120},
        {"low": 285, "medium": 233, "high": 337},
        {"low": 300, "medium": 200, "high": 100},
        {"low": 100, "medium": 106},
        {"medium": 106, "high": 134},
        {"low": 100, "high": 134},
        {},
    ],
    ids=["tie-low-medium", "tie-medium-high", "all-tied", "inversion-1", "inversion-2",
         "descending", "missing-high", "missing-low", "missing-medium", "empty"],
)  # fmt: skip
def test_a_tie_an_inversion_or_a_missing_level_is_unverified(counts: dict[str, int]) -> None:
    assert _verdict({"claude-opus-5-5": counts}) is Status.UNVERIFIED


def test_a_cli_version_mismatch_is_unverified() -> None:
    assert _verdict(MONOTONIC, version="2.1.307 (Claude Code)") is Status.UNVERIFIED
    assert _verdict(MONOTONIC, pinned="") is Status.UNVERIFIED


def test_every_requested_model_must_pass_and_an_empty_request_does_not() -> None:
    both = {**MONOTONIC, "claude-haiku-5-5": {"low": 3, "medium": 2, "high": 4}}
    evidence = _evidence(both)

    assert capability.classify_behavioral_effort(evidence, VERSION, ["claude-opus-5-5"]) is (
        Status.VERIFIED
    )
    assert capability.classify_behavioral_effort(evidence, VERSION, list(both)) is Status.UNVERIFIED
    assert capability.classify_behavioral_effort(evidence, VERSION, []) is Status.UNVERIFIED
    assert capability.classify_behavioral_effort(evidence, VERSION, ["claude-unmeasured"]) is (
        Status.UNVERIFIED
    )
    assert capability.classify_behavioral_effort(None, VERSION, ["claude-opus-5-5"]) is (
        Status.UNVERIFIED
    )


def test_a_boolean_count_is_not_a_count() -> None:
    import _behavioral_effort as be

    assert not be.strictly_increasing({"low": False, "medium": True, "high": 2})


# --- records: behavioral evidence is Claude-only -----------------------------------------


def _document() -> dict[str, Any]:
    return json.loads(MATRIX.read_text(encoding="utf-8"))


def _load(tmp_path: Path, document: dict[str, Any]) -> list[Any]:
    path = tmp_path / "matrix.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return capability.load_matrix(path)


def _harness(document: dict[str, Any], name: str) -> dict[str, Any]:
    return next(h for h in document["harnesses"] if h["harness"] == name)


def _eligibility(records: list[Any]) -> dict[str, dict[str, str]]:
    rows = capability.build_report(records)["arm_eligibility"]
    return {row["arm"]: row["eligibility"] for row in rows}


def test_the_checked_in_claude_record_round_trips_its_counts() -> None:
    report = capability.build_report(capability.load_matrix(MATRIX))
    claude = next(h for h in report["harnesses"] if h["harness"] == "claude")

    assert claude["effort_behavioral"]["thinking_tokens"]["claude-opus-5-5"] == {
        "low": 100,
        "medium": 106,
        "high": 134,
    }
    assert all(
        "effort_behavioral" not in h for h in report["harnesses"] if h["harness"] != "claude"
    )


def test_codex_rejects_behavioral_evidence_on_its_effort_cell(tmp_path: Path) -> None:
    document = _document()
    cell = _harness(document, "codex")["capabilities"]["effort_override"]
    cell["evidence"] = "behavioral"

    with pytest.raises(capability.HarnessCapabilityError, match="only the claude effort_override"):
        _load(tmp_path, document)


def test_codex_rejects_behavioral_counts(tmp_path: Path) -> None:
    document = _document()
    _harness(document, "codex")["effort_behavioral"] = _harness(document, "claude")[
        "effort_behavioral"
    ]

    with pytest.raises(capability.HarnessCapabilityError, match="only claude may"):
        _load(tmp_path, document)


def test_claude_may_not_use_behavioral_evidence_on_another_cell(tmp_path: Path) -> None:
    document = _document()
    _harness(document, "claude")["capabilities"]["model_override"]["evidence"] = "behavioral"

    with pytest.raises(capability.HarnessCapabilityError, match="only the claude effort_override"):
        _load(tmp_path, document)


def test_a_verified_behavioral_cell_needs_every_supported_model_to_pass(tmp_path: Path) -> None:
    document = _document()
    _harness(document, "claude")["capabilities"]["effort_override"]["status"] = "VERIFIED"

    with pytest.raises(capability.HarnessCapabilityError, match="strictly increasing"):
        _load(tmp_path, document)


def test_a_verified_behavioral_cell_is_accepted_when_all_models_rise(tmp_path: Path) -> None:
    document = _document()
    claude = _harness(document, "claude")
    claude["capabilities"]["effort_override"]["status"] = "VERIFIED"
    for model in claude["effort_behavioral"]["thinking_tokens"]:
        claude["effort_behavioral"]["thinking_tokens"][model] = {"low": 1, "medium": 2, "high": 3}

    table = _eligibility(_load(tmp_path, document))

    assert {row["claude"] for row in table.values()} == {"ELIGIBLE_UNMATCHED"}
    assert {row["codex"] for row in table.values()} == {"ELIGIBLE_UNMATCHED"}


def test_a_version_mismatch_in_the_counts_rejects_every_effort_arm(tmp_path: Path) -> None:
    document = _document()
    _harness(document, "claude")["effort_behavioral"]["cli_version"] = "2.1.307 (Claude Code)"

    table = _eligibility(_load(tmp_path, document))

    assert {arm: table[arm]["claude"] for arm in "ACDE"} == dict.fromkeys("ACDE", "UNVERIFIED")
    assert {arm: table[arm]["claude"] for arm in "BF"} == dict.fromkeys("BF", "ELIGIBLE_UNMATCHED")


def test_a_failed_opus_inversion_rejects_arms_a_and_e_but_not_b_or_f(tmp_path: Path) -> None:
    document = _document()
    counts = _harness(document, "claude")["effort_behavioral"]["thinking_tokens"]
    counts["claude-opus-5-5"] = {"low": 100, "medium": 100, "high": 134}

    table = _eligibility(_load(tmp_path, document))

    assert {arm: table[arm]["claude"] for arm in "ACDE"} == dict.fromkeys("ACDE", "UNVERIFIED")
    assert table["B"]["claude"] == table["F"]["claude"] == "ELIGIBLE_UNMATCHED"


def test_codex_effort_still_needs_backend_evidence_to_pass_the_arm_gate(tmp_path: Path) -> None:
    document = _document()
    cell = _harness(document, "codex")["capabilities"]["effort_override"]
    cell["status"] = "UNVERIFIED"

    table = _eligibility(_load(tmp_path, document))

    assert table["A"]["codex"] == "UNVERIFIED"


@pytest.mark.parametrize(
    "bad",
    [{"cli_version": "", "prompt": "p", "thinking_tokens": {"m": {"low": 1}}},
     {"cli_version": "v", "prompt": "p", "thinking_tokens": {}},
     {"cli_version": "v", "prompt": "p", "thinking_tokens": {"m": {"max": 1}}},
     {"cli_version": "v", "prompt": "p", "thinking_tokens": {"m": {"low": -1}}},
     {"cli_version": "v", "prompt": "p", "thinking_tokens": {"m": {"low": True}}},
     {"cli_version": "v", "prompt": "p", "thinking_tokens": {"m": []}},
     "text"],
)  # fmt: skip
def test_a_malformed_behavioral_block_is_refused(tmp_path: Path, bad: object) -> None:
    document = _document()
    _harness(document, "claude")["effort_behavioral"] = bad

    with pytest.raises(capability.HarnessCapabilityError):
        _load(tmp_path, document)
