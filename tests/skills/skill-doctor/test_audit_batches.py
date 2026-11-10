"""Tests for audit_batches: assignments and all-or-nothing imports (epic #7248, M2)."""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any

import audit_batches as ab
import audit_scores
import pytest
from audit_batch_helpers import Row, _inventory, _row, _rows, _score


@pytest.fixture
def manifest() -> Row:
    return ab.build_assignment(_inventory(5), 2)


@pytest.fixture
def batch(manifest: Row) -> Row:
    first: Row = manifest["batches"][0]
    return first


@pytest.fixture
def accepted(tmp_path: Path, manifest: Row) -> Path:
    path = tmp_path / "accepted.json"
    ab.import_scores(manifest["batches"][1], path, _rows(manifest["batches"][1]))
    return path


# ---------------------------------------------------------------- assignment


def test_assignment_batches_cover_each_sampled_session_once(manifest: Row) -> None:
    ids = [sid for b in manifest["batches"] for sid in b["session_ids"]]

    assert ids == [f"copilot:s{i}" for i in range(5)]
    assert [len(b["session_ids"]) for b in manifest["batches"]] == [2, 2, 1]
    assert manifest["total_sessions"] == 5


def test_assignment_records_stratum_rule_candidates_cap_and_digest(batch: Row) -> None:
    assert batch["stratum"] == "skill_first"
    assert batch["selection_rule"] == "R W"
    assert batch["candidate_count"] == 40
    assert batch["cap"] == 12
    assert len(batch["source_digest"]) == 64
    assert batch["representative"] is False
    assert batch["non_probability_note"]


def test_repeated_assignment_is_identical_regardless_of_session_order() -> None:
    inventory = _inventory(5)
    shuffled = copy.deepcopy(inventory)
    shuffled["sessions"].reverse()
    shuffled["generated_at"] = "2030-01-01T00:00:00+00:00"

    first = ab.build_assignment(inventory, 2)
    second = ab.build_assignment(shuffled, 2)

    assert first == second
    assert ab.build_assignment(inventory, 2) == first


def test_digest_changes_when_membership_changes() -> None:
    assert (
        ab.build_assignment(_inventory(5), 2)["source_digest"]
        != (ab.build_assignment(_inventory(4), 2)["source_digest"])
    )


def test_digest_includes_audit_manifest_fingerprint() -> None:
    plain = ab.source_digest(_inventory())
    with_manifest = ab.source_digest(_inventory(), {"fingerprint": "abc"})
    other_manifest = ab.source_digest(_inventory(), {"fingerprint": "def"})

    assert len({plain, with_manifest, other_manifest}) == 3


def test_strata_become_separate_batches_with_their_own_metadata() -> None:
    inventory = _inventory(3, extra=2)
    inventory["sampling"]["timeline_supplement"] = {"requested": 2}
    inventory["sampling"]["strata"] = {
        "skill_first": {"candidates": 30, "rule": "SF"},
        "timeline_supplement": {"candidates": 9, "rule": "TL"},
    }

    batches = ab.build_assignment(inventory, 10)["batches"]

    assert [b["stratum"] for b in batches] == ["skill_first", "timeline_supplement"]
    assert [(b["candidate_count"], b["cap"], b["selection_rule"]) for b in batches] == [
        (30, 12, "SF"),
        (9, 2, "TL"),
    ]


def test_zero_sampled_sessions_gives_no_batches() -> None:
    inventory = _inventory(0)

    result = ab.build_assignment(inventory, 3)

    assert result["batches"] == []
    assert result["total_sessions"] == 0


def test_batch_size_below_one_is_rejected() -> None:
    with pytest.raises(ValueError, match="batch_size"):
        ab.build_assignment(_inventory(), 0)


def test_inventory_without_sessions_list_is_rejected() -> None:
    with pytest.raises(ab.ImportRejectedError):
        ab.build_assignment({"sampling": {}}, 2)


# -------------------------------------------------------------------- import


def test_full_import_leaves_exactly_one_accepted_score_per_assigned_record(
    tmp_path: Path, manifest: Row
) -> None:
    path = tmp_path / "accepted.json"

    for b in manifest["batches"]:
        ab.import_scores(b, path, _rows(b))

    data = json.loads(path.read_text(encoding="utf-8"))
    ids = [row["session_id"] for row in data["sessions"]]
    assigned = [sid for b in manifest["batches"] for sid in b["session_ids"]]
    assert sorted(ids) == sorted(assigned)
    assert len(ids) == len(set(ids))
    assert data["source_digest"] == manifest["source_digest"]
    assert ab.unscored_ids(manifest, path) == []


def test_unscored_ids_lists_batches_not_yet_imported(accepted: Path, manifest: Row) -> None:
    assert ab.unscored_ids(manifest, accepted) == ["copilot:s0", "copilot:s1", "copilot:s4"]


def test_reimporting_a_batch_replaces_instead_of_double_counting(
    accepted: Path, manifest: Row
) -> None:
    second = manifest["batches"][1]

    summary = ab.import_scores(second, accepted, _rows(second))

    assert summary["total"] == 2
    assert len(json.loads(accepted.read_text(encoding="utf-8"))["sessions"]) == 2


def _drop_first(rows: list[Row]) -> list[Row]:
    return rows[1:]


def _add_extra(rows: list[Row]) -> list[Row]:
    return [*rows, {**rows[0], "session_id": "copilot:other"}]


def _duplicate(rows: list[Row]) -> list[Row]:
    return [*rows, copy.deepcopy(rows[0])]


def _bad_label(rows: list[Row]) -> list[Row]:
    rows[0]["scores"]["efficiency"]["label"] = "not_a_label"
    return rows


def _bad_value(rows: list[Row]) -> list[Row]:
    rows[0]["scores"]["verbosity"]["score"] = 0.99
    return rows


def _no_scores(rows: list[Row]) -> list[Row]:
    del rows[0]["scores"]
    return rows


def _not_an_object(rows: list[Row]) -> list[Row]:
    rows[0] = "oops"  # type: ignore[call-overload]
    return rows


def _blank_id(rows: list[Row]) -> list[Row]:
    rows[0]["session_id"] = "  "
    return rows


def _foreign_batch(rows: list[Row]) -> list[Row]:
    rows[0]["batch_id"] = "batch-009-deadbeef0000"
    return rows


def _foreign_digest(rows: list[Row]) -> list[Row]:
    rows[0]["source_digest"] = "0" * 64
    return rows


def _missing_identity(rows: list[Row]) -> list[Row]:
    del rows[0]["batch_id"]
    return rows


def _foreign_stratum(rows: list[Row]) -> list[Row]:
    rows[0]["stratum"] = "timeline_supplement"
    return rows


INVALID = [
    (_drop_first, "missing session_id"),
    (_add_extra, "extra session_id"),
    (_duplicate, "duplicate session_id"),
    (_bad_label, "unknown label"),
    (_bad_value, "requires score"),
    (_no_scores, "scores must be an object"),
    (_not_an_object, "must be an object"),
    (_blank_id, "malformed"),
    (_foreign_batch, "foreign assignment"),
    (_foreign_digest, "foreign assignment"),
    (_missing_identity, "foreign assignment"),
    (_foreign_stratum, "foreign assignment"),
]


@pytest.mark.parametrize(("mutate", "message"), INVALID, ids=[m.__name__ for m, _ in INVALID])
def test_invalid_rows_are_rejected_and_the_accepted_file_is_unchanged(
    accepted: Path, manifest: Row, mutate: Any, message: str
) -> None:
    target = manifest["batches"][0]
    before = accepted.read_bytes()

    with pytest.raises(ab.ImportRejectedError) as raised:
        ab.import_scores(target, accepted, mutate(_rows(target)))

    assert message in "; ".join(raised.value.errors)
    assert accepted.read_bytes() == before
    assert not list(accepted.parent.glob(".audit_scores.*"))


def test_invalid_first_import_creates_no_accepted_file(tmp_path: Path, batch: Row) -> None:
    path = tmp_path / "accepted.json"

    with pytest.raises(ab.ImportRejectedError):
        ab.import_scores(batch, path, _drop_first(_rows(batch)))

    assert not path.exists()


def test_rows_that_are_not_a_list_are_rejected(tmp_path: Path, batch: Row) -> None:
    with pytest.raises(ab.ImportRejectedError, match="list"):
        ab.import_scores(batch, tmp_path / "a.json", {"sessions": []})


def test_tampered_assignment_is_rejected(tmp_path: Path, batch: Row) -> None:
    tampered = {**batch, "session_ids": [*batch["session_ids"], "copilot:s9"]}

    with pytest.raises(ab.ImportRejectedError, match="altered"):
        ab.import_scores(tampered, tmp_path / "a.json", _rows(tampered))


def test_assignment_missing_fields_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ab.ImportRejectedError, match="assignment must be"):
        ab.import_scores({"batch_id": "x"}, tmp_path / "a.json", [])


def test_stale_digest_requires_a_new_assignment(accepted: Path) -> None:
    other = ab.build_assignment(_inventory(6), 2)["batches"][0]
    before = accepted.read_bytes()

    with pytest.raises(ab.ImportRejectedError, match="new assignment"):
        ab.import_scores(other, accepted, _rows(other))

    assert accepted.read_bytes() == before


def test_corrupt_accepted_file_is_rejected_and_untouched(tmp_path: Path, batch: Row) -> None:
    path = tmp_path / "accepted.json"
    path.write_text("{not json", encoding="utf-8")

    with pytest.raises(ab.ImportRejectedError, match="unreadable"):
        ab.import_scores(batch, path, _rows(batch))

    assert path.read_text(encoding="utf-8") == "{not json"


def test_accepted_file_with_wrong_shape_is_rejected(tmp_path: Path, batch: Row) -> None:
    path = tmp_path / "accepted.json"
    path.write_text("[]", encoding="utf-8")

    with pytest.raises(ab.ImportRejectedError, match="accepted-scores object"):
        ab.import_scores(batch, path, _rows(batch))


def test_interrupted_write_leaves_the_accepted_file_unchanged(
    accepted: Path, manifest: Row, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = manifest["batches"][0]
    before = accepted.read_bytes()

    def explode(*_args: Any, **_kwargs: Any) -> None:
        raise OSError("simulated crash during replace")

    monkeypatch.setattr(os, "replace", explode)

    with pytest.raises(OSError, match="simulated crash"):
        ab.import_scores(target, accepted, _rows(target))

    assert accepted.read_bytes() == before
    assert not list(accepted.parent.glob(".audit_scores.*"))


def test_provider_termination_is_preserved_and_not_counted_as_agent_failure(
    tmp_path: Path, batch: Row
) -> None:
    first, second = batch["session_ids"]
    cut = _row(batch, first, terminated_by="provider_limit")
    cut["scores"]["efficiency"] = _score("efficiency", "highly_inefficient")
    path = tmp_path / "accepted.json"

    ab.import_scores(batch, path, [cut, _row(batch, second)])

    stored = json.loads(path.read_text(encoding="utf-8"))["sessions"]
    assert stored[0]["terminated_by"] == "provider_limit"
    failures = audit_scores.failed_conversations(stored)
    assert failures["count"] == 0
    assert failures["excluded_session_ids"] == [first]


def test_import_accepts_pre_cutoff_failure_even_when_terminated(tmp_path: Path, batch: Row) -> None:
    first, second = batch["session_ids"]
    cut = _row(batch, first, terminated_by="provider_limit")
    cut["scores"]["efficiency"] = {
        **_score("efficiency", "highly_inefficient"),
        "pre_cutoff": True,
    }
    path = tmp_path / "accepted.json"

    ab.import_scores(batch, path, [cut, _row(batch, second)])

    stored = json.loads(path.read_text(encoding="utf-8"))["sessions"]
    assert audit_scores.failed_conversations(stored)["count"] == 1
