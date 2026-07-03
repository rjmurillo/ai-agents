"""Regression tests for #2832: pre-commit must re-stage ruff auto-fixes
even when advisory findings remain.

Background
----------
`.githooks/pre-commit` runs ``ruff check --fix`` on staged Python files
(non-blocking, ADR-042). Pre-fix, the re-stage loop lived only in the
verify-success branch: when the post-fix ``ruff check`` still reported
findings (the pre-existing #2194 advisory backlog), the hook warned and
skipped re-staging. The commit then recorded the unfixed content while
the fix sat unstaged in the working tree, and the next push failed the
pre-push ``build_all --check`` staleness gate.

The fix hoists the re-stage loop into the autofix block so a mutated
file is always re-staged, regardless of the verify outcome.

These tests mirror the autofix block as a bash fragment (same pattern as
``test_pre_commit_taste_lint_summary.py``) and drive it in a throwaway
git repo with a stub ``ruff`` on PATH. A companion structural test pins
the ordering inside the real hook so the fragment and the hook cannot
drift apart silently.
"""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PRE_COMMIT = REPO_ROOT / ".githooks" / "pre-commit"

# Mirrors the autofix + verify block of `.githooks/pre-commit`. Kept
# behaviorally identical: fix, re-stage unconditionally, then verify.
AUTOFIX_FRAGMENT = r"""
set -e
echo_action()  { echo "ACTION: $1"; }
echo_success() { echo "SUCCESS: $1"; }
echo_warning() { echo "WARNING: $1"; }
echo_info()    { echo "$1"; }

AUTOFIX="${AUTOFIX:-1}"
FILES_FIXED=0
PY_FILES=("$TARGET_FILE")

if [ "$AUTOFIX" = "1" ]; then
    echo_action "Auto-fixing Python files with ruff..."
    ruff check --fix -- "${PY_FILES[@]}" 2>/dev/null || true

    for file in "${PY_FILES[@]}"; do
        if [ -f "$file" ] && ! git diff --quiet -- "$file" 2>/dev/null; then
            echo_success "Fixed: $file"
            git add -- "$file"
            FILES_FIXED=1
        fi
    done
fi

if ! ruff check -- "${PY_FILES[@]}" 2>/dev/null; then
    echo_warning "Python linting found issues (non-blocking)."
else
    echo_success "Python files OK."
fi
echo "FILES_FIXED=$FILES_FIXED"
exit 0
"""

FIXED_CONTENT = 'GREETING = "hello"\n'
UNFIXED_CONTENT = 'GREETING = f"hello"\n'


def _write_stub_ruff(stub_dir: Path, verify_exit: int) -> None:
    """Install a fake ``ruff`` whose ``check --fix`` rewrites the target
    file and whose plain ``check`` exits with ``verify_exit``."""
    stub = stub_dir / "ruff"
    stub.write_text(
        "#!/usr/bin/env bash\n"
        'if [ "$1" = "check" ] && [ "$2" = "--fix" ]; then\n'
        f"    printf '%s' '{FIXED_CONTENT.rstrip()}' > \"$4\"\n"
        "    exit 0\n"
        "fi\n"
        f"exit {verify_exit}\n"
    )
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


@pytest.fixture
def fixture_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", repo], check=True, timeout=15)
    subprocess.run(
        ["git", "-C", repo, "config", "user.email", "t@example.com"],
        check=True,
        timeout=15,
    )
    subprocess.run(
        ["git", "-C", repo, "config", "user.name", "Test"], check=True, timeout=15
    )
    target = repo / "sample.py"
    target.write_text(UNFIXED_CONTENT)
    subprocess.run(["git", "-C", repo, "add", "sample.py"], check=True, timeout=15)
    return repo


def _run_fragment(repo: Path, stub_dir: Path, autofix: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PATH"] = f"{stub_dir}{os.pathsep}{env['PATH']}"
    env["AUTOFIX"] = autofix
    env["TARGET_FILE"] = "sample.py"
    return subprocess.run(
        ["bash", "-c", AUTOFIX_FRAGMENT],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def _staged_content(repo: Path) -> str:
    return subprocess.run(
        ["git", "-C", repo, "show", ":sample.py"],
        capture_output=True,
        text=True,
        timeout=15,
        check=True,
    ).stdout


def test_restages_fix_when_advisory_findings_remain(
    fixture_repo: Path, tmp_path: Path
) -> None:
    """The #2832 case: verify stays red, the fix must still be staged."""
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir()
    _write_stub_ruff(stub_dir, verify_exit=1)

    result = _run_fragment(fixture_repo, stub_dir, autofix="1")

    assert result.returncode == 0
    assert "Fixed: sample.py" in result.stdout
    assert "FILES_FIXED=1" in result.stdout
    assert "found issues (non-blocking)" in result.stdout
    assert _staged_content(fixture_repo) == FIXED_CONTENT.rstrip()
    diff = subprocess.run(
        ["git", "-C", fixture_repo, "diff", "--quiet", "--", "sample.py"],
        timeout=15,
        check=False,
    )
    assert diff.returncode == 0, "working tree must match the index after re-stage"


def test_restages_fix_when_verify_passes(fixture_repo: Path, tmp_path: Path) -> None:
    """Existing behavior preserved: clean verify still re-stages the fix."""
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir()
    _write_stub_ruff(stub_dir, verify_exit=0)

    result = _run_fragment(fixture_repo, stub_dir, autofix="1")

    assert result.returncode == 0
    assert "FILES_FIXED=1" in result.stdout
    assert "Python files OK." in result.stdout
    assert _staged_content(fixture_repo) == FIXED_CONTENT.rstrip()


def test_no_mutation_when_autofix_disabled(fixture_repo: Path, tmp_path: Path) -> None:
    """AUTOFIX=0 must neither fix nor re-stage anything."""
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir()
    _write_stub_ruff(stub_dir, verify_exit=1)

    result = _run_fragment(fixture_repo, stub_dir, autofix="0")

    assert result.returncode == 0
    assert "FILES_FIXED=0" in result.stdout
    assert _staged_content(fixture_repo) == UNFIXED_CONTENT


def test_hook_restages_inside_autofix_block() -> None:
    """Structural pin on the real hook: the re-stage loop sits inside the
    autofix block, before the verify check, so the fragment above cannot
    drift from the hook without this test failing."""
    hook = PRE_COMMIT.read_text()
    autofix_idx = hook.index("Auto-fixing Python files with ruff...")
    restage_idx = hook.index('git add -- "$file"', autofix_idx)
    verify_idx = hook.index("Python linting found issues (non-blocking).", autofix_idx)
    assert autofix_idx < restage_idx < verify_idx, (
        "re-stage loop must run inside the autofix block before the verify "
        "step; see issue #2832"
    )
