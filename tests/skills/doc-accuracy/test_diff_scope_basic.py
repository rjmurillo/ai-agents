"""Line-scoped gating in --diff-base mode: in-scope blocks, out-of-scope is info."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from diff_scope_helpers import (
    by_symbol,
    edit_and_commit,
    example,
    gate_diff,
    gate_result,
    make_repo,
    run_gate,
)


def test_untouched_illustrative_block_does_not_block(tmp_path: Path) -> None:
    body = "# T\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n" + example("Ghost")
    repo = make_repo(tmp_path, {"doc.md": body})
    edit_and_commit(repo, "doc.md", body.replace("| 1 | 2 |", "| 3 | 4 |"))

    code, data = gate_diff(repo, tmp_path)

    assert code == 0
    assert gate_result(tmp_path)["verdict"] == "PASS"
    assert gate_result(tmp_path)["blocking_findings"] == 0
    finding = data["findings"][0]
    assert (finding["severity"], finding["original_severity"]) == ("info", "high")
    assert finding["in_diff"] is False


def test_finding_inside_changed_hunk_still_blocks(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, {"doc.md": "# T\n\n" + example("Real")})
    edit_and_commit(repo, "doc.md", "# T\n\n" + example("Ghost"))

    code, data = gate_diff(repo, tmp_path)

    finding = data["findings"][0]
    assert code == 10
    assert (finding["severity"], finding["in_diff"]) == ("high", True)
    assert "original_severity" not in finding


def test_mixed_blocks_only_touched_one_blocks(tmp_path: Path) -> None:
    old = "# T\n\n" + example("Alpha") + "\ntext\n\n" + example("Beta")
    repo = make_repo(tmp_path, {"doc.md": old})
    edit_and_commit(repo, "doc.md", old.replace("Beta", "Gamma"))

    code, data = gate_diff(repo, tmp_path)

    found = by_symbol(data)
    assert code == 10
    assert found["Gamma"]["in_diff"] is True
    assert found["Alpha"]["severity"] == "info"
    assert gate_result(tmp_path)["blocking_findings"] == 1


def test_new_file_is_in_scope_on_every_line(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, {})
    edit_and_commit(repo, "new.md", "# New\n\n" + example("Ghost"))

    code, data = gate_diff(repo, tmp_path)

    assert code == 10
    assert data["findings"][0]["in_diff"] is True


def test_edit_after_block_does_not_touch_block(tmp_path: Path) -> None:
    old = "# T\n\n" + example("Ghost") + "\ntail one\n"
    repo = make_repo(tmp_path, {"doc.md": old})
    edit_and_commit(repo, "doc.md", old.replace("tail one", "tail two"))

    code, data = gate_diff(repo, tmp_path)

    assert code == 0
    assert data["findings"][0]["in_diff"] is False


def test_without_diff_base_untouched_block_still_blocks(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, {"doc.md": "# T\n\n" + example("Ghost")})

    code, data = run_gate(repo, tmp_path)

    finding = data["findings"][0]
    assert code == 10
    assert finding["severity"] == "high"
    assert "in_diff" not in finding
    assert "original_severity" not in finding
