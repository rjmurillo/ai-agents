"""Issue 7460: a balanced fence edit must not gate an untouched example."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from diff_scope_helpers import (
    FENCE,
    by_symbol,
    edit_and_commit,
    example,
    gate_diff,
    make_repo,
)

BALANCED_BLOCK = f"new text\n\n{FENCE}bash\necho hi\n{FENCE}\n\n"
BASE_DOC = "# T\n\nintro\n\n" + example("Ghost")
MARKER = "<!-- doc-accuracy: external-sdk Foo -- vendored -->\n"


def _insert_above_example(doc: str, text: str) -> str:
    return doc.replace("intro\n\n", "intro\n\n" + text, 1)


def test_balanced_block_above_untouched_example_stays_info(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, {"doc.md": BASE_DOC})
    edit_and_commit(repo, "doc.md", _insert_above_example(BASE_DOC, BALANCED_BLOCK))

    code, data = gate_diff(repo, tmp_path)

    ghost = by_symbol(data)["Ghost"]
    assert code == 0
    assert ghost["severity"] == "info"
    assert ghost["in_diff"] is False


def test_single_added_fence_above_example_still_blocks(tmp_path: Path) -> None:
    # The lone fence re-pairs the file: prose once inside the skipped bash
    # block becomes a claim, and it is not on a changed line.
    base = f"# T\n\n{FENCE}bash\necho hi\nmethod accepts `Ghost`\n{FENCE}\n"
    repo = make_repo(tmp_path, {"doc.md": base})
    edit_and_commit(repo, "doc.md", base.replace("# T\n\n", f"# T\n\n{FENCE}\n", 1))

    code, data = gate_diff(repo, tmp_path)

    assert code == 10
    assert by_symbol(data)["Ghost"]["in_diff"] is True


def test_retagged_opening_fence_keeps_its_block_in_scope(tmp_path: Path) -> None:
    """Retagging ```text to ```csharp is even parity, but the block still gates.

    The removed and added fence lines net zero, so parity adds no range. The
    example's claim span starts on its opening fence, which the hunk covers, so
    findings the new language exposes stay blocking.
    """
    body = "".join(f"line {n}\n" for n in range(6))
    base = f"# T\n\nintro\n\n{FENCE}text\nvar g = new Ghost();\n{body}{FENCE}\n"
    repo = make_repo(tmp_path, {"doc.md": base})
    edit_and_commit(repo, "doc.md", base.replace(f"{FENCE}text", f"{FENCE}csharp", 1))

    code, data = gate_diff(repo, tmp_path)

    ghost = by_symbol(data)["Ghost"]
    assert code == 10
    assert ghost["severity"] == "high"
    assert ghost["in_diff"] is True


def test_balanced_block_above_honored_marker_keeps_findings_in_scope(tmp_path: Path) -> None:
    base = "# T\n" + MARKER + "\n" + example("Ghost")
    head = base.replace("# T\n", "# T\n\n" + BALANCED_BLOCK, 1)
    repo = make_repo(tmp_path, {"doc.md": base})
    edit_and_commit(repo, "doc.md", head)

    code, data = gate_diff(repo, tmp_path)

    ghost = by_symbol(data)["Ghost"]
    assert code == 10
    assert ghost["in_diff"] is True
    assert ghost["scope_reason"] == "ignored_external_sdk_marker"
    assert ghost["scope_marker_line"] == head.split("\n").index(MARKER.rstrip("\n")) + 1


def test_prose_edit_above_already_ignored_marker_stays_info(tmp_path: Path) -> None:
    """A marker below a fence was ignored at the base too; prose cannot flip it."""
    base = f"# T\n\nintro\n\n{FENCE}bash\necho hi\n{FENCE}\n\n" + MARKER + "\n" + example("Ghost")
    repo = make_repo(tmp_path, {"doc.md": base})
    edit_and_commit(repo, "doc.md", base.replace("intro", "intro two", 1))

    code, data = gate_diff(repo, tmp_path)

    ghost = by_symbol(data)["Ghost"]
    assert code == 0
    assert ghost["in_diff"] is False
    assert "scope_reason" not in ghost


def test_edited_stop_line_above_ignored_marker_keeps_findings_in_scope(tmp_path: Path) -> None:
    """Editing the first fence-like line above the marker can flip its status."""
    base = f"# T\n\nuse {FENCE} here\n\n" + MARKER + "\n" + example("Ghost")
    repo = make_repo(tmp_path, {"doc.md": base})
    edit_and_commit(repo, "doc.md", base.replace(f"use {FENCE} here", f"use {FENCE} there", 1))

    code, data = gate_diff(repo, tmp_path)

    assert code == 10
    assert by_symbol(data)["Ghost"]["scope_reason"] == "ignored_external_sdk_marker"


def test_prose_edit_below_example_keeps_marker_honored(tmp_path: Path) -> None:
    base = "# T\n" + MARKER + "\n" + example("Ghost") + "\ntail\n"
    repo = make_repo(tmp_path, {"doc.md": base})
    edit_and_commit(repo, "doc.md", base.replace("tail", "tail two"))

    code, data = gate_diff(repo, tmp_path)

    assert code == 0
    assert not [f for f in data["findings"] if f["severity"] != "info"]
