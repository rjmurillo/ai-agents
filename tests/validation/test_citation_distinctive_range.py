"""A name that occurs on both sides of a range does not prove the range.

The citing line names several rare tokens. One of them also occurs inside
the wrong block. That mixed hit must not hide the names that sit outside.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.validation.citation_freshness_helpers import _add_doc, _git, _repo, _run

_CITED = "hooks/group.yml"
_BODY = "memory-index arg\nplain\nmemory-size: 1\nmemory-index job\nmemory-tier: 1\n"


def _prepare(tmp_path: Path, citation: str) -> Path:
    root = _repo(tmp_path)
    _git(root, "checkout", "-q", "main")
    _add_doc(root, _CITED, _BODY)
    _git(root, "checkout", "-q", "-B", "feature")
    line = f"See `{_CITED}:{citation}` for `memory-index`, `memory-size`, and `memory-tier`.\n"
    _add_doc(root, "docs/notes.md", line)
    return root


def test_mixed_hit_does_not_keep_two_names_outside(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """One in-range copy of a name does not save two names found only outside."""
    root = _prepare(tmp_path, "1")

    code, out = _run(root, capsys)

    assert code == 1, out
    assert "distinctive anchors" in out


def test_same_names_keep_a_range_that_holds_them(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A range that holds the named jobs stays quiet when one name also occurs earlier."""
    root = _prepare(tmp_path, "3-5")

    code, out = _run(root, capsys)

    assert code == 0, out
