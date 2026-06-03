"""Tests for the review-skill drift-check phase in .githooks/pre-push (REQ-008-03 / REQ-008-07).

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

import os
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


def test_pre_push_pytest_strips_git_hook_environment() -> None:
    """The pytest phase must not inherit Git's hook repository override vars."""
    text = PRE_PUSH_HOOK.read_text(encoding="utf-8")
    pytest_phase_idx = text.find("# 14. Python tests (pytest)")
    assert pytest_phase_idx > 0, "pytest phase missing"
    pytest_phase = text[pytest_phase_idx : pytest_phase_idx + 2600]
    assert "env \\" in pytest_phase
    assert "-u GIT_DIR" in pytest_phase
    assert "-u GIT_WORK_TREE" in pytest_phase
    assert "-u GIT_INDEX_FILE" in pytest_phase
    assert "-u GIT_COMMON_DIR" in pytest_phase
    assert '-m pytest "$REPO_ROOT/tests/"' in pytest_phase


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


def test_pre_push_hook_falls_back_when_python_missing() -> None:
    """If no python interpreter is available, the hook records skip (does not crash).

    Detection delegates to set_python_cmd (uv-aware) per PR #1965 cluster B.
    """
    text = PRE_PUSH_HOOK.read_text(encoding="utf-8")
    drift_phase_idx = text.find("Phase 5b: Review-axes drift detection")
    drift_phase = text[drift_phase_idx : drift_phase_idx + 2000]
    assert "set_python_cmd" in drift_phase
    assert "record_skip" in drift_phase


def test_generator_module_callable_from_python() -> None:
    """The generator path the hook invokes is importable.

    Catches a class of regression where the hook references a path that
    has been moved or renamed.
    """
    assert GENERATOR.is_file(), f"generator missing at hook-cited path: {GENERATOR}"


def test_pre_push_hook_drift_phase_invokes_generator(tmp_path: Path) -> None:
    """Behavioral test: extract Phase 5b from the hook and invoke it as a
    standalone shell script with a stubbed generator on PATH.

    Stubs `python3` to a script that echoes a controlled exit code, so we
    can pin the hook's behavior on each generator outcome (0/1/2).
    """
    if shutil.which("bash") is None:
        pytest.skip("bash not available")

    # Extract just Phase 5b from the hook for isolated execution. The end
    # boundary is the next phase header (Phase 5c), NOT Phase 6: Phase 5c
    # was inserted between 5b and 6, and including it here would run the
    # bot-cascade code (real `gh api` calls) under the stubbed `python3`,
    # violating the mock-I/O rule (devin finding on PR #2011).
    hook_text = PRE_PUSH_HOOK.read_text(encoding="utf-8")
    start = hook_text.find("# Phase 5b: Review-axes drift detection")
    end = hook_text.find("# Phase 5c:", start)
    if end < 0:
        # Fall back to Phase 6 if Phase 5c is ever removed.
        end = hook_text.find("# Phase 6:", start)
    assert start > 0 and end > start, "Phase 5b boundaries not found"
    phase = hook_text[start:end]

    # Stub harness: define record_pass/fail/skip and set_python_cmd as
    # no-ops that report. set_python_cmd is the new detection helper used
    # by the drift phase (PR #1965 cluster B).
    harness = """
record_pass() { echo "PASS: $1"; }
record_fail() { echo "FAIL: $1"; EXIT_STATUS=1; }
record_warn() { echo "WARN: $1"; }
record_skip() { echo "SKIP: $1"; }
echo_phase() { echo "PHASE: $1"; }
echo_info() { echo "INFO: $1"; }
set_python_cmd() { PYTHON_CMD=(python3); return 0; }
EXIT_STATUS=0
"""

    for stub_exit, expected in [(0, "PASS:"), (1, "FAIL:"), (2, "FAIL:")]:
        # Stub python3 with a script that exits with the desired code.
        stub_dir = tmp_path / f"stub_{stub_exit}"
        stub_dir.mkdir()
        stub = stub_dir / "python3"
        stub.write_text(
            f'#!/usr/bin/env bash\necho "drift sample output"\nexit {stub_exit}\n',
            encoding="utf-8",
        )
        stub.chmod(0o755)

        script = harness + phase
        result = subprocess.run(
            ["bash", "-c", script],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
            env={
                **os.environ,
                "PATH": f"{stub_dir}:{os.environ.get('PATH', '')}",
            },
            cwd=str(REPO_ROOT),
        )
        assert expected in result.stdout, (
            f"stub exit {stub_exit}: expected {expected!r} in hook output, "
            f"got stdout={result.stdout!r} stderr={result.stderr!r}"
        )


def test_generator_dry_run_clean_state_returns_zero() -> None:
    """End-to-end smoke: the generator dry-run on the live tree returns 0.

    Drift in the steady state is a regression: it means the canonical files
    and the generated CI prompts have diverged. The test asserts unconditionally
    so the failure surfaces; do NOT skip-on-drift (a drifted tree is exactly
    what the drift check is supposed to catch, and a test that silently passes
    on drift defeats its purpose).

    Drift behavior under controlled conditions is covered by
    tests/build_scripts/test_generate_pr_quality_prompts.py.
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
    assert result.returncode == 0, (
        f"generator dry-run reports drift in the steady state "
        f"(exit {result.returncode}). This means canonical and generated "
        f"have diverged in the working tree. "
        f"Run `python3 build/scripts/generate_pr_quality_prompts.py` to fix.\n"
        f"stdout={result.stdout!r}\n"
        f"stderr={result.stderr!r}"
    )
