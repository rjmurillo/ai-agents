"""Tests for the bot-cascade warning Phase 5c in .githooks/pre-push (REQ-011).

Pattern: structural verification of the bash hook (string-presence and
syntax). Same pattern as test_drift_check.py for Phase 5b. Bash hooks are
thin delegates; static verification is sufficient.

Acceptance criteria pinned:

- REQ-011-01: unresolved threads emit warn (not block).
- REQ-011-02: incomplete pagination emits skip, not pass.
- REQ-011-03: recent bot review under 120s emits warn.
- REQ-011-04: gh api auth failures emit skip, not swallow as pass.

Refs:
- REQ-011 (acceptance criteria)
- DESIGN-011 (architecture, test strategy)
- PR #1989 retrospective (highest-leverage bot-cascade intervention)
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PRE_PUSH_HOOK = REPO_ROOT / ".githooks" / "pre-push"


def _hook_text() -> str:
    return PRE_PUSH_HOOK.read_text(encoding="utf-8")


def _phase_5c_block() -> str:
    """Return only the Phase 5c block of the hook for scoped grep.

    Phase 5c starts at the header comment and ends at the next phase header
    or end of file. This scopes assertions so we do not accidentally match
    other phases.
    """
    text = _hook_text()
    # Match from "Phase 5c" header to next phase or end of file.
    pattern = re.compile(
        r"# Phase 5c.*?(?=# Phase \d|\Z)",
        re.DOTALL,
    )
    match = pattern.search(text)
    return match.group(0) if match else ""


def test_phase_5c_header_present() -> None:
    """REQ-011-01: Phase 5c block exists after Phase 5b."""
    text = _hook_text()
    assert "Phase 5c" in text, (
        "REQ-011-01: pre-push hook must include a Phase 5c block"
    )
    # Phase 5c must come after Phase 5b (drift check) per DESIGN-011.
    phase_5b_pos = text.find("Phase 5b")
    phase_5c_pos = text.find("Phase 5c")
    assert phase_5b_pos < phase_5c_pos, "Phase 5c must follow Phase 5b"


def test_phase_5c_calls_unresolved_threads_script() -> None:
    """REQ-011-01: hook queries unresolved threads via canonical script."""
    block = _phase_5c_block()
    assert "get_unresolved_review_threads.py" in block, (
        "REQ-011-01: hook must invoke get_unresolved_review_threads.py"
    )


def test_phase_5c_parses_fetched_pages_complete() -> None:
    """REQ-011-02: hook parses fetched_pages_complete BEFORE trusting count."""
    block = _phase_5c_block()
    assert "fetched_pages_complete" in block, (
        "REQ-011-02: hook must check fetched_pages_complete; "
        "incomplete pagination cannot be trusted"
    )


def test_phase_5c_emits_warn_on_unresolved() -> None:
    """REQ-011-01: hook emits record_warn (not record_fail) on unresolved."""
    block = _phase_5c_block()
    assert "record_warn" in block, "REQ-011-01: hook must emit record_warn"
    assert "unresolved" in block.lower(), (
        "REQ-011-01: warn message must reference unresolved threads"
    )


def test_phase_5c_emits_skip_on_incomplete() -> None:
    """REQ-011-02: hook emits record_skip when fetched_pages_complete=false."""
    block = _phase_5c_block()
    assert "record_skip" in block, (
        "REQ-011-02: hook must emit record_skip on incomplete pagination, "
        "not fall through to pass"
    )


def test_phase_5c_queries_reviews_endpoint() -> None:
    """REQ-011-03: hook queries gh api ... /reviews for bot timestamp."""
    block = _phase_5c_block()
    assert "/reviews" in block, (
        "REQ-011-03: hook must query the reviews endpoint to find bot timestamps"
    )


def test_phase_5c_filters_bot_reviews() -> None:
    """REQ-011-03: hook filters for Bot users when computing review age."""
    block = _phase_5c_block()
    assert "Bot" in block, (
        "REQ-011-03: hook must filter user.type == Bot when reading reviews"
    )


def test_phase_5c_120_second_threshold() -> None:
    """REQ-011-03: hook uses 120-second threshold for recent bot reviews."""
    block = _phase_5c_block()
    assert "120" in block, (
        "REQ-011-03: hook must reference the 120-second threshold from DESIGN-011"
    )


def test_phase_5c_no_fail_open_on_reviews() -> None:
    """REQ-011-04: hook does NOT use `|| true` fail-open on reviews query.

    PR #1989's M5 had this exact bug. The reviews call must propagate exit
    codes; auth/network failures produce SKIP, never PASS.
    """
    block = _phase_5c_block()
    # The reviews call must NOT be followed by `|| true` (fail-open pattern).
    # Look for the specific dangerous pattern.
    review_lines = [
        line for line in block.splitlines()
        if "reviews" in line and "gh api" in line
    ]
    for line in review_lines:
        assert "|| true" not in line, (
            f"REQ-011-04: `|| true` on reviews query swallows auth failures; "
            f"line: {line.strip()}"
        )


def test_phase_5c_warn_only_never_fails() -> None:
    """REQ-011-01..04: Phase 5c is warn-only; never calls record_fail."""
    block = _phase_5c_block()
    assert "record_fail" not in block, (
        "Phase 5c is warn-only; record_fail must NOT appear in the block"
    )


def test_pre_push_hook_bash_syntax_valid() -> None:
    """Hook must parse without syntax errors after Phase 5c additions."""
    if shutil.which("bash") is None:
        pytest.skip("bash not available on this platform")
    result = subprocess.run(
        ["bash", "-n", str(PRE_PUSH_HOOK)],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, (
        f"pre-push hook has bash syntax error:\n{result.stderr}"
    )
