"""Mutation harness for the debate-log canonical path fix (Issue #4250).

Isolation model (Issues #4346, #4457)
--------------------------------------
Every mutation runs inside a detached git worktree created from HEAD. The
active worktree's tracked files are NEVER written. If the test process is
killed at any point, the active worktree stays clean and `git status --short`
remains empty. A durable marker blocks pre-push after SIGKILL until the stale
scratch worktree is recovered.

Three mutants and one inverted control:

  M1 (positive): revert the directory name "critique" back to "analysis".
      Expected: DEAD (tests detect the regression).

  M2 (positive): change the error message path from .agents/critique to
      .agents/wrong-dir.
      Expected: DEAD (tests detect the wrong message).

  M3 (positive): comment out the missing-debate-log early return so a missing
      log no longer fails.
      Expected: DEAD (tests detect missing gate).

  IC (inverted control): no-op mutation that changes a comment but not logic.
      Expected: SURVIVED (rc == 0). Proves the harness can tell green from red.

All test nodes assert:
  - returncode != 4 (no "file or directory not found" from pytest)
  - "no tests ran" not in stdout (suite collected at least one test)

Counting occurs before each mutation; DID-NOT-APPLY is raised if the literal
is absent (count == 0).
"""

from __future__ import annotations

import ast
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from scripts.testing.mutation_workspace import isolated_mutation_worktree

REPO_ROOT = Path(__file__).resolve().parents[2]
_TARGET_REL = Path("scripts") / "validation" / "git_hook_policy.py"
# Test paths are relative so the subprocess can resolve them from its own cwd.
_TESTS = [
    "tests/test_lefthook_integration.py",
    "tests/validation/test_session_log_optional.py",
]

_OUTCOME_DEAD = "DEAD"
_OUTCOME_SURVIVED = "SURVIVED"
_OUTCOME_DID_NOT_APPLY = "DID-NOT-APPLY"

# Timeout budget (Issue #5102)
# ---------------------------
# Two caps bound every mutation test, and their ORDER is the contract:
#
#   inner: subprocess.run(timeout=_INNER_SUBPROCESS_TIMEOUT_SECONDS) in
#          _run_tests_in, bounding the nested pytest process.
#   outer: @pytest.mark.timeout(_OUTER_TEST_TIMEOUT_SECONDS) on each test that
#          calls _run_tests_in, overriding the repo-wide --timeout=120 set in
#          pyproject.toml addopts.
#
# The outer cap MUST exceed the inner one. When the outer fires first,
# pytest-timeout interrupts inside subprocess.communicate and the failure names
# no command, which is the exact signature reported in Issue #5102:
#   "Failed: Timeout (>120.0s) from pytest-timeout", raised inside
#   subprocess.communicate, on a diff that never touched the mutated file.
# With the inner cap binding instead, the failure is a subprocess.TimeoutExpired
# naming the pytest command, and _apply_positive_mutant's finally block restores
# the target bytes.
#
# Sizing follows .claude/rules/ci-scripts.md MUST 16: size on a loaded machine,
# never an idle one. Worst measured single inner run on a contributor machine
# was 80.69s wall (Issue #5102) for tests/test_lefthook_integration.py alone.
# _TESTS has since grown tests/validation/test_session_log_optional.py, taking
# the collected count from 859 to 943 (+9.8%), so that same machine now needs
# roughly 89s. 120s left under 35s of headroom, which load average 7.63 erased.
_INNER_SUBPROCESS_TIMEOUT_SECONDS = 300
_OUTER_TEST_TIMEOUT_SECONDS = 360


def _run_tests_in(wt_path: Path) -> subprocess.CompletedProcess[str]:
    """Run the lefthook integration test suite from a scratch worktree."""
    pycache = wt_path / "scripts" / "validation" / "__pycache__"
    if pycache.exists():
        import shutil

        shutil.rmtree(pycache)

    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "--tb=short",
        "-q",
        "--import-mode=importlib",
        *_TESTS,
    ]
    return subprocess.run(
        cmd,
        cwd=str(wt_path),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={
            **__import__("os").environ,
            "PYTHONDONTWRITEBYTECODE": "1",
        },
        timeout=_INNER_SUBPROCESS_TIMEOUT_SECONDS,
    )


def _assert_suite_ran(result: subprocess.CompletedProcess[str], label: str) -> None:
    assert result.returncode != 4, (
        f"{label}: pytest exited 4 (file or directory not found). "
        "Suite was never collected.\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "no tests ran" not in result.stdout.lower(), (
        f"{label}: no tests were collected.\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def _apply_positive_mutant(
    wt_path: Path,
    original: bytes,
    original_fragment: bytes,
    mutant_fragment: bytes,
    label: str,
) -> str:
    """Apply mutant in scratch worktree and assert suite detects it (DEAD)."""
    count = original.count(original_fragment)
    if count == 0:
        raise AssertionError(
            f"{_OUTCOME_DID_NOT_APPLY} ({label}): literal not found in target. "
            "The file was changed; update this harness."
        )
    if count > 1:
        raise AssertionError(f"PATTERN-AMBIGUOUS ({label}): expected 1 occurrence, found {count}.")

    mutated = original.replace(original_fragment, mutant_fragment, 1)
    assert mutated != original, f"Mutation {label} produced a byte-identical file"

    wt_target = wt_path / _TARGET_REL
    wt_target.write_bytes(mutated)

    try:
        result = _run_tests_in(wt_path)
    finally:
        wt_target.write_bytes(original)
        assert wt_target.read_bytes() == original, (
            f"{label}: scratch worktree target was not restored to original bytes"
        )

    _assert_suite_ran(result, label)

    assert result.returncode != 0, (
        f"MUTANT SURVIVED ({label}): suite passed after mutation. "
        "Tests do not detect the regression.\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    return _OUTCOME_DEAD


def test_run_tests_uses_a_bounded_timeout(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    recorded: dict[str, object] = {}

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        recorded.update(kwargs)
        return subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    _run_tests_in(tmp_path)

    assert recorded["timeout"] == _INNER_SUBPROCESS_TIMEOUT_SECONDS


# ---------------------------------------------------------------------------
# Timeout-budget regression guards (Issue #5102)
# ---------------------------------------------------------------------------

# Worst single inner-suite wall clock measured on a contributor machine, in
# seconds. 80.69s was recorded in Issue #5102 against tests/test_lefthook_
# integration.py alone; _TESTS has since grown a second file that lifts the
# collected count from 859 to 943 (+9.8%), so the same machine now needs ~89s.
_MEASURED_WORST_INNER_SECONDS = 89

# A cap this far above the inner bound is no longer a cap. Pins the other side
# so "raise it until it stops failing" cannot silently disable the budget.
_OUTER_TIMEOUT_CEILING_SECONDS = 1800


def _tests_running_the_inner_suite() -> list[str]:
    """Names of the top-level tests that create a worktree and run the inner suite.

    Discovered from this module's own source rather than hard-coded, so a fifth
    mutant added without the timeout marker fails instead of silently
    inheriting the repo-wide --timeout=120 from pyproject.toml addopts.
    The `scratch_worktree` fixture is the discriminator: taking it is what makes
    a test spawn a real nested pytest run through _run_tests_in.
    """
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    return [
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name.startswith("test_")
        and any(arg.arg == "scratch_worktree" for arg in node.args.args)
    ]


def _timeout_marker_seconds(test_name: str) -> float | None:
    """Return the seconds argument of the test's timeout marker, or None."""
    func = globals()[test_name]
    for mark in getattr(func, "pytestmark", []):
        if mark.name == "timeout" and mark.args:
            return mark.args[0]
    return None


def test_every_inner_suite_test_raises_the_outer_timeout() -> None:
    names = _tests_running_the_inner_suite()

    # Report the scope alongside the finding: a zero-finding sweep over a
    # zero-sized scope proves nothing (testing.md MUST 10).
    assert len(names) == 4, f"Expected 4 inner-suite tests, discovered {len(names)}: {names}"

    unmarked = [name for name in names if _timeout_marker_seconds(name) is None]
    assert not unmarked, (
        f"These tests spawn the inner suite but carry no @pytest.mark.timeout, "
        f"so they inherit the repo-wide --timeout=120 that Issue #5102 blocked "
        f"pushes on: {unmarked}"
    )

    too_low = {
        name: seconds
        for name in names
        if (seconds := _timeout_marker_seconds(name)) is not None
        and seconds < _OUTER_TEST_TIMEOUT_SECONDS
    }
    assert not too_low, (
        f"Timeout lowered below {_OUTER_TEST_TIMEOUT_SECONDS}s: {too_low}. "
        "See Issue #5102 for the measured budget."
    )


def test_outer_timeout_exceeds_the_inner_subprocess_timeout() -> None:
    # Ordering invariant. When the outer cap fires first, pytest-timeout
    # interrupts inside subprocess.communicate and names no command, which is
    # the unactionable failure Issue #5102 reported. The inner bound must win.
    assert _OUTER_TEST_TIMEOUT_SECONDS > _INNER_SUBPROCESS_TIMEOUT_SECONDS


def test_outer_timeout_clears_twice_the_measured_inner_runtime() -> None:
    assert _OUTER_TEST_TIMEOUT_SECONDS >= 2 * _MEASURED_WORST_INNER_SECONDS


def test_outer_timeout_stays_bounded() -> None:
    # pytest-timeout reads 0 as "no timeout at all", so removing the bound and
    # raising it read identically at the marker. Both must fail here.
    assert isinstance(_OUTER_TEST_TIMEOUT_SECONDS, int)
    assert 0 < _OUTER_TEST_TIMEOUT_SECONDS <= _OUTER_TIMEOUT_CEILING_SECONDS


def test_positive_mutant_restores_target_when_test_run_raises(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    original = b"before\n"
    target = tmp_path / _TARGET_REL
    target.parent.mkdir(parents=True)
    target.write_bytes(original)

    def raise_timeout(_wt_path: Path) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(cmd="pytest", timeout=_INNER_SUBPROCESS_TIMEOUT_SECONDS)

    monkeypatch.setattr(sys.modules[__name__], "_run_tests_in", raise_timeout)

    with pytest.raises(subprocess.TimeoutExpired):
        _apply_positive_mutant(tmp_path, original, b"before", b"after", "timeout")

    assert target.read_bytes() == original


@pytest.fixture()
def scratch_worktree() -> Iterator[Path]:
    """Provide a marked scratch git worktree; remove it after the test."""
    with isolated_mutation_worktree(REPO_ROOT, [_TARGET_REL]) as workspace:
        yield workspace.root


def _active_target_unmodified() -> bool:
    """Return True when the mutation target file is unmodified in the active worktree.

    Checks only the target file, not the entire worktree. Other in-progress
    changes (baseline updates, session logs) must not produce false failures.
    """
    result = subprocess.run(
        ["git", "diff", "--name-only", "HEAD", "--", str(_TARGET_REL)],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(REPO_ROOT),
    )
    # Also check the working-tree against the index (unstaged changes).
    result2 = subprocess.run(
        ["git", "diff", "--name-only", "--", str(_TARGET_REL)],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(REPO_ROOT),
    )
    return result.stdout.strip() == "" and result2.stdout.strip() == ""


# ---------------------------------------------------------------------------
# M1: revert directory name from "critique" back to "analysis"
# ---------------------------------------------------------------------------

_M1_ORIGINAL = b'        path.parent == PurePosixPath(".agents/critique")\n'
_M1_MUTANT = b'        path.parent == PurePosixPath(".agents/analysis")  # M1 mutant\n'


@pytest.mark.timeout(_OUTER_TEST_TIMEOUT_SECONDS)
def test_m1_directory_name_reverted_is_detected(scratch_worktree: Path) -> None:
    original = (REPO_ROOT / _TARGET_REL).read_bytes()
    outcome = _apply_positive_mutant(
        scratch_worktree, original, _M1_ORIGINAL, _M1_MUTANT, "M1-dir-name"
    )
    assert outcome == _OUTCOME_DEAD
    assert _active_target_unmodified(), "Mutation target is dirty in active worktree after M1"


# ---------------------------------------------------------------------------
# M2: change the error message to reference a wrong directory
# ---------------------------------------------------------------------------

_M2_ORIGINAL = (
    b'            "ERROR: ADR changes require a debate log staged in .agents/critique",\n'
)
_M2_MUTANT = b'            "ERROR: ADR changes require a debate log staged in .agents/wrong-dir",\n'


@pytest.mark.timeout(_OUTER_TEST_TIMEOUT_SECONDS)
def test_m2_error_message_path_changed_is_detected(scratch_worktree: Path) -> None:
    original = (REPO_ROOT / _TARGET_REL).read_bytes()
    outcome = _apply_positive_mutant(
        scratch_worktree, original, _M2_ORIGINAL, _M2_MUTANT, "M2-error-msg"
    )
    assert outcome == _OUTCOME_DEAD
    assert _active_target_unmodified(), "Mutation target is dirty in active worktree after M2"


# ---------------------------------------------------------------------------
# M3: remove the missing-debate-log early return
# ---------------------------------------------------------------------------

_M3_ORIGINAL = b"    if not debate_logs:\n"
_M3_MUTANT = b"    if False:  # M3 mutant: gate removed\n"


@pytest.mark.timeout(_OUTER_TEST_TIMEOUT_SECONDS)
def test_m3_missing_debate_log_gate_removed_is_detected(scratch_worktree: Path) -> None:
    original = (REPO_ROOT / _TARGET_REL).read_bytes()
    outcome = _apply_positive_mutant(
        scratch_worktree, original, _M3_ORIGINAL, _M3_MUTANT, "M3-gate-removed"
    )
    assert outcome == _OUTCOME_DEAD
    assert _active_target_unmodified(), "Mutation target is dirty in active worktree after M3"


# ---------------------------------------------------------------------------
# IC: inverted control - change a comment only; suite MUST survive (rc == 0)
# ---------------------------------------------------------------------------

_IC_ORIGINAL = (
    b"    # Canonical debate-log directory per:\n"
    b"    #   .claude/skills/adr-review/references/artifacts.md line 3:\n"
    b'    #     "Save debate artifacts to `.agents/critique/`."\n'
    b"    #   .claude/skills/adr-review/references/artifacts.md line 7:\n"
    b'    #     "Save to: `.agents/critique/ADR-NNN-debate-log.md`"\n'
    b"    # Issue #4250: the hook previously searched .agents/analysis/ but the\n"
    b"    # skill writes to .agents/critique/.\n"
)
_IC_MUTANT = (
    b"    # Canonical debate-log directory per:\n"
    b"    #   .claude/skills/adr-review/references/artifacts.md line 3:\n"
    b'    #     "Save debate artifacts to `.agents/critique/`."\n'
    b"    #   .claude/skills/adr-review/references/artifacts.md line 7:\n"
    b'    #     "Save to: `.agents/critique/ADR-NNN-debate-log.md`"\n'
    b"    # Issue #4250: the hook previously searched .agents/analysis/ but the\n"
    b"    # skill writes to .agents/critique/.  # IC mutant\n"
)


@pytest.mark.timeout(_OUTER_TEST_TIMEOUT_SECONDS)
def test_ic_comment_only_change_survives(scratch_worktree: Path) -> None:
    """Inverted control: a comment-only mutation must NOT be detected (rc == 0)."""
    original = (REPO_ROOT / _TARGET_REL).read_bytes()

    count = original.count(_IC_ORIGINAL)
    if count == 0:
        raise AssertionError(
            f"{_OUTCOME_DID_NOT_APPLY} (IC): comment literal not found. "
            "Update this harness to match the current comment."
        )
    if count > 1:
        raise AssertionError(f"PATTERN-AMBIGUOUS (IC): {count} occurrences found.")

    mutated = original.replace(_IC_ORIGINAL, _IC_MUTANT, 1)
    assert mutated != original, "IC mutation produced a byte-identical file"

    wt_target = scratch_worktree / _TARGET_REL
    wt_target.write_bytes(mutated)

    result = _run_tests_in(scratch_worktree)
    _assert_suite_ran(result, "IC")

    assert result.returncode == 0, (
        "INVERTED CONTROL FAILED (IC): suite rejected a comment-only change. "
        "The harness is over-sensitive or a test matches comments.\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert _active_target_unmodified(), "Mutation target is dirty in active worktree after IC"


# ---------------------------------------------------------------------------
# Isolation guarantee test (issue #4346)
# ---------------------------------------------------------------------------


def test_scratch_worktree_created_and_removed() -> None:
    """The scratch worktree fixture creates an isolated tree and removes it.

    Verifies that:
    - The scratch worktree exists and contains the target file.
    - A mutation written to the scratch worktree does NOT appear in the active tree.
    - After the fixture tears down, the scratch worktree directory is gone.
    """
    with isolated_mutation_worktree(REPO_ROOT, [_TARGET_REL]) as workspace:
        wt = workspace.root
        wt_target = wt / _TARGET_REL
        assert wt_target.exists(), "Scratch worktree missing the target file"

        original_active = (REPO_ROOT / _TARGET_REL).read_bytes()
        sentinel = b"# ISOLATION-SENTINEL\n"
        wt_target.write_bytes(original_active + sentinel)

        active_bytes = (REPO_ROOT / _TARGET_REL).read_bytes()
        assert sentinel not in active_bytes, (
            "Writing to scratch worktree leaked into the active worktree"
        )

    assert not wt.exists(), "Scratch worktree directory still exists after removal"
