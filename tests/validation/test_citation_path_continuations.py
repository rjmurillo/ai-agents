"""A full repository path sets the filename for a later bare range."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from scripts.validation.citation_continuations import _expand_continuations
from tests.validation.citation_freshness_helpers import TARGET, _git, _repo, _run

_SCRIPT = (
    Path(__file__).resolve().parents[2] / "scripts" / "validation" / "citation_reverse_pass.py"
)


def _run_reverse(root: Path) -> tuple[int, str]:
    """Run the reverse pass CLI against one fixture repository."""
    proc = subprocess.run(
        [sys.executable, str(_SCRIPT), "--repo-root", str(root), "--base", "main"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        check=False,
    )
    return proc.returncode, proc.stdout + proc.stderr


def test_full_path_binds_a_later_bare_range() -> None:
    """A repository path makes a following bare range cite that same file."""
    name = "util.py"
    index = {name: [f"lib/{name}"]}
    text = f"See lib/{name}:3 and :99."
    assert _expand_continuations(text, index) == f"See lib/{name}:3 and lib/{name}:99."


def test_a_decimal_after_a_filename_is_not_a_bare_range() -> None:
    """A JSON measurement's decimal value never binds to an earlier filename."""
    name = "util.py"
    index = {name: [f"lib/{name}"]}
    text = f'{{"files":["lib/{name}"],"min":118.22,"max":128.43}}'
    assert _expand_continuations(text, index) == text


def test_a_bare_range_ending_a_sentence_still_binds() -> None:
    """A trailing period after a bare range is punctuation, not a decimal."""
    name = "util.py"
    index = {name: [f"lib/{name}"]}
    text = f"See lib/{name}:3 and :99. Then stop."
    assert _expand_continuations(text, index) == f"See lib/{name}:3 and lib/{name}:99. Then stop."


def test_url_and_parent_paths_do_not_bind_a_bare_range() -> None:
    """URLs, dot-slash paths, and parent paths do not donate a filename."""
    name = "util.py"
    index = {name: [f"lib/{name}"]}
    samples = (
        f"See https://example.com/lib/{name}:3 and :99.",
        f"See ../lib/{name}:3 and :99.",
        f"See ./lib/{name}:3 and :99.",
    )
    for text in samples:
        assert text.endswith(":99.")
        assert _expand_continuations(text, index).endswith(":99.")


def test_forward_checks_a_bare_range_after_a_full_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """An added full-path cite plus :99 fails when line 99 does not exist."""
    root = _repo(tmp_path)
    line = f"See {TARGET}:3 and :99 for `magic_token`.\n"
    doc = root / "docs" / "notes.md"
    doc.parent.mkdir(parents=True)
    doc.write_text(line, encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "cite")

    code, out = _run(root, capsys)

    assert code == 1, out
    assert "99" in out


def test_reverse_checks_a_bare_range_after_a_full_path(tmp_path: Path) -> None:
    """A kept full-path cite plus :4 fails once line 4 disappears."""
    root = _repo(tmp_path)
    _git(root, "checkout", "-q", "main")
    held = "# helper module\nPLACEHOLDER = 0\ndef magic_token():\n    return magic_token()\n"
    target = root / TARGET
    target.write_text(held, encoding="utf-8")
    doc = root / "docs" / "notes.md"
    doc.parent.mkdir(parents=True)
    doc.write_text(f"See {TARGET}:3 and :4 for `magic_token`.\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "cite")
    _git(root, "checkout", "-q", "-B", "feature")
    target.write_text("\n".join(held.splitlines()[:3]) + "\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "truncate")

    code, out = _run_reverse(root)

    assert code == 1, out
    assert "4" in out
