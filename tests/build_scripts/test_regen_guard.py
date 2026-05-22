"""Tests for build/scripts/regen_guard.py (REQ-003-008)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "build" / "scripts"))

import regen_guard  # noqa: E402


def test_missing_file_is_not_protected(tmp_path: Path) -> None:
    assert not regen_guard.is_protected(tmp_path / "nope.md")
    assert regen_guard.detect_reason(tmp_path / "nope.md") is None


def test_html_comment_marks_protected(tmp_path: Path) -> None:
    target = tmp_path / "agent.md"
    target.write_text("---\nname: x\n---\n<!-- NO-REGEN: hand-edited -->\nbody\n")
    assert regen_guard.is_protected(target) is True
    assert regen_guard.detect_reason(target) == regen_guard.REASON_HTML_COMMENT


def test_hash_comment_at_line_start_marks_protected(tmp_path: Path) -> None:
    target = tmp_path / "script.py"
    target.write_text("#!/usr/bin/env python3\n# NO-REGEN: rewritten upstream\nprint('hi')\n")
    assert regen_guard.is_protected(target) is True
    assert regen_guard.detect_reason(target) == regen_guard.REASON_HASH_COMMENT


def test_indented_hash_comment_marks_protected(tmp_path: Path) -> None:
    target = tmp_path / "indented.py"
    target.write_text("def f():\n    # NO-REGEN tags inside a body still count\n    pass\n")
    assert regen_guard.is_protected(target) is True


def test_string_literal_no_regen_does_not_mark_protected(tmp_path: Path) -> None:
    """A bare string with NO-REGEN must not count; sentinel needs comment shape."""
    target = tmp_path / "literal.md"
    target.write_text('text = "NO-REGEN appears here as data not a marker"\n')
    assert regen_guard.is_protected(target) is False


def test_sidecar_marks_protected_even_when_target_clean(tmp_path: Path) -> None:
    target = tmp_path / "agent.agent.md"
    target.write_text("---\nname: x\n---\nbody\n")
    sidecar = tmp_path / "agent.agent.md.noregen"
    sidecar.write_text("custom content; do not regenerate\n")
    assert regen_guard.is_protected(target) is True
    assert regen_guard.detect_reason(target) == regen_guard.REASON_SIDECAR


def test_sidecar_preferred_over_in_file_marker(tmp_path: Path) -> None:
    """Sidecar wins because it is the most explicit escape hatch."""
    target = tmp_path / "agent.md"
    target.write_text("<!-- NO-REGEN -->\nbody\n")
    (tmp_path / "agent.md.noregen").write_text("")
    assert regen_guard.detect_reason(target) == regen_guard.REASON_SIDECAR


def test_marker_past_head_window_is_ignored(tmp_path: Path) -> None:
    """A marker buried past 4 KiB must be missed; encourages sidecar use."""
    target = tmp_path / "long.md"
    payload = "x" * 5000 + "\n# NO-REGEN past head\n"
    target.write_text(payload)
    assert regen_guard.is_protected(target) is False


def test_unreadable_file_falls_back_to_unprotected(tmp_path: Path) -> None:
    """Read errors do not block the build; sidecar is the safe escape hatch."""
    target = tmp_path / "ghost.md"
    # Simulate by passing a directory path of the same name (open will fail).
    target.mkdir()
    assert regen_guard.is_protected(target) is False


@pytest.mark.parametrize("comment", ["<!-- NO-REGEN -->", "# NO-REGEN-this-too"])
def test_multiple_comment_styles(tmp_path: Path, comment: str) -> None:
    target = tmp_path / "f.md"
    target.write_text(f"{comment}\nbody\n")
    assert regen_guard.is_protected(target) is True
