"""Mutation harness for the ADR debate-log evidence gate (issue #5205).

A red-on-main figure pasted into a PR description is a claim. This module is
the check: each mutant reverts one defect this gate is supposed to stop, and
the #5205 regression suite has to come back red. If it does not, those tests
are decoration.

Eleven mutants and one inverted control. Two revert the defects #5205
reported; nine revert defects found by review of this PR, which are as much
part of the contract as the originals. Each mutant carries its own banner and
docstring at the point of definition, so the inventory here stays a table:

===== ======== ==================================================
 Id    Source   Reverts
===== ======== ==================================================
 M4    issue    the evidence check, so a stub clears again
 M5    issue    ``any()`` coverage, so one log authorizes all
 M6    review   the byte floor onto lossily decoded text
 M7    review   an unreadable log to a silent skip
 M8    review   the unfilled-template placeholder check
 M9    review   the unbounded positions-table fallback
 M10   review   ``T`` from the staged-log discovery query
 M11   review   the staged blob to a lossy decode
 M12   review   placeholder matching to exact literals
 M13   review   the whitespace class to ASCII space and tab
 M14   review   the external exit code to the logic one
 IC    control  nothing; a comment only, and MUST survive
===== ======== ==================================================

Every positive mutant is expected DEAD. IC is expected SURVIVED: without it a
harness that reports DEAD unconditionally looks identical to a working one.

Isolation follows the same model as ``test_mutate_debate_log_path.py``
(issues #4346, #4457): every mutation runs inside a detached scratch worktree
and the active worktree's tracked files are never written. This module is
separate from that one rather than appended to it because the combined file
crossed the 500-line taste ceiling, and because the two harnesses guard
different defects; the repository already keys mutation harnesses by issue.
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from scripts.testing.mutation_workspace import isolated_mutation_worktree

REPO_ROOT = Path(__file__).resolve().parents[2]
_TARGET_REL = Path("scripts") / "validation" / "git_hook_policy.py"
# The two defects are only observable through the suite written for #5205.
# Both halves of the split suite. The boundary module is not optional here:
# M6's killer, test_invalid_utf8_bytes_do_not_inflate_toward_the_byte_floor,
# lives there, so running only the sibling would report M6 SURVIVED.
_TESTS = [
    "tests/validation/test_git_hook_policy_adr_debate_evidence.py",
    "tests/validation/test_git_hook_policy_adr_debate_boundaries.py",
    "tests/validation/test_git_hook_policy_adr_debate_mirrors.py",
    "tests/validation/test_git_hook_policy_adr_debate_discovery.py",
]

_OUTCOME_DEAD = "DEAD"
_OUTCOME_SURVIVED = "SURVIVED"
_OUTCOME_DID_NOT_APPLY = "DID-NOT-APPLY"

# Same ordering contract as the sibling harness: the outer cap MUST exceed the
# inner one, or pytest-timeout interrupts inside subprocess.communicate and the
# failure names no command (issue #5102). The inner suite here is
# four files of 62 cases total, well under the sibling's ~943, so these caps
# carry wide margin.
_INNER_SUBPROCESS_TIMEOUT_SECONDS = 300
_OUTER_TEST_TIMEOUT_SECONDS = 360


def _run_tests_in(wt_path: Path) -> subprocess.CompletedProcess[str]:
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
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        timeout=_INNER_SUBPROCESS_TIMEOUT_SECONDS,
    )


def _assert_suite_ran(result: subprocess.CompletedProcess[str], label: str) -> None:
    assert result.returncode != 4, (
        f"{label}: pytest exited 4 (file or directory not found). "
        f"Suite was never collected.\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "no tests ran" not in result.stdout.lower(), (
        f"{label}: no tests were collected.\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def _mutate(wt_path: Path, original: bytes, before: bytes, after: bytes, label: str) -> bytes:
    count = original.count(before)
    if count == 0:
        raise AssertionError(
            f"{_OUTCOME_DID_NOT_APPLY} ({label}): literal not found in target. "
            "The file was changed; update this harness."
        )
    if count > 1:
        raise AssertionError(f"PATTERN-AMBIGUOUS ({label}): expected 1 occurrence, found {count}.")
    mutated = original.replace(before, after, 1)
    assert mutated != original, f"Mutation {label} produced a byte-identical file"
    (wt_path / _TARGET_REL).write_bytes(mutated)
    return mutated


def _run_mutant(
    wt_path: Path, original: bytes, before: bytes, after: bytes, label: str
) -> subprocess.CompletedProcess[str]:
    _mutate(wt_path, original, before, after, label)
    wt_target = wt_path / _TARGET_REL
    try:
        result = _run_tests_in(wt_path)
    finally:
        wt_target.write_bytes(original)
        assert wt_target.read_bytes() == original, (
            f"{label}: scratch worktree target was not restored to original bytes"
        )
    _assert_suite_ran(result, label)
    return result


def _apply_positive_mutant(
    wt_path: Path, original: bytes, before: bytes, after: bytes, label: str
) -> str:
    result = _run_mutant(wt_path, original, before, after, label)
    assert result.returncode != 0, (
        f"MUTANT SURVIVED ({label}): suite passed after mutation. "
        f"Tests do not detect the regression.\nstdout:\n{result.stdout}"
    )
    return _OUTCOME_DEAD


@pytest.fixture()
def scratch_worktree() -> Iterator[Path]:
    """Provide a marked scratch git worktree; remove it after the test."""
    with isolated_mutation_worktree(REPO_ROOT, [_TARGET_REL]) as workspace:
        yield workspace.root


def _active_target_unmodified() -> bool:
    result = subprocess.run(
        ["git", "diff", "--name-only", "HEAD", "--", str(_TARGET_REL)],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(REPO_ROOT),
        check=False,
    )
    return result.returncode == 0 and not result.stdout.strip()


# ---------------------------------------------------------------------------
# M4: neuter the evidence check, reverting defect 1
# ---------------------------------------------------------------------------

_M4_ORIGINAL = b"    evidence_error = _debate_log_evidence_error(contents)\n"
_M4_MUTANT = b"    evidence_error = None  # M4 mutant: evidence check removed\n"


@pytest.mark.timeout(_OUTER_TEST_TIMEOUT_SECONDS)
def test_m4_evidence_check_removed_is_detected(scratch_worktree: Path) -> None:
    original = (REPO_ROOT / _TARGET_REL).read_bytes()
    outcome = _apply_positive_mutant(
        scratch_worktree, original, _M4_ORIGINAL, _M4_MUTANT, "M4-evidence-removed"
    )
    assert outcome == _OUTCOME_DEAD
    assert _active_target_unmodified(), "Mutation target is dirty in active worktree after M4"


# ---------------------------------------------------------------------------
# M5: restore the any() coverage semantics, reverting defect 2
# ---------------------------------------------------------------------------

_M5_ORIGINAL = (
    b"    return {\n"
    b"        staged for staged in adr_ids"
    b" if _normalized_record_number(staged) not in covered\n"
    b"    }\n"
)
_M5_MUTANT = (
    b"    # M5 mutant: any() semantics restored\n"
    b"    normalized = {_normalized_record_number(staged) for staged in adr_ids}\n"
    b"    return set() if (covered & normalized) else set(adr_ids)\n"
)


@pytest.mark.timeout(_OUTER_TEST_TIMEOUT_SECONDS)
def test_m5_coverage_reverted_to_any_semantics_is_detected(scratch_worktree: Path) -> None:
    original = (REPO_ROOT / _TARGET_REL).read_bytes()
    outcome = _apply_positive_mutant(
        scratch_worktree, original, _M5_ORIGINAL, _M5_MUTANT, "M5-any-coverage"
    )
    assert outcome == _OUTCOME_DEAD
    assert _active_target_unmodified(), "Mutation target is dirty in active worktree after M5"


# ---------------------------------------------------------------------------
# M6: measure the byte floor on the decoded text again, restoring the
# replacement-character inflation a review found on PR #5308
# ---------------------------------------------------------------------------

_M6_ORIGINAL = b"    if _evidence_byte_count(content) < DEBATE_LOG_MIN_BYTES:\n"
_M6_MUTANT = (
    b"    # M6 mutant: byte floor measured on the decoded text\n"
    b'    if len(content.encode("utf-8")) < DEBATE_LOG_MIN_BYTES:\n'
)


@pytest.mark.timeout(_OUTER_TEST_TIMEOUT_SECONDS)
def test_m6_byte_floor_measured_after_lossy_decode_is_detected(scratch_worktree: Path) -> None:
    """Each invalid byte re-encodes to three, so 100 on-disk bytes measured 300."""
    original = (REPO_ROOT / _TARGET_REL).read_bytes()
    outcome = _apply_positive_mutant(
        scratch_worktree, original, _M6_ORIGINAL, _M6_MUTANT, "M6-inflated-byte-floor"
    )
    assert outcome == _OUTCOME_DEAD
    assert _active_target_unmodified(), "Mutation target is dirty in active worktree after M6"


# ---------------------------------------------------------------------------
# M7: drop an unreadable staged log silently, restoring the fail-open a review
# found on PR #5308
# ---------------------------------------------------------------------------

_M7_ORIGINAL = b"    if unreadable:\n"
_M7_MUTANT = b"    if False:  # M7 mutant: unreadable staged logs are skipped silently\n"


@pytest.mark.timeout(_OUTER_TEST_TIMEOUT_SECONDS)
def test_m7_silently_skipping_an_unreadable_log_is_detected(scratch_worktree: Path) -> None:
    """A covering sibling must not excuse a staged log that will not read."""
    original = (REPO_ROOT / _TARGET_REL).read_bytes()
    outcome = _apply_positive_mutant(
        scratch_worktree, original, _M7_ORIGINAL, _M7_MUTANT, "M7-unreadable-skipped"
    )
    assert outcome == _OUTCOME_DEAD
    assert _active_target_unmodified(), "Mutation target is dirty in active worktree after M7"


# ---------------------------------------------------------------------------
# M8: drop the unfilled-template placeholder check, restoring the fail-open a
# review found on PR #5308
# ---------------------------------------------------------------------------

_M8_ORIGINAL = b"    if unresolved:\n"
_M8_MUTANT = b"    if False:  # M8 mutant: unfilled template placeholders accepted\n"


@pytest.mark.timeout(_OUTER_TEST_TIMEOUT_SECONDS)
def test_m8_accepting_an_unfilled_template_is_detected(scratch_worktree: Path) -> None:
    """Copying the canonical template is not conducting a review."""
    original = (REPO_ROOT / _TARGET_REL).read_bytes()
    outcome = _apply_positive_mutant(
        scratch_worktree, original, _M8_ORIGINAL, _M8_MUTANT, "M8-unfilled-template"
    )
    assert outcome == _OUTCOME_DEAD
    assert _active_target_unmodified(), "Mutation target is dirty in active worktree after M8"


# ---------------------------------------------------------------------------
# M9: restore the unbounded positions-table fallback deleted after review of
# PR #5308
# ---------------------------------------------------------------------------

_M9_ORIGINAL = b"""    lines = content.splitlines()
    for index, line in enumerate(lines):
"""
_M9_MUTANT = b"""    lines = content.splitlines()
    if any(  # M9 mutant: unbounded positions-table fallback restored
        candidate.lstrip().startswith("|")
        and DEBATE_LOG_ROLE_RE.search(candidate)
        and DEBATE_LOG_DECISION_RE.search(candidate)
        for candidate in lines
    ):
        return True
    for index, line in enumerate(lines):
"""


@pytest.mark.timeout(_OUTER_TEST_TIMEOUT_SECONDS)
def test_m9_unbounded_positions_table_fallback_is_detected(scratch_worktree: Path) -> None:
    """A role beside a decision word in prose notes must not read as a verdict."""
    original = (REPO_ROOT / _TARGET_REL).read_bytes()
    outcome = _apply_positive_mutant(
        scratch_worktree, original, _M9_ORIGINAL, _M9_MUTANT, "M9-unbounded-table"
    )
    assert outcome == _OUTCOME_DEAD
    assert _active_target_unmodified(), "Mutation target is dirty in active worktree after M9"


# ---------------------------------------------------------------------------
# M10: drop type changes from staged-log discovery, restoring the fail-open a
# review found on PR #5308
# ---------------------------------------------------------------------------

_M10_ORIGINAL = b'            "--diff-filter=ACMRT",\n            "-z",\n'
_M10_MUTANT = (
    b'            "--diff-filter=ACMR",  # M10 mutant: type changes not discovered\n'
    b'            "-z",\n'
)


@pytest.mark.timeout(_OUTER_TEST_TIMEOUT_SECONDS)
def test_m10_dropping_type_changes_from_discovery_is_detected(scratch_worktree: Path) -> None:
    """Converting a tracked log to a symlink stages as T, not as A/C/M/R."""
    original = (REPO_ROOT / _TARGET_REL).read_bytes()
    outcome = _apply_positive_mutant(
        scratch_worktree, original, _M10_ORIGINAL, _M10_MUTANT, "M10-no-type-changes"
    )
    assert outcome == _OUTCOME_DEAD
    assert _active_target_unmodified(), "Mutation target is dirty in active worktree after M10"


# ---------------------------------------------------------------------------
# M11: decode the staged blob lossily again, restoring the fail-open a review
# found on PR #5308
# ---------------------------------------------------------------------------

_M11_ORIGINAL = b'        return blob.decode("utf-8")\n    except UnicodeDecodeError:\n'
_M11_MUTANT = (
    b"        # M11 mutant: invalid bytes decoded away instead of reported\n"
    b'        return blob.decode("utf-8", errors="replace")\n'
    b"    except UnicodeDecodeError:\n"
)


@pytest.mark.timeout(_OUTER_TEST_TIMEOUT_SECONDS)
def test_m11_lossy_decoding_of_the_staged_blob_is_detected(scratch_worktree: Path) -> None:
    """Corrupting each placeholder defeats the fifth signal; the decode stops it."""
    original = (REPO_ROOT / _TARGET_REL).read_bytes()
    outcome = _apply_positive_mutant(
        scratch_worktree, original, _M11_ORIGINAL, _M11_MUTANT, "M11-lossy-decode"
    )
    assert outcome == _OUTCOME_DEAD
    assert _active_target_unmodified(), "Mutation target is dirty in active worktree after M11"


# ---------------------------------------------------------------------------
# M12: match the template placeholders exactly again, restoring the fail-open a
# review found on PR #5308
# ---------------------------------------------------------------------------

_M12_ORIGINAL = b"        if _normalized_for_placeholders(placeholder) in normalized\n"
_M12_MUTANT = (
    b"        # M12 mutant: placeholders matched exactly, spacing and case win\n"
    b"        if placeholder in content\n"
)


@pytest.mark.timeout(_OUTER_TEST_TIMEOUT_SECONDS)
def test_m12_exact_placeholder_matching_is_detected(scratch_worktree: Path) -> None:
    """One space before each closing bracket defeated exact matching."""
    original = (REPO_ROOT / _TARGET_REL).read_bytes()
    outcome = _apply_positive_mutant(
        scratch_worktree, original, _M12_ORIGINAL, _M12_MUTANT, "M12-exact-placeholders"
    )
    assert outcome == _OUTCOME_DEAD
    assert _active_target_unmodified(), "Mutation target is dirty in active worktree after M12"


# ---------------------------------------------------------------------------
# M13: narrow the placeholder whitespace class back to ASCII, restoring the
# fail-open a review found on PR #5308
# ---------------------------------------------------------------------------

_M13_ORIGINAL = b'DEBATE_LOG_PLACEHOLDER_SPACING_RE = re.compile(r"[^\\S\\r\\n]+")\n'
_M13_MUTANT = (
    b"# M13 mutant: only ASCII space and tab collapse\n"
    b'DEBATE_LOG_PLACEHOLDER_SPACING_RE = re.compile(r"[ \\t]+")\n'
)


@pytest.mark.timeout(_OUTER_TEST_TIMEOUT_SECONDS)
def test_m13_ascii_only_whitespace_normalization_is_detected(scratch_worktree: Path) -> None:
    """One U+00A0 before each closing bracket cleared the unfilled template."""
    original = (REPO_ROOT / _TARGET_REL).read_bytes()
    outcome = _apply_positive_mutant(
        scratch_worktree, original, _M13_ORIGINAL, _M13_MUTANT, "M13-ascii-whitespace"
    )
    assert outcome == _OUTCOME_DEAD
    assert _active_target_unmodified(), "Mutation target is dirty in active worktree after M13"


# ---------------------------------------------------------------------------
# M14: collapse the external failure back into the logic exit code
# ---------------------------------------------------------------------------

_M14_ORIGINAL = b"        return 3\n"
_M14_MUTANT = b"        return 1  # M14 mutant: git failure reported as a logic violation\n"


@pytest.mark.timeout(_OUTER_TEST_TIMEOUT_SECONDS)
def test_m14_external_failure_exit_code_is_detected(scratch_worktree: Path) -> None:
    """AGENTS.md:50 reserves 3 for external failures; this gate is a CLI handler."""
    original = (REPO_ROOT / _TARGET_REL).read_bytes()
    outcome = _apply_positive_mutant(
        scratch_worktree, original, _M14_ORIGINAL, _M14_MUTANT, "M14-exit-code-class"
    )
    assert outcome == _OUTCOME_DEAD
    assert _active_target_unmodified(), "Mutation target is dirty in active worktree after M14"


# ---------------------------------------------------------------------------
# IC: comment-only change; the suite MUST survive it
# ---------------------------------------------------------------------------

_IC_ORIGINAL = b"DEBATE_LOG_MIN_BYTES = 300\n"
_IC_MUTANT = b"DEBATE_LOG_MIN_BYTES = 300  # IC mutant: comment only\n"


@pytest.mark.timeout(_OUTER_TEST_TIMEOUT_SECONDS)
def test_ic_comment_only_change_survives(scratch_worktree: Path) -> None:
    """Inverted control: proves the harness can tell green from red."""
    original = (REPO_ROOT / _TARGET_REL).read_bytes()
    result = _run_mutant(scratch_worktree, original, _IC_ORIGINAL, _IC_MUTANT, "IC-comment-only")
    assert result.returncode == 0, (
        f"INVERTED CONTROL FAILED: a comment-only change reddened the suite, so a "
        f"DEAD verdict from any positive mutant proves nothing.\nstdout:\n{result.stdout}"
    )
    assert _active_target_unmodified(), "Mutation target is dirty in active worktree after IC"


def _tests_running_the_inner_suite() -> list[str]:
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    return [
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name.startswith("test_")
        and any(arg.arg == "scratch_worktree" for arg in node.args.args)
    ]


def test_every_inner_suite_test_raises_the_outer_timeout() -> None:
    """Report the scope alongside the finding (testing.md MUST 10)."""
    names = _tests_running_the_inner_suite()
    assert len(names) == 12, f"Expected 12 inner-suite tests, discovered {len(names)}: {names}"

    unmarked = [
        name
        for name in names
        if not any(
            mark.name == "timeout" and mark.args and mark.args[0] >= _OUTER_TEST_TIMEOUT_SECONDS
            for mark in getattr(globals()[name], "pytestmark", [])
        )
    ]
    assert not unmarked, (
        f"These tests spawn the inner suite but carry no adequate "
        f"@pytest.mark.timeout, so they inherit the repo-wide --timeout=120 "
        f"that issue #5102 blocked pushes on: {unmarked}"
    )
