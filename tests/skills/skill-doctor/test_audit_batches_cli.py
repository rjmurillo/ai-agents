"""audit_batches CLI exit codes and write behavior (epic #7248, M2)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import audit_batches as ab
import pytest
from audit_batch_helpers import Row, _inventory, _rows


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


# ----------------------------------------------------------------------- CLI


def _write(path: Path, data: Any) -> Path:
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_cli_assign_writes_manifest_and_batches_and_is_repeatable(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    inv = _write(tmp_path / "inventory.json", _inventory(3))
    out = tmp_path / "out"

    assert ab.main(["assign", str(inv), "--batch-size", "2", "--out", str(out)]) == 0
    first = {p.name: p.read_bytes() for p in out.iterdir()}
    assert ab.main(["assign", str(inv), "--batch-size", "2", "--out", str(out)]) == 0

    assert {p.name: p.read_bytes() for p in out.iterdir()} == first
    assert ab.MANIFEST_FILENAME in first
    assert len(first) == 3
    assert "2 batches, 3 sessions" in capsys.readouterr().out


def test_cli_assign_accepts_an_audit_manifest(tmp_path: Path) -> None:
    inv = _write(tmp_path / "inventory.json", _inventory(2))
    audit = _write(tmp_path / "audit_manifest.json", {"fingerprint": "f" * 64})
    plain_out, bound_out = tmp_path / "plain", tmp_path / "bound"

    assert ab.main(["assign", str(inv), "--batch-size", "5", "--out", str(plain_out)]) == 0
    code = ab.main(
        [
            "assign",
            str(inv),
            "--batch-size",
            "5",
            "--out",
            str(bound_out),
            "--audit-manifest",
            str(audit),
        ]
    )

    assert code == 0
    digests = [
        json.loads((out / ab.MANIFEST_FILENAME).read_text(encoding="utf-8"))["source_digest"]
        for out in (plain_out, bound_out)
    ]
    assert digests[0] != digests[1]


def test_cli_assign_refuses_to_overwrite_a_different_assignment(tmp_path: Path) -> None:
    out = tmp_path / "out"
    first = _write(tmp_path / "a.json", _inventory(3))
    second = _write(tmp_path / "b.json", _inventory(4))
    assert ab.main(["assign", str(first), "--batch-size", "2", "--out", str(out)]) == 0
    before = {p.name: p.read_bytes() for p in out.iterdir()}

    code = ab.main(["assign", str(second), "--batch-size", "2", "--out", str(out)])

    assert code == 1
    assert {p.name: p.read_bytes() for p in out.iterdir()} == before


def test_cli_assign_inventory_without_sessions_exits_1(tmp_path: Path) -> None:
    inv = _write(tmp_path / "inventory.json", {"sampling": {}})

    assert ab.main(["assign", str(inv), "--batch-size", "2", "--out", str(tmp_path / "o")]) == 1


@pytest.mark.parametrize("size", ["0", "-3"])
def test_cli_assign_non_positive_batch_size_exits_2(tmp_path: Path, size: str) -> None:
    inv = _write(tmp_path / "inventory.json", _inventory(2))

    assert ab.main(["assign", str(inv), "--batch-size", size, "--out", str(tmp_path / "o")]) == 2


def test_cli_assign_unreadable_inventory_exits_2(tmp_path: Path) -> None:
    code = ab.main(
        ["assign", str(tmp_path / "missing.json"), "--batch-size", "2", "--out", str(tmp_path)]
    )

    assert code == 2


def test_cli_assign_invalid_json_exits_2(tmp_path: Path) -> None:
    inv = tmp_path / "inventory.json"
    inv.write_text("{nope", encoding="utf-8")

    assert ab.main(["assign", str(inv), "--batch-size", "2", "--out", str(tmp_path / "o")]) == 2


@pytest.mark.parametrize(
    "argv",
    [[], ["bogus"], ["assign"], ["assign", "inv.json"], ["import", "a.json", "r.json"]],
)
def test_cli_bad_arguments_exit_2(argv: list[str]) -> None:
    assert ab.main(argv) == 2


def test_cli_import_ok_then_invalid_leaves_accepted_unchanged(tmp_path: Path, batch: Row) -> None:
    assignment = _write(tmp_path / "batch.json", batch)
    good = _write(tmp_path / "rows.json", {"sessions": _rows(batch)})
    bad = _write(tmp_path / "bad.json", _rows(batch)[1:])
    accepted = tmp_path / "accepted.json"

    assert ab.main(["import", str(assignment), str(good), "--accepted", str(accepted)]) == 0
    before = accepted.read_bytes()
    code = ab.main(["import", str(assignment), str(bad), "--accepted", str(accepted)])

    assert code == 1
    assert accepted.read_bytes() == before


def test_cli_import_unreadable_rows_exits_2(tmp_path: Path, batch: Row) -> None:
    assignment = _write(tmp_path / "batch.json", batch)

    code = ab.main(
        [
            "import",
            str(assignment),
            str(tmp_path / "missing.json"),
            "--accepted",
            str(tmp_path / "accepted.json"),
        ]
    )

    assert code == 2


def test_cli_import_write_failure_exits_2_and_keeps_file(
    accepted: Path, manifest: Row, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = manifest["batches"][0]
    assignment = _write(tmp_path / "batch.json", target)
    rows = _write(tmp_path / "rows.json", _rows(target))
    before = accepted.read_bytes()

    def explode(*_args: Any, **_kwargs: Any) -> None:
        raise OSError("simulated crash")

    monkeypatch.setattr(os, "replace", explode)

    assert ab.main(["import", str(assignment), str(rows), "--accepted", str(accepted)]) == 2
    assert accepted.read_bytes() == before
