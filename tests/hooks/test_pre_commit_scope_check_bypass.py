#!/usr/bin/env python3
"""Behavioral tests for the pre-commit ``SKIP_SCOPE_CHECK`` bypass observability.

Regression guard for #3142. The scope-explosion wrapper in ``.githooks/pre-commit``
supported ``SKIP_SCOPE_CHECK=1`` but the bypass was silent: the ``if [ ... != "1" ]``
guard had no ``else`` branch, so with the flag set the wrapper skipped
``scripts/detect_scope_explosion.py`` entirely and the detector's own bypass
message never printed. Per the config-catalog rule, every escape hatch must be
narrow, announced, and observable.

The Python detector already prints a bypass line and is covered by
``tests/test_detect_scope_explosion.py``. Those tests do NOT exercise the hook
wrapper, which bypasses before the detector runs. To close that gap without
duplicating the wrapper (which would drift from the hook), these tests extract
the exact ``SKIP_SCOPE_CHECK`` guard block from ``.githooks/pre-commit`` and run
it under bash with stubbed hook helpers against controlled flag values.
"""

import os
import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PRE_COMMIT = REPO_ROOT / ".githooks" / "pre-commit"

_GUARD_LINE = 'if [ "$SKIP_SCOPE_CHECK" != "1" ]; then'
_MARKER = "SCOPE_RAN"


def _hook_text() -> str:
    return PRE_COMMIT.read_text(encoding="utf-8")


def _extract_target_block() -> str:
    """Return the ``SKIP_SCOPE_CHECK`` guard block from the hook.

    Extracts from the ``if [ "$SKIP_SCOPE_CHECK" != "1" ]; then`` line through
    the matching outer ``fi`` (the only column-0 ``fi`` after the guard; every
    nested terminator is indented), inclusive.
    """
    lines = _hook_text().splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.strip() == _GUARD_LINE:
            start = i
            break
    assert start is not None, "SKIP_SCOPE_CHECK guard not found in hook"
    end = None
    for j in range(start + 1, len(lines)):
        if lines[j] == "fi":  # column-0 fi closes the outer guard
            end = j
            break
    assert end is not None, "outer guard terminator not found in hook"
    return "\n".join(lines[start : end + 1])


def _run_block(skip_value: str | None, cwd: Path) -> str:
    """Run the extracted guard block under bash and return combined output.

    ``skip_value`` is passed via the child environment (``None`` leaves
    ``SKIP_SCOPE_CHECK`` unset). The detector invocation is stubbed with a
    ``printf`` that emits ``SCOPE_RAN`` so the test can prove whether the
    wrapper reached the detector path. Hook helpers ``echo_warning`` and
    ``echo_error`` are stubbed to echo their arguments.
    """
    block = _extract_target_block()
    detect_stub = cwd / "detect_scope_explosion.py"
    detect_stub.write_text("# stub\n", encoding="utf-8")
    script = (
        # Match the hook's error mode (`.githooks/pre-commit` sets `set -e`).
        "set -e\n"
        "echo_warning() { echo \"WARN:$*\"; }\n"
        "echo_error() { echo \"ERR:$*\"; }\n"
        "set_python_cmd() { return 0; }\n"
        # Stub the detector so reaching it prints an observable marker instead
        # of running the real scope check.
        f"PYTHON_CMD=(printf '{_MARKER}\\n')\n"
        f'SCOPE_DETECT_SCRIPT="{detect_stub}"\n'
        "EXIT_STATUS=0\n"
        f"{block}\n"
    )
    bash = shutil.which("bash")
    assert bash is not None, "bash interpreter required for this test"
    env = {k: v for k, v in os.environ.items() if k != "SKIP_SCOPE_CHECK"}
    if skip_value is not None:
        env["SKIP_SCOPE_CHECK"] = skip_value
    result = subprocess.run(
        [bash, "-c", script],
        cwd=cwd,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=True,
        env=env,
    )
    return result.stdout


# --- Positive: the bypass is announced ------------------------------------


def test_bypass_prints_observable_warning(tmp_path: Path) -> None:
    out = _run_block("1", cwd=tmp_path)

    assert "Scope detection bypassed (SKIP_SCOPE_CHECK=1)" in out
    # Acceptance criterion 1: exactly one bypass line, and criterion 7: no other
    # scope work runs (the detector marker must be absent).
    assert out.count("Scope detection bypassed") == 1
    assert _MARKER not in out


# --- Negative: unset runs the detector, no bypass line --------------------


def test_unset_runs_detector_without_bypass_line(tmp_path: Path) -> None:
    out = _run_block(None, cwd=tmp_path)

    assert _MARKER in out
    assert "bypassed" not in out


# --- Edge: only the literal "1" bypasses ----------------------------------


def test_value_zero_does_not_bypass(tmp_path: Path) -> None:
    out = _run_block("0", cwd=tmp_path)

    assert _MARKER in out
    assert "bypassed" not in out


def test_value_two_does_not_bypass(tmp_path: Path) -> None:
    out = _run_block("2", cwd=tmp_path)

    assert _MARKER in out
    assert "bypassed" not in out


def test_truthy_word_does_not_bypass(tmp_path: Path) -> None:
    # "true" is not the documented literal "1"; the detector must still run.
    out = _run_block("true", cwd=tmp_path)

    assert _MARKER in out
    assert "bypassed" not in out


# --- Structural: the else branch exists in the hook -----------------------


def test_hook_has_observable_else_branch() -> None:
    block = _extract_target_block()

    assert "else" in block
    assert "SKIP_SCOPE_CHECK=1" in block
    assert "echo_warning" in block.split("else", 1)[1]
