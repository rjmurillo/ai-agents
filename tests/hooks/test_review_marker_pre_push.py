"""Tests for the review-marker guard in ``.githooks/pre-push``."""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PRE_PUSH_HOOK = REPO_ROOT / ".githooks" / "pre-push"


def test_pre_push_has_review_marker_phase() -> None:
    """The hook validates marker-bearing pushes before /ship."""
    text = PRE_PUSH_HOOK.read_text(encoding="utf-8")
    assert "Review marker freshness (Issue #1938 / AC6)" in text
    assert ".claude/skills/review/scripts/validate_review_marker.py" in text
    assert "Review marker validation failed" in text


def test_pre_push_only_skips_when_pushed_ref_has_no_review_marker() -> None:
    """The hook does not silently pass a stale marker-bearing pushed ref."""
    text = PRE_PUSH_HOOK.read_text(encoding="utf-8")
    assert "grep -q '^/review@'" in text
    assert "/ship enforces presence" in text
    assert "record_fail \"Review marker validation failed" in text
    no_marker_index = text.index("if ! printf")
    continue_index = text.index("continue", no_marker_index)
    validator_index = text.index("Review marker validator is a symlink")
    assert continue_index < validator_index


def test_pre_push_validates_pushed_sha_with_repo_root() -> None:
    """Vendored validator copy checks this repo, not the script directory."""
    text = PRE_PUSH_HOOK.read_text(encoding="utf-8")
    assert 'for pushed_sha in "${PVB_HEADS[@]}"' in text
    assert '--ref "$pushed_sha"' in text
    assert '--repo-root "$REPO_ROOT"' in text


def test_pre_push_hook_bash_syntax() -> None:
    """The edited hook remains valid bash."""
    result = subprocess.run(
        ["bash", "-n", str(PRE_PUSH_HOOK)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
