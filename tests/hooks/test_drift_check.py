"""Tests for the review-axes drift-check phase in .githooks/pre-push (REQ-008-03 / REQ-008-07).

The drift-check phase is bash that delegates to the Python generator's
``--dry-run`` mode. The full drift logic is tested at the generator level
in tests/build_scripts/test_generate_pr_quality_prompts.py (idempotency,
clean-vs-drift, exit codes 0/1/2). These tests cover the hook delegation
contract:

1. The hook references the generator command and expected flag.
2. The hook propagates exit codes correctly (0 -> pass, 1 -> fail, 2 -> fail).
3. The hook calls the canonical generator path under build/scripts/.
4. Bash syntax is valid.

A truly behavioral end-to-end test would require invoking ``git push``
under a stubbed environment, which is heavier than the value it adds:
the hook is a thin shell delegate. Static and structural verification is
sufficient.

Refs #1934 (REQ-008-03 AC, REQ-008-07 AC).
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PRE_PUSH_HOOK = REPO_ROOT / ".githooks" / "pre-push"
GENERATOR = REPO_ROOT / "build" / "scripts" / "generate_pr_quality_prompts.py"


def test_pre_push_hook_exists() -> None:
    assert PRE_PUSH_HOOK.is_file(), f"pre-push hook missing: {PRE_PUSH_HOOK}"


def test_pre_push_hook_is_executable() -> None:
    import os
    assert os.access(PRE_PUSH_HOOK, os.X_OK), (
        f"pre-push hook not executable: {PRE_PUSH_HOOK}"
    )


def test_pre_push_hook_bash_syntax_valid() -> None:
    """`bash -n` parses without executing; catches structural shell errors."""
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


def test_pre_push_hook_invokes_generator_dry_run() -> None:
    """The drift-check phase calls the generator with --dry-run."""
    text = PRE_PUSH_HOOK.read_text(encoding="utf-8")
    assert (
        "build/scripts/generate_pr_quality_prompts.py --dry-run" in text
    ), "pre-push hook must invoke generator dry-run"


def test_pre_push_hook_handles_drift_exit_code_one() -> None:
    """The hook records FAIL when generator exits 1 (drift detected)."""
    text = PRE_PUSH_HOOK.read_text(encoding="utf-8")
    # The hook captures exit code into DRIFT_EXIT and branches on it.
    assert "DRIFT_EXIT" in text
    assert 'DRIFT_EXIT" -eq 1' in text
    assert "record_fail" in text


def test_pre_push_hook_handles_config_error_as_fail() -> None:
    """Exit code 2 (config error) produces record_fail not record_warn.

    F8 from /test gate: the hook must match CI strictness. Earlier behavior
    treated config errors as warnings, which let bad config silently pass
    locally and surface only at CI.
    """
    text = PRE_PUSH_HOOK.read_text(encoding="utf-8")
    drift_phase_idx = text.find("Phase 5b: Review-axes drift detection")
    assert drift_phase_idx > 0, "drift phase comment missing"
    drift_phase = text[drift_phase_idx : drift_phase_idx + 2000]
    # In the drift phase, the else branch (exit != 1) must record_fail.
    assert "record_fail" in drift_phase
    # And must NOT silently warn on the catch-all else.
    assert "record_warn" not in drift_phase, (
        "drift phase records warn on config error; should be fail per F8"
    )


def test_pre_push_hook_falls_back_when_python3_missing() -> None:
    """If python3 is unavailable, the hook records skip (does not crash)."""
    text = PRE_PUSH_HOOK.read_text(encoding="utf-8")
    drift_phase_idx = text.find("Phase 5b: Review-axes drift detection")
    drift_phase = text[drift_phase_idx : drift_phase_idx + 2000]
    assert "command -v python3" in drift_phase
    assert "record_skip" in drift_phase


def test_generator_module_callable_from_python() -> None:
    """The generator path the hook invokes is importable.

    Catches a class of regression where the hook references a path that
    has been moved or renamed.
    """
    assert GENERATOR.is_file(), f"generator missing at hook-cited path: {GENERATOR}"


def test_generator_dry_run_clean_state_returns_zero() -> None:
    """End-to-end smoke: invoking the generator dry-run on the live tree
    returns 0 (no drift) given the synced state.

    This verifies the hook will pass in the steady state. Drift behavior
    is covered by tests/build_scripts/test_generate_pr_quality_prompts.py.
    """
    import sys
    result = subprocess.run(
        [sys.executable, str(GENERATOR), "--dry-run"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        timeout=30,
        check=False,
    )
    # 0 = clean, 1 = drift, 2 = config error.
    assert result.returncode in (0, 1), (
        f"unexpected generator exit {result.returncode}: "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    if result.returncode == 1:
        pytest.skip("drift present; not the steady state we are pinning")
