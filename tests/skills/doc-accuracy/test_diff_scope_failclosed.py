"""Scoping defaults closed: unknown or empty ranges mean changed in full."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from diff_scope_helpers import commit, example, gate_diff, git, make_repo, mod

CLAIM = {"id": "c1", "file": "docs/a.md", "line": 3, "end_line": 5, "type": "code_example"}


def _finding() -> dict:
    return {"claim_id": "c1", "severity": "high"}


@pytest.mark.parametrize(
    "changed_lines",
    [{}, {"docs/other.md": [[3, 3]]}, {"docs/a.md": []}],
    ids=["missing-file-key", "other-file-only", "empty-range-list"],
)
def test_unknown_or_empty_ranges_stay_blocking(changed_lines: dict) -> None:
    out = mod._scope_findings([_finding()], {"c1": CLAIM}, changed_lines)

    assert out[0]["in_diff"] is True
    assert out[0]["severity"] == "high"
    assert "original_severity" not in out[0]


def test_claim_path_spelling_is_normalized_before_lookup() -> None:
    claim = dict(CLAIM, file="./docs/a.md")

    out = mod._scope_findings([_finding()], {"c1": claim}, {"docs/a.md": [[9, 9]]})

    assert out[0]["in_diff"] is False


def test_pure_rename_marker_downgrades_untouched_claims(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, {"old.md": "# T\n\n" + example("Ghost")})
    git(repo, "mv", "old.md", "moved.md")
    commit(repo)

    code, data = gate_diff(repo, tmp_path)

    assert code == 0
    assert data["findings"][0]["severity"] == "info"
    assert mod.run_assessment(repo, diff_base="HEAD~1")["changed_lines"] == {
        "moved.md": [[0, 0]]
    }
