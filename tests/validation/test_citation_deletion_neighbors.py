"""A deletion-only hunk still selects citations on the lines beside it."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.validation.citation_freshness_helpers import TARGET, _git, _repo, _run


def _commit(root: Path, relpath: str, text: str, message: str) -> None:
    path = root / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", message)


def test_deletion_beside_a_stale_cite_is_checked(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Deleting only the next line still checks the stale cite above it."""
    root = _repo(tmp_path)
    _git(root, "checkout", "-q", "main")
    _commit(
        root,
        "docs/notes.md",
        f"See `{TARGET}:1` for `magic_token`.\nkeep\n",
        "cite",
    )
    _git(root, "checkout", "-q", "-B", "feature")
    _commit(root, "docs/notes.md", f"See `{TARGET}:1` for `magic_token`.\n", "drop")

    code, out = _run(root, capsys)

    assert code == 1, out
    assert "magic_token" in out


def test_deletion_beside_a_fresh_cite_stays_quiet(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A neighboring cite whose anchor is in range stays quiet."""
    root = _repo(tmp_path)
    _git(root, "checkout", "-q", "main")
    _commit(
        root,
        "docs/notes.md",
        f"See `{TARGET}:3` for `magic_token`.\nkeep\n",
        "cite",
    )
    _git(root, "checkout", "-q", "-B", "feature")
    _commit(root, "docs/notes.md", f"See `{TARGET}:3` for `magic_token`.\n", "drop")

    code, out = _run(root, capsys)

    assert code == 0, out


def test_deletion_anchor_is_not_an_authored_claim(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Forward leaves a neighbor cite into a changed file for the reverse pass."""
    root = _repo(tmp_path)
    _git(root, "checkout", "-q", "main")
    _commit(
        root,
        "docs/notes.md",
        f"See `{TARGET}:1` for `magic_token`.\nkeep\n",
        "cite",
    )
    _git(root, "checkout", "-q", "-B", "feature")
    _commit(root, "docs/notes.md", f"See `{TARGET}:1` for `magic_token`.\n", "drop")
    target = root / TARGET
    target.write_text(target.read_text(encoding="utf-8") + "extra = 1\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "touch target")

    code, out = _run(root, capsys)

    assert code == 0, out
