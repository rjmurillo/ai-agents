"""M13 through M20 of the ADR debate-log evidence mutation harness (issue #5205).

Split from ``test_mutate_adr_debate_evidence.py`` when that module crossed the
500-line taste ceiling. No semantic seam here the way the validation-suite
splits have one: this is the second half of the mutant catalog by number, not
a grouping by concern. M13, M15 and M17 revert placeholder-normalization
folding; M14, M16, M18, M19 and M20 revert the exit-code and read-path
contract. They landed in review in that mixed order and are kept in that
order rather than reshuffled into a false grouping.

Same isolation model as the sibling file: every mutation runs inside a
detached scratch worktree, and the active worktree's tracked files are never
written. See ``test_mutate_adr_debate_evidence.py`` for the full mutant
inventory table and the inverted control.

Issue #5205.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from tests.mutation._adr_debate_harness import (
    _OUTCOME_DEAD,
    _OUTER_TEST_TIMEOUT_SECONDS,
    _TARGET_REL,
    REPO_ROOT,
    _active_target_unmodified,
    _apply_positive_mutant,
)

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

# Anchored on the comment above it: bare ``return 3`` occurs four times in the
# module, and the harness's ambiguity guard rejected the unanchored pattern
# rather than mutating an unrelated exit. That guard working is why this is a
# two-line pattern.
_M14_ORIGINAL = (
    b"        # that is a judgement about staged evidence rather than about git.\n"
    b"        return 3\n"
)
_M14_MUTANT = (
    b"        # are all judgements about staged evidence.\n"
    b"        return 1  # M14 mutant: git failure reported as a logic violation\n"
)


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
# M15: stop resolving markdown escapes and invisible characters, restoring the
# fourth and fifth defeats of the placeholder check
# ---------------------------------------------------------------------------

_M15_ORIGINAL = b'    unescaped = DEBATE_LOG_PLACEHOLDER_ESCAPE_RE.sub(r"\\1", visible)\n'
_M15_MUTANT = b"    unescaped = visible  # M15 mutant: markdown escapes survive\n"


@pytest.mark.timeout(_OUTER_TEST_TIMEOUT_SECONDS)
def test_m15_unresolved_markdown_escapes_are_detected(scratch_worktree: Path) -> None:
    """`\\]` renders as `]`, so the template reads as shipped and matches nothing."""
    original = (REPO_ROOT / _TARGET_REL).read_bytes()
    outcome = _apply_positive_mutant(
        scratch_worktree, original, _M15_ORIGINAL, _M15_MUTANT, "M15-markdown-escapes"
    )
    assert outcome == _OUTCOME_DEAD
    assert _active_target_unmodified(), "Mutation target is dirty in active worktree after M15"


# ---------------------------------------------------------------------------
# M16: collapse the per-path regular-file tri-state back into a boolean
# ---------------------------------------------------------------------------

_M16_ORIGINAL = b"""    if result.returncode == 1:
        return False
    if result.returncode != 0:
        _print_process_output(result, stdout_stream=sys.stderr)
        return None
"""
_M16_MUTANT = b"""    if result.returncode != 0:  # M16 mutant: every failure reads as False
        return False
"""


@pytest.mark.timeout(_OUTER_TEST_TIMEOUT_SECONDS)
def test_m16_regular_file_query_failure_collapsed_is_detected(scratch_worktree: Path) -> None:
    """A broken or timed-out ls-files must not be reported as a staged symlink.

    The prior mutant only broke the rc=1 branch, which the "missing from the
    index" test alone kills without touching a query failure at all. This
    mutant deletes the ``None`` branch outright, collapsing every nonzero
    code (128, a timeout's synthesized 3, or 1) to ``False``, so it is killed
    only by a test that proves a genuine query failure is not misread as a
    definite "not a regular file" answer. Found by review.
    """
    original = (REPO_ROOT / _TARGET_REL).read_bytes()
    outcome = _apply_positive_mutant(
        scratch_worktree, original, _M16_ORIGINAL, _M16_MUTANT, "M16-regular-file-tristate"
    )
    assert outcome == _OUTCOME_DEAD
    assert _active_target_unmodified(), "Mutation target is dirty in active worktree after M16"


# ---------------------------------------------------------------------------
# M19: narrow the tri-state discriminator back to "only 128 is fatal", so a
# timeout or failed process start (_run_command's synthesized 3) misreads as
# "not a regular file" again
# ---------------------------------------------------------------------------

_M19_ORIGINAL = b"""    if result.returncode == 1:
        return False
    if result.returncode != 0:
        _print_process_output(result, stdout_stream=sys.stderr)
        return None
"""
_M19_MUTANT = b"""    if result.returncode == 128:  # M19 mutant: only 128 counts as unknown
        _print_process_output(result, stdout_stream=sys.stderr)
        return None
    if result.returncode != 0:
        return False
"""


@pytest.mark.timeout(_OUTER_TEST_TIMEOUT_SECONDS)
def test_m19_timeout_misread_as_not_regular_is_detected(scratch_worktree: Path) -> None:
    """A timed-out ls-files (synthesized exit 3) must not read as "not found"."""
    original = (REPO_ROOT / _TARGET_REL).read_bytes()
    outcome = _apply_positive_mutant(
        scratch_worktree, original, _M19_ORIGINAL, _M19_MUTANT, "M19-timeout-misclassified"
    )
    assert outcome == _OUTCOME_DEAD
    assert _active_target_unmodified(), "Mutation target is dirty in active worktree after M19"


# ---------------------------------------------------------------------------
# M17: stop dropping Unicode format characters. M15 only removed the escape
# resolution, so the zero-width and soft-hyphen cases had no mutant of their
# own and could not prove they detect anything. Found by review.
# ---------------------------------------------------------------------------

_M17_ORIGINAL = b'    visible = "".join(\n'
_M17_MUTANT = (
    b'    visible = text  # M17 mutant: invisible characters survive\n    _unused = "".join(\n'
)


@pytest.mark.timeout(_OUTER_TEST_TIMEOUT_SECONDS)
def test_m17_invisible_characters_surviving_is_detected(scratch_worktree: Path) -> None:
    """Zero-width space and soft hyphen render as nothing and cleared the gate."""
    original = (REPO_ROOT / _TARGET_REL).read_bytes()
    outcome = _apply_positive_mutant(
        scratch_worktree, original, _M17_ORIGINAL, _M17_MUTANT, "M17-format-characters"
    )
    assert outcome == _OUTCOME_DEAD
    assert _active_target_unmodified(), "Mutation target is dirty in active worktree after M17"


# ---------------------------------------------------------------------------
# M18: collapse a blob git would not produce back into the decode failure
# ---------------------------------------------------------------------------

_M18_ORIGINAL = b"""        if blob_result.returncode != 0:
            unreadable.append(path)
"""
_M18_MUTANT = b"""        if blob_result.returncode != 0:
            undecodable.append(path)  # M18 mutant: git failure reads as bad bytes
"""


@pytest.mark.timeout(_OUTER_TEST_TIMEOUT_SECONDS)
def test_m18_read_failure_collapsed_into_decode_failure_is_detected(
    scratch_worktree: Path,
) -> None:
    """A blob git will not produce is external, not the committer's mojibake."""
    original = (REPO_ROOT / _TARGET_REL).read_bytes()
    outcome = _apply_positive_mutant(
        scratch_worktree, original, _M18_ORIGINAL, _M18_MUTANT, "M18-read-vs-decode"
    )
    assert outcome == _OUTCOME_DEAD
    assert _active_target_unmodified(), "Mutation target is dirty in active worktree after M18"


# ---------------------------------------------------------------------------
# M20: stop preserving git's diagnostic through the blob-read failure path,
# restoring the message that claimed output it never printed
# ---------------------------------------------------------------------------

_M20_ORIGINAL = b'blob_result.stderr.decode("utf-8", errors="replace")'
_M20_MUTANT = b'""  # M20 mutant: diagnostic discarded'


@pytest.mark.timeout(_OUTER_TEST_TIMEOUT_SECONDS)
def test_m20_discarded_blob_read_diagnostic_is_detected(scratch_worktree: Path) -> None:
    """git's own stderr for a failed blob read must reach the committer."""
    original = (REPO_ROOT / _TARGET_REL).read_bytes()
    outcome = _apply_positive_mutant(
        scratch_worktree, original, _M20_ORIGINAL, _M20_MUTANT, "M20-discarded-diagnostic"
    )
    assert outcome == _OUTCOME_DEAD
    assert _active_target_unmodified(), "Mutation target is dirty in active worktree after M20"


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
    """Report the scope alongside the finding (testing.md MUST 10).

    This file's own guard, covering only the mutants defined here. The
    sibling file's guard covers M4 through M12 plus the inverted control;
    this one covers M13 through M20.
    """
    names = _tests_running_the_inner_suite()
    assert len(names) == 8, f"Expected 8 inner-suite tests, discovered {len(names)}: {names}"

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
