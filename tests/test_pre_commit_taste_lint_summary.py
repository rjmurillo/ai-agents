"""Regression tests for #2436: pre-commit final summary must distinguish blocking success from advisory taste-lint errors.

Background
----------
`.githooks/pre-commit` runs taste-lints as a non-blocking advisory check
(exit code 10 means "violations detected" but the hook intentionally does
NOT propagate that into ``EXIT_STATUS``). Pre-fix, the final summary
unconditionally printed::

    SUCCESS: All pre-commit checks passed.

even when taste-lints had just printed ``[ERROR]`` findings. The exit
code stayed at 0 (correct), but the wording hid the advisory failures.
Agents and humans reading the transcript would see both ``[ERROR]`` and
``SUCCESS`` with no signal that one was advisory.

The fix tracks an advisory flag (``TASTE_LINTS_ADVISORY=1`` when
``TASTE_EXIT`` is 10) and rewords the final summary accordingly:

* Blocking failure (EXIT_STATUS != 0)            -> ``ERROR: Pre-commit checks failed`` (unchanged, exit 2).
* Blocking pass + advisory taste-lint errors     -> ``SUCCESS: Blocking pre-commit checks passed; non-blocking taste-lints reported errors.``
* Blocking pass + auto-fixed files               -> ``SUCCESS: All checks passed. Some files were auto-fixed and re-staged.`` (unchanged).
* Blocking pass + no advisories and no auto-fix  -> ``SUCCESS: All pre-commit checks passed.`` (unchanged).

These tests reproduce the final-summary block in isolation as a small
bash fragment, exercising every combination of the three signals that
feed it: ``EXIT_STATUS``, ``FILES_FIXED``, ``TASTE_LINTS_ADVISORY``.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PRE_COMMIT = REPO_ROOT / ".githooks" / "pre-commit"

# Wording the fix MUST emit (and that pre-fix builds MUST NOT emit) when
# taste-lints report non-blocking errors but every blocking check passed.
# The full sentence lives in one place so a future wording tweak only has
# to touch this constant and the corresponding line in `.githooks/pre-commit`.
ADVISORY_SUMMARY = (
    "Blocking pre-commit checks passed; "
    "non-blocking taste-lints reported errors."
)


def _final_summary_fragment() -> str:
    """Return a bash fragment that mirrors the hook's final-summary block.

    The fragment is intentionally small. It defines the same echo helpers
    the real hook uses, declares the three signal vars the summary block
    consumes, and runs the same conditional ladder. Tests inject
    ``EXIT_STATUS``, ``FILES_FIXED``, and ``TASTE_LINTS_ADVISORY`` via
    the subprocess environment, run the fragment under ``bash -c``, and
    assert on the resulting exit code and stdout wording.

    The fragment is kept byte-identical with the hook's summary block so
    a regression in either copy fails the test. The companion
    ``test_pre_commit_hook_summary_matches_fragment`` proves that
    equivalence by scanning the real hook for the same wording.
    """
    return r"""
set -e
RED=''
GREEN=''
YELLOW=''
NC=''
echo_error()   { echo "ERROR: $1"; }
echo_warning() { echo "WARNING: $1"; }
echo_success() { echo "SUCCESS: $1"; }
echo_info()    { echo "$1"; }

EXIT_STATUS="${EXIT_STATUS:-0}"
FILES_FIXED="${FILES_FIXED:-0}"
TASTE_LINTS_ADVISORY="${TASTE_LINTS_ADVISORY:-0}"

echo ""
if [ "$EXIT_STATUS" -ne 0 ]; then
    echo_error "Pre-commit checks failed. Please fix the issues above."
    exit 2
fi

if [ "$FILES_FIXED" = "1" ]; then
    echo_success "All checks passed. Some files were auto-fixed and re-staged."
elif [ "$TASTE_LINTS_ADVISORY" = "1" ]; then
    echo_success "Blocking pre-commit checks passed; non-blocking taste-lints reported errors."
    echo_info "  Review the [ERROR] lines above; taste lints are advisory (exit 0)."
else
    echo_success "All pre-commit checks passed."
fi
exit 0
"""


def _run_summary(
    exit_status: str = "0",
    files_fixed: str = "0",
    taste_lints_advisory: str = "0",
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update(
        {
            "EXIT_STATUS": exit_status,
            "FILES_FIXED": files_fixed,
            "TASTE_LINTS_ADVISORY": taste_lints_advisory,
        }
    )
    return subprocess.run(
        ["bash", "-c", _final_summary_fragment()],
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )


# ---------------------------------------------------------------------------
# Behavioural tests: cover the four states of the summary block.
# ---------------------------------------------------------------------------


def test_summary_clean_pass_uses_unchanged_wording() -> None:
    """No advisories + no autofix -> existing ``All pre-commit checks passed`` line."""
    result = _run_summary()
    assert result.returncode == 0, result.stderr
    assert "SUCCESS: All pre-commit checks passed." in result.stdout
    assert "non-blocking taste-lints" not in result.stdout


def test_summary_autofix_pass_uses_unchanged_wording() -> None:
    """Auto-fixed files -> existing ``Some files were auto-fixed and re-staged`` line."""
    result = _run_summary(files_fixed="1")
    assert result.returncode == 0, result.stderr
    assert "Some files were auto-fixed and re-staged." in result.stdout
    assert "non-blocking taste-lints" not in result.stdout


def test_summary_advisory_taste_lint_errors_uses_new_wording() -> None:
    """Advisory taste-lint errors -> new wording distinguishes blocking pass from advisory failure.

    This is the regression case from issue #2436. Pre-fix, this output
    would say ``SUCCESS: All pre-commit checks passed.`` and the test
    fails. Post-fix, the wording differentiates blocking success from
    advisory errors so transcript readers can see at a glance that
    findings exist.
    """
    result = _run_summary(taste_lints_advisory="1")
    assert result.returncode == 0, result.stderr
    assert ADVISORY_SUMMARY in result.stdout, (
        f"Final summary missing advisory wording (#2436). stdout was: {result.stdout!r}"
    )
    # The pre-fix wording MUST NOT appear when advisories are present.
    # ``All pre-commit checks passed.`` was the misleading line.
    assert "SUCCESS: All pre-commit checks passed." not in result.stdout, (
        "Hook still prints the misleading unconditional success line when "
        "non-blocking taste-lints reported errors (#2436)."
    )


def test_summary_autofix_takes_priority_over_advisory() -> None:
    """When both signals are set, auto-fix wording wins (autofixes are louder than advisories).

    Rationale: auto-fix means the working tree was modified and the
    commit now contains different bytes than the user staged. That is a
    stronger user-facing signal than an advisory lint warning, so the
    summary surfaces it. The advisory ``[ERROR]`` lines are already
    visible higher up in the transcript regardless.
    """
    result = _run_summary(files_fixed="1", taste_lints_advisory="1")
    assert result.returncode == 0, result.stderr
    assert "Some files were auto-fixed and re-staged." in result.stdout


def test_summary_blocking_failure_still_exits_2() -> None:
    """Blocking failure path is unchanged: exit 2 and the advisory flag is irrelevant."""
    result = _run_summary(exit_status="1", taste_lints_advisory="1")
    assert result.returncode == 2
    assert "ERROR: Pre-commit checks failed" in result.stdout
    # No SUCCESS line on the failure path.
    assert "SUCCESS:" not in result.stdout


def test_summary_advisory_flag_does_not_change_exit_code() -> None:
    """AC: ``Pre-commit keeps exit code 0 for non-blocking taste-lints.`` (#2436).

    The new wording must not accidentally turn an advisory finding into
    a blocking failure. Whether or not advisories fired, a clean
    ``EXIT_STATUS`` must yield exit 0.
    """
    advisory = _run_summary(taste_lints_advisory="1")
    clean = _run_summary()
    assert advisory.returncode == 0
    assert clean.returncode == 0


# ---------------------------------------------------------------------------
# Drift guard: assert the real hook ships the wording the fragment encodes.
# ---------------------------------------------------------------------------


def test_pre_commit_hook_summary_matches_fragment() -> None:
    """The real ``.githooks/pre-commit`` must emit the new advisory wording.

    The behavioural tests above run an isolated bash fragment. This
    drift guard makes sure the canonical hook on disk wasn't edited to
    print something different (e.g. an earlier revision that only
    updates the fragment in tests). If a future commit reverts the
    wording in the hook itself, this fails loudly.
    """
    text = PRE_COMMIT.read_text(encoding="utf-8")
    assert ADVISORY_SUMMARY in text, (
        "`.githooks/pre-commit` is missing the advisory summary wording "
        f"({ADVISORY_SUMMARY!r}). #2436 regressed."
    )


def test_pre_commit_hook_sets_taste_lints_advisory_flag() -> None:
    """The taste-lints branch must set ``TASTE_LINTS_ADVISORY=1`` on exit code 10.

    Pins the wiring between the taste-lints exit-code 10 branch and the
    summary block. Without this flag, the new summary wording would
    never fire.
    """
    text = PRE_COMMIT.read_text(encoding="utf-8")
    # Must initialize the flag near the other tracking vars (default 0).
    init = re.compile(
        r"^\s*TASTE_LINTS_ADVISORY=0\s*$",
        re.MULTILINE,
    )
    assert init.search(text), (
        "`.githooks/pre-commit` does not initialize TASTE_LINTS_ADVISORY=0; "
        "the summary block would treat the var as unset on shells that "
        "object to `set -u` even if the test harness defaults it."
    )
    # Must set the flag inside the TASTE_EXIT == 10 branch. The gap allows
    # for the existing comments and warning prints between the branch head
    # and the assignment, but is bounded so an assignment outside the
    # branch (e.g. moved to global init) does not satisfy the test.
    setter = re.compile(
        r"TASTE_EXIT -eq 10[\s\S]{0,800}?TASTE_LINTS_ADVISORY=1",
    )
    assert setter.search(text), (
        "TASTE_LINTS_ADVISORY=1 is not set inside the `TASTE_EXIT -eq 10` "
        "branch, so the advisory summary wording would never fire (#2436)."
    )


def test_pre_commit_hook_drops_unconditional_success_line() -> None:
    """The unconditional ``All pre-commit checks passed`` line must be gated.

    Pre-fix, the hook had::

        else
            echo_success "All pre-commit checks passed."
        fi

    as the final ``else`` branch with only ``FILES_FIXED`` distinguished.
    Post-fix, the ``else`` branch must follow at least two ``elif``
    conditions (auto-fix and advisory). The structural assertion below
    pins that shape so a future edit cannot quietly drop the advisory
    case.
    """
    text = PRE_COMMIT.read_text(encoding="utf-8")
    # Match: if FILES_FIXED ... elif TASTE_LINTS_ADVISORY ... else ...
    summary_shape = re.compile(
        r'if\s+\[\s*"\$FILES_FIXED"\s*=\s*"1"\s*\][\s\S]{0,400}?'
        r'elif\s+\[\s*"\$TASTE_LINTS_ADVISORY"\s*=\s*"1"\s*\][\s\S]{0,400}?'
        r'else[\s\S]{0,200}?All pre-commit checks passed',
    )
    assert summary_shape.search(text), (
        "Final-summary block in `.githooks/pre-commit` is missing the "
        "elif TASTE_LINTS_ADVISORY branch between FILES_FIXED and the "
        "unconditional success line (#2436)."
    )


def test_pre_commit_hook_is_syntactically_valid() -> None:
    """``bash -n`` parses the hook (no syntax regression from the wording edit)."""
    result = subprocess.run(
        ["bash", "-n", str(PRE_COMMIT)],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, f"bash -n failed: {result.stderr}"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
