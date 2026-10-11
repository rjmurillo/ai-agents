"""Fence edits and symlinks: claims the diff did not touch but still changed."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from diff_scope_helpers import commit, edit_and_commit, example, gate_diff, git, make_repo

PROSE = "method accepts `Ghost`"
SKIPPED_BLOCK = f"# T\n\n```bash\necho hi\n{PROSE}\n```\n"


@pytest.mark.parametrize(
    "new_doc",
    [
        SKIPPED_BLOCK.replace("```bash\n", "", 1),
        SKIPPED_BLOCK.replace("```bash", "``bash", 1),
        SKIPPED_BLOCK.replace("```bash", "  ~~~bash", 1),
    ],
    ids=["fence-deleted", "fence-broken", "fence-restyled"],
)
def test_changed_fence_puts_later_claims_in_scope(tmp_path: Path, new_doc: str) -> None:
    """Unpaired fences re-pair; prose once inside a skipped block becomes a claim."""
    repo = make_repo(tmp_path, {"doc.md": SKIPPED_BLOCK})
    edit_and_commit(repo, "doc.md", new_doc)

    code, data = gate_diff(repo, tmp_path)

    assert code == 10
    assert data["findings"][0]["in_diff"] is True


def test_edit_far_from_any_fence_keeps_untouched_claim_info(tmp_path: Path) -> None:
    old = "# T\n\nintro\n\n" + example("Ghost")
    repo = make_repo(tmp_path, {"doc.md": old})
    edit_and_commit(repo, "doc.md", old.replace("intro", "outro"))

    code, data = gate_diff(repo, tmp_path)

    assert code == 0
    assert data["findings"][0]["severity"] == "info"


@pytest.mark.skipif(os.name == "nt", reason="needs symlink support")
def test_repointed_symlink_doc_is_gated_in_full(tmp_path: Path) -> None:
    """git diffs only the link text, but the claims come from the new target."""
    repo = make_repo(
        tmp_path,
        {"good.md": "# Good\n", "bad.md": "# Bad\n\n" + example("Ghost")},
    )
    (repo / "link.md").symlink_to("good.md")
    commit(repo)
    (repo / "link.md").unlink()
    (repo / "link.md").symlink_to("bad.md")
    commit(repo)
    git(repo, "log", "-1")

    code, data = gate_diff(repo, tmp_path)

    link = [f for f in data["findings"] if f["file"] == "link.md"]
    assert code == 10
    assert link and link[0]["in_diff"] is True
