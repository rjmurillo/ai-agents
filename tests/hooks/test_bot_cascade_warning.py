"""Tests for the bot-cascade warning phase in .githooks/pre-push (REQ-009-10, M5).

Phase 5c is a thin bash delegate that calls
`.claude/skills/github/scripts/pr/get_unresolved_review_threads.py`
and warns when `unresolved_count > 0`. The full thread-query logic is
tested at the skill level. These tests cover the hook delegation contract:

1. The hook references the canonical script path and the `--pull-request` flag.
2. The hook warns (record_warn) on unresolved count; it never blocks (record_fail).
3. The hook skips silently when `gh` is unavailable, no PR exists, or the
   query fails.
4. Bash syntax is valid for the augmented hook.

A truly behavioral end-to-end test would require `git push` against a stubbed
GitHub. The hook is a thin shell delegate per ADR-006; static and structural
verification is sufficient. Behavioral tests on the underlying script live
under `tests/skills/github/`.

Refs #1988, REQ-009-10.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PRE_PUSH_HOOK = REPO_ROOT / ".githooks" / "pre-push"
UNRESOLVED_SCRIPT = (
    REPO_ROOT
    / ".claude"
    / "skills"
    / "github"
    / "scripts"
    / "pr"
    / "get_unresolved_review_threads.py"
)


def _hook_text() -> str:
    return PRE_PUSH_HOOK.read_text(encoding="utf-8")


def test_pre_push_hook_bash_syntax_valid() -> None:
    """`bash -n` parses without executing; catches Phase 5c structural errors."""
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
        f"pre-push hook has bash syntax error after M5 edit:\n{result.stderr}"
    )


def test_phase_5c_header_present() -> None:
    """Phase 5c section header lands in the hook for operator discoverability."""
    text = _hook_text()
    assert "Phase 5c: Bot-cascade warning" in text, (
        "M5 must add a `Phase 5c: Bot-cascade warning` echo_phase block"
    )


def test_phase_5c_invokes_canonical_script() -> None:
    """The hook calls the canonical get_unresolved_review_threads.py path."""
    text = _hook_text()
    assert (
        ".claude/skills/github/scripts/pr/get_unresolved_review_threads.py"
        in text
    ), "Phase 5c must invoke the canonical unresolved-threads script"
    assert "--pull-request" in text, (
        "Phase 5c must pass --pull-request as an argv flag (no shell concat)"
    )


def test_phase_5c_is_warn_only_never_blocks() -> None:
    """The bot-cascade block must use record_warn, never record_fail.

    The bot-cascade gap is a velocity issue, not a correctness issue. Blocking
    pushes here would surprise developers on a transient gh outage. The test
    inspects only the executable lines (ignoring shell `#` comments) to keep
    the constraint about call sites, not prose.
    """
    text = _hook_text()
    # Locate Phase 5c span by header to keep the assertion local.
    start = text.find("Phase 5c: Bot-cascade warning")
    assert start != -1, "Phase 5c header not found"
    # Phase 6 follows immediately; bound the slice.
    end = text.find("# Phase 6: Summary", start)
    if end == -1:
        end = len(text)
    phase_5c = text[start:end]
    assert "record_warn" in phase_5c, (
        "Phase 5c must surface the cascade risk via record_warn"
    )
    # Strip shell comments before searching for call sites. A directive
    # in a comment that says "never call record_fail" should not trip
    # this guard; a literal call to record_fail in executable code must.
    executable_lines = [
        line for line in phase_5c.splitlines() if not line.strip().startswith("#")
    ]
    executable = "\n".join(executable_lines)
    assert "record_fail" not in executable, (
        "Phase 5c must NOT call record_fail in executable code; it is warn-only"
    )


def test_phase_5c_handles_missing_gh_gracefully() -> None:
    """When `gh` is absent, the phase must record_skip, not error."""
    text = _hook_text()
    start = text.find("Phase 5c: Bot-cascade warning")
    end = text.find("# Phase 6: Summary", start)
    phase_5c = text[start:end if end != -1 else len(text)]
    assert "command -v gh" in phase_5c, (
        "Phase 5c must guard on gh availability"
    )
    assert "record_skip" in phase_5c, (
        "Phase 5c must record_skip when prerequisites are missing"
    )


def test_phase_5c_references_batch_fix_pattern() -> None:
    """The warning output must point operators to the canonical mitigation.

    Session 14 of pr-review-observations.md documents the batch-fix pattern.
    Without this reference, operators see the warning and push again without
    understanding the cascade dynamics.
    """
    text = _hook_text()
    start = text.find("Phase 5c: Bot-cascade warning")
    end = text.find("# Phase 6: Summary", start)
    phase_5c = text[start:end if end != -1 else len(text)]
    assert "Batch-fix pattern" in phase_5c or "batch-fix pattern" in phase_5c, (
        "Phase 5c output must reference the batch-fix pattern"
    )
    assert "Session 14" in phase_5c, (
        "Phase 5c must cite Session 14 of pr-review-observations.md"
    )


def test_canonical_script_exists() -> None:
    """Sanity: the script the hook delegates to must exist on disk."""
    assert UNRESOLVED_SCRIPT.is_file(), (
        f"canonical thread-query script missing: {UNRESOLVED_SCRIPT}"
    )
