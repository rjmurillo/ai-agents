"""Renames, multiple hunks, and hunk-boundary cases for line-scoped gating."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from diff_scope_helpers import (
    FENCE,
    by_symbol,
    commit,
    edit_and_commit,
    example,
    gate_diff,
    git,
    make_repo,
    mod,
)

BASE = "HEAD~1"
TWO = "# T\n\n" + example("Alpha") + "\ntext\n\n" + example("Beta")


def test_pure_rename_keeps_old_findings_out_of_scope(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, {"old.md": "# T\n\n" + example("Ghost")})
    git(repo, "mv", "old.md", "moved.md")
    commit(repo)

    code, data = gate_diff(repo, tmp_path)

    assert code == 0
    assert data["findings"][0]["file"] == "moved.md"
    assert data["findings"][0]["in_diff"] is False


def test_rename_with_edit_scopes_to_edited_hunk(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, {"old.md": TWO})
    git(repo, "mv", "old.md", "moved.md")
    edit_and_commit(repo, "moved.md", TWO.replace("Beta", "Gamma"))

    _, data = gate_diff(repo, tmp_path)

    found = by_symbol(data)
    assert found["Gamma"]["in_diff"] is True
    assert found["Alpha"]["in_diff"] is False


def test_multiple_hunks_each_scope_their_own_block(tmp_path: Path) -> None:
    pad = "".join(f"filler {n}\n" for n in range(6))
    old = "# T\n\n" + example("One") + pad + example("Two") + pad + example("Three")
    repo = make_repo(tmp_path, {"doc.md": old})
    edit_and_commit(repo, "doc.md", old.replace("One", "Uno").replace("Three", "Tres"))

    _, data = gate_diff(repo, tmp_path)

    got = {s: f["in_diff"] for s, f in by_symbol(data).items()}
    assert got == {"Uno": True, "Two": False, "Tres": True}


def test_claim_spanning_hunk_boundary_and_pure_deletion_are_in_scope(
    tmp_path: Path,
) -> None:
    old = f"# T\n\n{FENCE}python\nx = Ghost()\ny = 1\nz = 2\n{FENCE}\n"
    repo = make_repo(tmp_path, {"doc.md": old})
    edit_and_commit(repo, "doc.md", old.replace("z = 2", "z = 3"))
    _, edited = gate_diff(repo, tmp_path)
    edit_and_commit(repo, "doc.md", old.replace("z = 2\n", "").replace("y = 1\n", ""))

    _, deleted = gate_diff(repo, tmp_path)

    assert edited["findings"][0]["in_diff"] is True
    assert deleted["findings"][0]["in_diff"] is True


def test_file_without_hunks_is_changed_in_full(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, {"doc.md": "# T\n\n" + example("Ghost")})
    git(repo, "update-index", "--chmod=+x", "doc.md")
    git(repo, "commit", "-q", "-m", "mode only")

    result = mod.run_assessment(repo, diff_base=BASE)

    assert result["changed_lines"]["doc.md"] == [[1, 6]]
