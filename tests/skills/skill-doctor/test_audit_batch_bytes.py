"""Byte-capped review batches: a scorer batch closes before its transcripts pass the cap."""

from __future__ import annotations

import json
from pathlib import Path

import audit_batches as ab
import pytest
from audit_batch_helpers import _inventory, _rows


def _sized_inventory(tmp_path: Path, sizes: list[int]) -> dict:
    inventory = _inventory(len(sizes))
    for session, size in zip(inventory["sessions"], sizes, strict=False):
        path = tmp_path / f"{session['meta']['id']}.md"
        path.write_bytes(b"x" * size)
        session["transcript_path"] = str(path)
    return inventory


def _sizes(assignment: dict) -> list[int]:
    return [batch["transcript_bytes"] for batch in assignment["batches"]]


def test_byte_cap_closes_a_batch_before_it_passes_the_cap(tmp_path: Path) -> None:
    inventory = _sized_inventory(tmp_path, [60, 60, 60, 60, 60])
    assignment = ab.build_assignment(inventory, 20, max_batch_bytes=150)
    assert [len(b["session_ids"]) for b in assignment["batches"]] == [2, 2, 1]
    assert _sizes(assignment) == [120, 120, 60]
    assert assignment["max_batch_bytes"] == 150


def test_count_cap_still_binds_under_a_large_byte_cap(tmp_path: Path) -> None:
    inventory = _sized_inventory(tmp_path, [1, 1, 1, 1, 1])
    assignment = ab.build_assignment(inventory, 2, max_batch_bytes=10_000)
    assert [len(b["session_ids"]) for b in assignment["batches"]] == [2, 2, 1]


def test_oversize_transcript_gets_its_own_batch(tmp_path: Path) -> None:
    inventory = _sized_inventory(tmp_path, [10, 500, 10])
    assignment = ab.build_assignment(inventory, 20, max_batch_bytes=100)
    assert _sizes(assignment) == [10, 500, 10]


@pytest.mark.parametrize("path", ["gone.md", None, ""])
def test_unreadable_or_missing_transcript_counts_as_zero_bytes(tmp_path: Path, path) -> None:
    inventory = _sized_inventory(tmp_path, [40, 40])
    inventory["sessions"][0]["transcript_path"] = str(tmp_path / path) if path else path
    assignment = ab.build_assignment(inventory, 20, max_batch_bytes=50)
    assert _sizes(assignment) == [40]


def test_batch_rule_names_the_top_level_reservation(tmp_path: Path) -> None:
    inventory = _sized_inventory(tmp_path, [10])
    inventory["sampling"]["top_level_rule"] = "TOP"
    batch = ab.build_assignment(inventory, 20)["batches"][0]
    assert batch["selection_rule"] == "R W TOP"


def test_no_byte_cap_leaves_the_assignment_unchanged(tmp_path: Path) -> None:
    inventory = _sized_inventory(tmp_path, [60, 60, 60])
    assignment = ab.build_assignment(inventory, 2)
    assert "max_batch_bytes" not in assignment
    assert all("transcript_bytes" not in batch for batch in assignment["batches"])
    assert assignment == ab.build_assignment(_inventory(3), 2)


def test_byte_capped_batch_still_imports(tmp_path: Path) -> None:
    inventory = _sized_inventory(tmp_path, [60, 60, 60])
    batch = ab.build_assignment(inventory, 20, max_batch_bytes=150)["batches"][0]
    accepted = tmp_path / "scores.json"
    ab.import_scores(batch, accepted, _rows(batch))
    assert len(json.loads(accepted.read_text(encoding="utf-8"))["sessions"]) == 2


def test_zero_byte_cap_is_rejected() -> None:
    with pytest.raises(ValueError, match="max_batch_bytes"):
        ab.build_assignment(_inventory(2), 2, max_batch_bytes=0)


@pytest.mark.parametrize("value", ["0", "-5"])
def test_cli_non_positive_byte_cap_exits_2(tmp_path: Path, value: str) -> None:
    inv = tmp_path / "inventory.json"
    inv.write_text(json.dumps(_inventory(2)), encoding="utf-8")
    argv = ["assign", str(inv), "--batch-size", "2", "--max-batch-bytes", value]
    assert ab.main([*argv, "--out", str(tmp_path / "o")]) == 2


def test_cli_byte_cap_writes_byte_counts(tmp_path: Path) -> None:
    inv = tmp_path / "inventory.json"
    inv.write_text(json.dumps(_sized_inventory(tmp_path, [80, 80])), encoding="utf-8")
    out = tmp_path / "o"
    argv = ["assign", str(inv), "--batch-size", "20", "--max-batch-bytes", "100"]
    assert ab.main([*argv, "--out", str(out)]) == 0
    manifest = json.loads((out / ab.MANIFEST_FILENAME).read_text(encoding="utf-8"))
    assert manifest["max_batch_bytes"] == 100
    assert len(manifest["batches"]) == 2
