"""Adversarial tests: a PR must not forge diff structure to dodge the gate.

Each test adds a wrong claim (``Ghost``) and tries to make the scoper
attribute its hunk elsewhere or shift its line numbers. The claim must block.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from diff_scope_helpers import FENCE, FILLER, edit_and_commit, example, gate_diff, make_repo, mod

BASE = "HEAD~1"
WRONG = example("Ghost")


def _assert_ghost_blocks(code: int, data: dict) -> None:
    ghost = [f for f in data["findings"] if f["evidence"]["symbol"] == "Ghost"]
    assert code == 10
    assert len(ghost) == 1
    assert ghost[0]["in_diff"] is True
    assert ghost[0]["severity"] == "high"
    assert "original_severity" not in ghost[0]


@pytest.mark.parametrize(
    "forged_line",
    [
        "a\x0c+++ b/other.md",  # form feed splits lines for str.splitlines
        "a\x1c@@ -1 +900 @@",  # same, forging a hunk header
        "++ b/other.md",  # patch shows it as "+++ b/other.md"
        "a" + "\r" * 40,  # lone CRs shift Python line numbers, not git's
    ],
    ids=["form-feed-file-header", "separator-hunk-header", "plus-plus-line", "lone-cr"],
)
def test_forged_line_cannot_hide_a_later_wrong_claim(
    tmp_path: Path, forged_line: str
) -> None:
    """Hunk 1 adds ``forged_line``; a later, separate hunk adds the wrong claim."""
    base = "# T\n\nintro\n\n" + FILLER + "\ntail\n"
    repo = make_repo(tmp_path, {"doc.md": base})
    new = "# T\n\n" + forged_line + "\n\n" + FILLER + "\ntail\n\n" + WRONG
    edit_and_commit(repo, "doc.md", new.encode())

    code, data = gate_diff(repo, tmp_path)

    _assert_ghost_blocks(code, data)


def test_added_dev_null_line_does_not_drop_later_hunk(tmp_path: Path) -> None:
    lines = [f"l{n}" for n in range(1, 31)]
    repo = make_repo(tmp_path, {"doc.md": "\n".join(lines) + "\n"})
    new = lines[:1] + ["++ /dev/null"] + lines[1:19] + ["BAD"] + lines[20:]
    edit_and_commit(repo, "doc.md", "\n".join(new) + "\n")

    _, ranges = mod._get_changed_diff(BASE, repo)

    assert ranges["doc.md"] == [[2, 2], [21, 21]]


def test_crlf_doc_new_wrong_claim_blocks(tmp_path: Path) -> None:
    base = "# T\r\n\r\nintro\r\n"
    repo = make_repo(tmp_path, {"doc.md": base})
    edit_and_commit(repo, "doc.md", (base + "\r\n" + WRONG.replace("\n", "\r\n")).encode())

    code, data = gate_diff(repo, tmp_path)

    _assert_ghost_blocks(code, data)


def test_crlf_doc_untouched_example_stays_info(tmp_path: Path) -> None:
    base = "# T\r\n\r\n" + WRONG.replace("\n", "\r\n") + "\r\nintro\r\n"
    repo = make_repo(tmp_path, {"doc.md": base})
    edit_and_commit(repo, "doc.md", base.replace("intro", "outro").encode())

    code, data = gate_diff(repo, tmp_path)

    assert code == 0
    assert data["findings"][0]["severity"] == "info"


def test_textconv_filter_cannot_shift_line_numbers(tmp_path: Path) -> None:
    """A textconv driver for *.md must not change the hunks git reports."""
    base = "# T\n\nintro\n\n" + FILLER
    repo = make_repo(tmp_path, {"doc.md": base})
    (repo / ".gitattributes").write_text("*.md diff=strip\n")
    (repo / ".git" / "config").write_text(
        (repo / ".git" / "config").read_text()
        + "[diff \"strip\"]\n\ttextconv = sed 1,5d\n"
    )
    edit_and_commit(repo, "doc.md", base + FENCE + "text\nGhost\n" + FENCE + "\n")

    _, ranges = mod._get_changed_diff(BASE, repo)

    assert ranges["doc.md"][0][1] == base.count("\n") + 3
