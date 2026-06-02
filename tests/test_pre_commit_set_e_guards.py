"""Regression tests for #2258: pre-commit substitutions must survive set -e.

`.githooks/pre-commit` runs under `set -e`. A standalone command substitution
`VAR=$(cmd)` whose `cmd` exits nonzero causes the hook to abort AT THAT LINE,
before the following `EXIT=$?` capture and before any remediation message can
print. The bug surfaced live: a scope-exploded commit died with no explanation.

The fix is the `VAR=$(cmd) && VAR_EXIT=0 || VAR_EXIT=$?` guard. These tests:

1. Prove the behavioral difference (unguarded dies, guarded captures the code).
2. Pin the fix so no future edit reintroduces the unguarded shape at the
   audited sites.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PRE_COMMIT = REPO_ROOT / ".githooks" / "pre-commit"


def _run_bash(script: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-c", script],
        capture_output=True,
        text=True,
        timeout=15,
    )


def test_unguarded_substitution_dies_under_set_e() -> None:
    """Baseline: the buggy shape aborts before the exit-code line runs."""
    script = (
        "set -e\n"
        "OUT=$(sh -c 'echo hello; exit 1')\n"  # dies here under set -e
        "EXIT=$?\n"
        'echo "REACHED EXIT=$EXIT"\n'
    )
    result = _run_bash(script)

    assert result.returncode != 0, "unguarded substitution unexpectedly survived"
    assert "REACHED" not in result.stdout, (
        "the line after the unguarded substitution ran; set -e did not abort "
        "(test environment differs from the hook's)"
    )


def test_guarded_substitution_captures_exit_under_set_e() -> None:
    """The fix shape captures both output and a nonzero exit without aborting."""
    script = (
        "set -e\n"
        "OUT=$(sh -c 'echo hello; exit 1') && EXIT=0 || EXIT=$?\n"
        'echo "REACHED EXIT=$EXIT OUT=$OUT"\n'
    )
    result = _run_bash(script)

    assert result.returncode == 0, "guarded substitution aborted unexpectedly"
    assert "REACHED EXIT=1 OUT=hello" in result.stdout, (
        f"guard did not capture exit/output correctly: {result.stdout!r}"
    )


def test_guarded_substitution_captures_zero_on_success() -> None:
    """On success the guard yields exit 0 and the captured output."""
    script = (
        "set -e\n"
        "OUT=$(sh -c 'echo ok; exit 0') && EXIT=0 || EXIT=$?\n"
        'echo "REACHED EXIT=$EXIT OUT=$OUT"\n'
    )
    result = _run_bash(script)

    assert result.returncode == 0
    assert "REACHED EXIT=0 OUT=ok" in result.stdout


# Variables whose `$(...)` substitution can legitimately exit nonzero and which
# must therefore use the set -e guard. Each pairs an output var with its exit var.
_AUDITED_SITES = (
    ("SCOPE_OUTPUT", "SCOPE_EXIT"),
    ("SYNC_OUTPUT", "SYNC_EXIT"),
    ("GENERATE_OUTPUT", "GENERATE_EXIT"),
    ("validator_output", "validator_exit"),
    ("adr_result", "adr_exit"),
    ("errors", "errors_exit"),
)


@pytest.mark.parametrize(("out_var", "exit_var"), _AUDITED_SITES)
def test_audited_site_uses_set_e_guard(out_var: str, exit_var: str) -> None:
    """Each audited substitution captures its exit on the same line via the guard.

    The vulnerable shape is `OUT=$(...)` on one line and `EXIT=$?` on the next.
    The fix puts `&& EXIT=0 || EXIT=$?` on the substitution line. Assert the
    fixed shape is present and the two-line vulnerable shape is absent.
    """
    text = PRE_COMMIT.read_text(encoding="utf-8")

    guarded = re.compile(
        rf"^\s*{re.escape(out_var)}=\$\(.*\)\s*&&\s*{re.escape(exit_var)}=0\s*\|\|\s*{re.escape(exit_var)}=\$\?\s*$",
        re.MULTILINE,
    )
    assert guarded.search(text), (
        f"{out_var}/{exit_var} is missing the `&& {exit_var}=0 || {exit_var}=$?` "
        "set -e guard (Issue #2258)"
    )

    vulnerable = re.compile(
        rf"^\s*{re.escape(out_var)}=\$\([^\n]*\)\s*\n\s*{re.escape(exit_var)}=\$\?\s*$",
        re.MULTILINE,
    )
    assert not vulnerable.search(text), (
        f"{out_var}/{exit_var} still uses the unguarded two-line shape that dies "
        "under set -e (Issue #2258)"
    )


def test_pre_commit_is_syntactically_valid() -> None:
    """The hook parses under bash -n (no syntax regression from the edits)."""
    result = subprocess.run(
        ["bash", "-n", str(PRE_COMMIT)],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, f"bash -n failed: {result.stderr}"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
