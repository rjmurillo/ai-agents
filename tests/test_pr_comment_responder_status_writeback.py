# taste-lint: ignore file-size, one contract across eleven carriers. Splitting
# it would duplicate the Gate 3 step constants and the comment-map and task-list
# fixture builders that every case here shares, and a second copy of those is
# how a carrier drops out of coverage unnoticed.
"""Regression coverage for the comment-map status write-back (issue #4054).

PR #5342 made Gate 4, Gate 5, and Phase 8.1 derive pending from ``comments.md``:
``TOTAL`` counts every rendered ``**Status**:`` field, ``TERMINAL`` counts the
ones the vocabulary table marks terminal, and the difference is pending. That
derivation is correct and covered by
``tests/test_pr_comment_responder_status_greps.py``.

Nothing in the documented workflow wrote a terminal status into that file.
Gate 3 and Step 6.5 rewrote ``tasks.md`` only, and Step 2.2 renders every detail
entry at ``**Status**: [ACKNOWLEDGED]``. A run that followed the instructions to
the letter therefore left every status at its starting value, so pending stayed
equal to the comment count and Gate 4 blocked forever. That is the fail-closed
mirror of the fail-open bug PR #5342 fixed: same missing link between the two
artifacts, opposite direction.

Gate 3 now writes both artifacts in one step. These tests lift the shipped
Gate 3 fence out of each carrier, run it against real files with a real shell,
then feed the result to that same carrier's Gate 4 derivation. The workflow is
proven to reach ``PENDING=0`` end to end rather than asserted to.

The helpers, carrier list, and Gate 4 slicer are imported from
``test_pr_comment_responder_status_greps`` rather than restated. A second copy
of the carrier list is how a carrier drops out of coverage unnoticed.
"""

from __future__ import annotations

import shlex
import subprocess
from collections.abc import Sequence
from pathlib import Path

import pytest

from tests.test_pr_comment_responder_status_greps import (
    CARRIER_PATHS,
    REPO_ROOT,
    TERMINAL_PATTERN,
    VOCABULARY_CARRIERS,
    _bash_fences,
    _carrier_id,
    _derivation_script,
    _gate_four_fence,
    _grep_count,
    _run_derivation,
    requires_bash,
    requires_grep,
)

TEMPLATE = REPO_ROOT / "templates/agents/pr-comment-responder.shared.md"

# The condensed workflow reference and its generated plugin copy. They restate
# the post-implementation checklist in prose, so they carry the same defect in
# shorter form and must name the comment map too.
WORKFLOW_CARRIERS: tuple[Path, ...] = (
    REPO_ROOT / ".claude/skills/pr-comment-responder/references/workflow.md",
    REPO_ROOT / "src/copilot-cli/skills/pr-comment-responder/references/workflow.md",
)

GATE_THREE_HEADING_KEY = "Gate 3"

# The steps Gate 3 must publish, quoted verbatim from
# templates/agents/pr-comment-responder.shared.md. The comment-map write is the
# one this suite exists for: without it the task list moves and the artifact
# every later gate counts does not.
COMMENT_ID_GUARD = 'case "$COMMENT_ID" in'
TERMINAL_STATUS_GUARD = "printf '%s\\n' \"**Status**: $TERMINAL_STATUS\" \\"
# The preflight that makes the step atomic. It runs before either file is
# written, so a comment the map cannot receive blocks with both artifacts
# untouched instead of leaving the task list ahead of the map.
COMMENT_MAP_PREFLIGHT = 'sed -n "/^### Comment $COMMENT_ID /,/^---$/p" "$COMMENT_MAP" \\'
# Phase 6 renders the task row as `- [ ] **TASK-[id]**: [description]`, which
# carries no `pending` token. The older `s/TASK-$COMMENT_ID.*pending/`
# substitution therefore matched nothing against a real task list and then
# failed its own verification, so Gate 3 could not pass. Marking a task done
# ticks the box and appends the terminal status.
TASK_ROW_GUARD = 'if grep -qF -- "$TASK_ROW" "$TASK_LIST"; then'
TASK_LIST_WRITE = (
    'sed -i "s|^- \\[ \\] \\*\\*TASK-$COMMENT_ID\\*\\*:\\(.*\\)$'
    '|- [x] **TASK-$COMMENT_ID**:\\1 $TERMINAL_STATUS|" "$TASK_LIST"'
)
COMMENT_MAP_WRITE = (
    'sed -i "/^### Comment $COMMENT_ID /,/^---$/ '
    's|^\\*\\*Status\\*\\*: .*$|**Status**: $TERMINAL_STATUS|" "$COMMENT_MAP"'
)
TASK_LIST_VERIFY = (
    'grep -F -- "- [x] **TASK-$COMMENT_ID**:" "$TASK_LIST" | grep -qF -- "$TERMINAL_STATUS"'
)
COMMENT_MAP_VERIFY = 'grep -qxF "**Status**: $TERMINAL_STATUS"'

REQUIRED_GATE_THREE_STEPS: tuple[str, ...] = (
    COMMENT_ID_GUARD,
    TERMINAL_STATUS_GUARD,
    COMMENT_MAP_PREFLIGHT,
    TASK_ROW_GUARD,
    TASK_LIST_WRITE,
    TASK_LIST_VERIFY,
    COMMENT_MAP_WRITE,
    COMMENT_MAP_VERIFY,
)

# The terminal-status guard must screen against Gate 4's own pattern. A near
# copy would admit a value the later gates reject, which is the split-contract
# shape issue #4054 reports.
TERMINAL_STATUS_GUARD_GREP = f'grep -Eq "{TERMINAL_PATTERN}"'

# Every terminal value the vocabulary table publishes. Gate 3 must be able to
# write each one, and Gate 4's terminal grep must then count it.
TERMINAL_STATUSES: tuple[str, ...] = (
    "[COMPLETE]",
    "[WONTFIX]",
    "[DUPLICATE]",
    "[DEFERRED] Refs #4054",
)

# The status Step 2.2 renders for every detail entry. Non-terminal by design:
# it is the starting value, and the whole defect is that nothing moved it.
INITIAL_STATUS = "[ACKNOWLEDGED]"

API_COMMENT_IDS: tuple[str, ...] = ("123", "124", "125")


def _comment_detail(comment_id: str, status: str) -> list[str]:
    """One detail entry in the shape Step 2.2 renders."""
    return [
        f"### Comment {comment_id} (@reviewer)",
        "",
        "**Type**: Review",
        "**Path**: file.py",
        f"**Line**: {comment_id}",
        "**Created**: 2026-08-27 00:00:00",
        f"**Status**: {status}",
        "",
        "**Comment**:",
        "> Reviewer body.",
        "",
        "---",
        "",
    ]


def _write_comment_map(tmp_path: Path, comment_ids: Sequence[str]) -> Path:
    lines = ["# PR Comment Map: PR #5342", ""]
    for comment_id in comment_ids:
        lines.extend(_comment_detail(comment_id, INITIAL_STATUS))
    target = tmp_path / "comments.md"
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target


def _task_row(comment_id: str) -> list[str]:
    """One task entry in the shape Phase 6 renders.

    Quoted from the ``Implementation Tasks (Phase 6)`` template in
    ``templates/agents/pr-comment-responder.shared.md``::

        - [ ] **TASK-[id]**: [description]
          - Comment: [comment_id] by @[author]
          - File: [path]
          - Plan: `.agents/pr-comments/PR-[number]/[comment_id]-plan.md`

    No ``pending`` token appears anywhere in it. An earlier fixture appended
    one, which made a Gate 3 step that matched on ``pending`` look correct
    against a shape the workflow never emits.
    """
    return [
        f"- [ ] **TASK-{comment_id}**: address comment {comment_id}",
        f"  - Comment: {comment_id} by @reviewer",
        "  - File: file.py",
        f"  - Plan: `.agents/pr-comments/PR-5342/{comment_id}-plan.md`",
    ]


def _write_task_list(tmp_path: Path, comment_ids: Sequence[str]) -> Path:
    lines = [
        "# PR #5342 Task List",
        "",
        "## Implementation Tasks (Phase 6)",
        "",
        "### Critical Priority",
        "",
    ]
    for comment_id in comment_ids:
        lines.extend(_task_row(comment_id))
    target = tmp_path / "tasks.md"
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target


def _status_lines(comment_map: Path) -> list[str]:
    return [
        line
        for line in comment_map.read_text(encoding="utf-8").splitlines()
        if line.startswith("**Status**: ")
    ]


def _gate_three_fence(path: Path) -> str:
    """Return the Gate 3 bash fence published by one carrier."""
    for heading, body in _bash_fences(path.read_text(encoding="utf-8")):
        if heading.startswith(GATE_THREE_HEADING_KEY):
            return body
    raise AssertionError(f"{_carrier_id(path)} publishes no Gate 3 fence")


def _gate_three_script(
    fence: str,
    *,
    comment_map: Path,
    task_list: Path,
    comment_id: str,
    terminal_status: str,
    with_map_writeback: bool = True,
) -> str:
    """Lift Gate 3's executable steps out verbatim and make them runnable.

    The slice starts at the comment-id guard, which drops only the two
    placeholder path assignments the carrier leaves to the caller. Setting
    ``with_map_writeback`` to False truncates the slice after the task-list
    verification, reproducing the step as it shipped before this fix: task list
    updated, comment map untouched.
    """
    assert COMMENT_ID_GUARD in fence, "Gate 3 fence publishes no comment-id guard"
    assert COMMENT_MAP_WRITE in fence, (
        "Gate 3 fence publishes no comment-map write, so the artifact Gate 4 "
        "counts never leaves its starting status (issue #4054)"
    )
    assert TASK_LIST_VERIFY in fence, "Gate 3 fence publishes no task-list verification"

    body = fence[fence.index(COMMENT_ID_GUARD) :]
    if not with_map_writeback:
        # Cut at the comment-map write, not at the task-list verification: the
        # verification sits inside the `if` that guards an optional task row,
        # so truncating there would leave the block unterminated. Everything
        # before the cut is the task-list half, `fi` included.
        body = body[: body.index(COMMENT_MAP_WRITE)]
    return (
        f"COMMENT_MAP={shlex.quote(str(comment_map))}\n"
        f"TASK_LIST={shlex.quote(str(task_list))}\n"
        f"COMMENT_ID={shlex.quote(comment_id)}\n"
        f"TERMINAL_STATUS={shlex.quote(terminal_status)}\n"
        f"{body}\n"
    )


def _run_gate_three(
    path: Path,
    *,
    comment_map: Path,
    task_list: Path,
    comment_id: str,
    terminal_status: str,
    with_map_writeback: bool = True,
) -> subprocess.CompletedProcess[str]:
    script = _gate_three_script(
        _gate_three_fence(path),
        comment_map=comment_map,
        task_list=task_list,
        comment_id=comment_id,
        terminal_status=terminal_status,
        with_map_writeback=with_map_writeback,
    )
    return _run_derivation(script)


# Gate 3, executed by the shell the carriers publish it for.


@requires_bash
@pytest.mark.parametrize("path", CARRIER_PATHS, ids=_carrier_id)
def test_gate_three_writes_the_terminal_status_into_the_comment_map(
    path: Path, tmp_path: Path
) -> None:
    """The step that marks a task done must move the comment map too.

    Before this fix the shipped step rewrote ``tasks.md`` and stopped. Gate 4
    reads ``comments.md`` and nothing else, so the fix landed, the commit
    pushed, and the gate still counted the comment pending.
    """
    comment_map = _write_comment_map(tmp_path, API_COMMENT_IDS)
    task_list = _write_task_list(tmp_path, API_COMMENT_IDS)

    result = _run_gate_three(
        path,
        comment_map=comment_map,
        task_list=task_list,
        comment_id="124",
        terminal_status="[COMPLETE]",
    )

    assert result.returncode == 0, (
        f"{_carrier_id(path)} Gate 3 failed: exit {result.returncode}, "
        f"stdout {result.stdout!r}, stderr {result.stderr!r}"
    )
    assert _status_lines(comment_map) == [
        f"**Status**: {INITIAL_STATUS}",
        "**Status**: [COMPLETE]",
        f"**Status**: {INITIAL_STATUS}",
    ], f"{_carrier_id(path)} Gate 3 did not write exactly the targeted comment"
    task_text = task_list.read_text(encoding="utf-8")
    assert "- [x] **TASK-124**: address comment 124 [COMPLETE]" in task_text, (
        f"{_carrier_id(path)} Gate 3 did not tick and annotate the task row"
    )
    assert "- [ ] **TASK-123**:" in task_text, (
        f"{_carrier_id(path)} Gate 3 moved a sibling comment's task row"
    )


@requires_bash
@requires_grep
@pytest.mark.parametrize("path", CARRIER_PATHS, ids=_carrier_id)
def test_the_documented_workflow_reaches_zero_pending(path: Path, tmp_path: Path) -> None:
    """End to end: follow the instructions, and Gate 4 must clear.

    Three comments start at ``[ACKNOWLEDGED]``. Each is worked to a different
    terminal outcome through the carrier's own Gate 3 fence. The carrier's own
    Gate 4 derivation then runs against the resulting map. Anything short of
    ``PENDING=0`` means the documented workflow cannot finish a PR.
    """
    comment_map = _write_comment_map(tmp_path, API_COMMENT_IDS)
    task_list = _write_task_list(tmp_path, API_COMMENT_IDS)

    for comment_id, status in zip(API_COMMENT_IDS, TERMINAL_STATUSES, strict=False):
        result = _run_gate_three(
            path,
            comment_map=comment_map,
            task_list=task_list,
            comment_id=comment_id,
            terminal_status=status,
        )
        assert result.returncode == 0, (
            f"{_carrier_id(path)} Gate 3 failed for comment {comment_id}: {result.stdout!r}"
        )

    assert _grep_count(TERMINAL_PATTERN, comment_map) == len(API_COMMENT_IDS)

    gate_four = _run_derivation(
        _derivation_script(_gate_four_fence(path), comment_map, len(API_COMMENT_IDS))
    )

    assert gate_four.returncode == 0, (
        f"{_carrier_id(path)} Gate 4 blocked a fully worked comment map: "
        f"exit {gate_four.returncode}, stdout {gate_four.stdout!r}"
    )
    assert "PENDING=0" in gate_four.stdout


@requires_bash
def test_without_the_writeback_gate_four_blocks_forever(tmp_path: Path) -> None:
    """Negative control: the write-back is what lets the workflow finish.

    Take the shipped Gate 3, truncate it after the task-list verification, and
    the step is exactly what it was before this fix. Every comment is worked,
    every task is marked done, and Gate 4 still counts three pending. That is
    the fail-closed trap issue #4054 reports, reproduced against the real shell.
    """
    comment_map = _write_comment_map(tmp_path, API_COMMENT_IDS)
    task_list = _write_task_list(tmp_path, API_COMMENT_IDS)

    for comment_id in API_COMMENT_IDS:
        result = _run_gate_three(
            TEMPLATE,
            comment_map=comment_map,
            task_list=task_list,
            comment_id=comment_id,
            terminal_status="[COMPLETE]",
            with_map_writeback=False,
        )
        assert result.returncode == 0, f"pre-fix Gate 3 failed for {comment_id}"

    assert _status_lines(comment_map) == [f"**Status**: {INITIAL_STATUS}"] * len(API_COMMENT_IDS)
    assert _grep_count(TERMINAL_PATTERN, comment_map) == 0

    gate_four = _run_derivation(
        _derivation_script(_gate_four_fence(TEMPLATE), comment_map, len(API_COMMENT_IDS))
    )

    # The sliced derivation stops at the API-count invariant, so it reports the
    # count rather than exiting. Gate 4's own check right after the slice reads
    # `if [ "$PENDING" -ne 0 ]` and blocks on any nonzero value.
    assert gate_four.returncode == 0
    assert "PENDING=3" in gate_four.stdout, (
        f"pre-fix workflow left {gate_four.stdout!r}; three worked comments "
        f"must still read pending, which is the block issue #4054 reports"
    )


@requires_bash
@pytest.mark.parametrize("terminal_status", TERMINAL_STATUSES)
@requires_grep
def test_gate_three_writes_every_terminal_status(terminal_status: str, tmp_path: Path) -> None:
    """All four terminal outcomes must be writable, not just ``[COMPLETE]``.

    ``[WONTFIX]``, ``[DUPLICATE]``, and ``[DEFERRED] Refs #<issue>`` are
    terminal in the vocabulary table. A step hardcoded to ``[COMPLETE]`` forces
    a wrong status onto three of the four outcomes.
    """
    comment_map = _write_comment_map(tmp_path, ("123",))
    task_list = _write_task_list(tmp_path, ("123",))

    result = _run_gate_three(
        TEMPLATE,
        comment_map=comment_map,
        task_list=task_list,
        comment_id="123",
        terminal_status=terminal_status,
    )

    assert result.returncode == 0, f"Gate 3 refused {terminal_status!r}: {result.stdout!r}"
    assert _status_lines(comment_map) == [f"**Status**: {terminal_status}"]
    assert _grep_count(TERMINAL_PATTERN, comment_map) == 1


@requires_bash
@pytest.mark.parametrize(
    "comment_id",
    ["", "12x", "12; rm -rf /", "../../etc/passwd", "$(id)", "1 2"],
)
def test_gate_three_refuses_a_non_numeric_comment_id(comment_id: str, tmp_path: Path) -> None:
    """A comment id reaches a ``sed`` program, so it must be digits only.

    GitHub comment ids are integers. Anything else is either a corrupted
    pipeline value or an injection attempt (CWE-78), and both must block before
    the value is spliced into a sed address.
    """
    comment_map = _write_comment_map(tmp_path, ("123",))
    task_list = _write_task_list(tmp_path, ("123",))

    result = _run_gate_three(
        TEMPLATE,
        comment_map=comment_map,
        task_list=task_list,
        comment_id=comment_id,
        terminal_status="[COMPLETE]",
    )

    assert result.returncode == 1, (
        f"Gate 3 accepted a non-numeric comment id {comment_id!r}: {result.stdout!r}"
    )
    assert "[BLOCKED] COMMENT_ID is not numeric" in result.stdout
    assert _status_lines(comment_map) == [f"**Status**: {INITIAL_STATUS}"], (
        "Gate 3 mutated the comment map after rejecting the id"
    )


@requires_bash
def test_gate_three_blocks_when_the_comment_is_not_in_the_map(tmp_path: Path) -> None:
    """A write that lands nowhere must block, not report success.

    The verification is what makes the step atomic. Without it a typo in the
    comment id silently leaves the map at its starting status while the task
    list says done, which is the same split-artifact state this fix closes.
    """
    comment_map = _write_comment_map(tmp_path, ("123",))
    task_list = _write_task_list(tmp_path, ("999",))

    task_before = task_list.read_bytes()
    map_before = comment_map.read_bytes()

    result = _run_gate_three(
        TEMPLATE,
        comment_map=comment_map,
        task_list=task_list,
        comment_id="999",
        terminal_status="[COMPLETE]",
    )

    assert result.returncode == 1, f"Gate 3 cleared a write that landed nowhere: {result.stdout!r}"
    assert "[BLOCKED] Comment 999" in result.stdout

    # Atomic means both or neither. Exit code and message alone do not prove
    # it: the step used to rewrite tasks.md first and only then discover the
    # comment map had no entry to move, which left the two artifacts
    # disagreeing on a path that reported failure.
    assert task_list.read_bytes() == task_before, (
        "Gate 3 blocked but left tasks.md modified, so the two artifacts "
        "disagree on a failure path (issue #4054)"
    )
    assert comment_map.read_bytes() == map_before, "Gate 3 blocked but left comments.md modified"


@requires_bash
def test_gate_three_skips_an_absent_task_row(tmp_path: Path) -> None:
    """An immediate-reply outcome has no task row, and that is not a failure.

    Phase 6 opens a ``TASK-[id]`` only for a comment it implements. A
    ``[WONTFIX]``, ``[DUPLICATE]``, or question outcome is answered from the
    Phase 5 immediate-reply table and never gets one. A step that required the
    row would block every one of those outcomes; the comment map still has to
    move for all of them.
    """
    comment_map = _write_comment_map(tmp_path, ("123", "124"))
    task_list = _write_task_list(tmp_path, ("123",))
    task_before = task_list.read_bytes()

    result = _run_gate_three(
        TEMPLATE,
        comment_map=comment_map,
        task_list=task_list,
        comment_id="124",
        terminal_status="[WONTFIX]",
    )

    assert result.returncode == 0, (
        f"Gate 3 blocked an outcome with no task row: {result.stdout!r} {result.stderr!r}"
    )
    assert _status_lines(comment_map) == [
        f"**Status**: {INITIAL_STATUS}",
        "**Status**: [WONTFIX]",
    ], "Gate 3 did not move the comment map for a comment with no task row"
    assert task_list.read_bytes() == task_before, (
        "Gate 3 touched the task list for a comment that has no row in it"
    )


@requires_bash
def test_the_old_task_row_substitution_never_matched_the_real_template(
    tmp_path: Path,
) -> None:
    """Negative control: the step as shipped could not pass on a real task list.

    Gate 3 substituted ``s/TASK-$COMMENT_ID.*pending/`` and then verified its
    own output. The Phase 6 template renders no ``pending`` token, so the
    substitution matched nothing, the verification found nothing, and the gate
    exited 1 on a correctly worked comment.
    """
    task_list = _write_task_list(tmp_path, ("123",))
    old_step = (
        'sed -i "s/TASK-$COMMENT_ID.*pending/TASK-$COMMENT_ID ... $TERMINAL_STATUS/" "$TASK_LIST"\n'
        'grep -F "TASK-$COMMENT_ID ... $TERMINAL_STATUS" "$TASK_LIST" || exit 1\n'
    )
    script = (
        f"TASK_LIST={shlex.quote(str(task_list))}\n"
        'COMMENT_ID=123\nTERMINAL_STATUS="[COMPLETE]"\n' + old_step
    )

    result = _run_derivation(script)

    assert result.returncode == 1, (
        "the old task-row substitution passed against the real template shape; "
        "if it now matches, this control no longer proves the defect"
    )
    assert "pending" not in task_list.read_text(encoding="utf-8"), (
        "the Phase 6 task template emits no `pending` token; a fixture that "
        "adds one hides the defect this control pins"
    )


@requires_bash
@pytest.mark.parametrize(
    "terminal_status",
    ["[COMPLETE]oops", "[DEFERRED]", "[DEFERRED] Refs #", "[BOGUS]", "[ACKNOWLEDGED]", ""],
)
def test_gate_three_refuses_a_status_the_later_gates_reject(
    terminal_status: str, tmp_path: Path
) -> None:
    """A value Gate 4 counts as pending must not be written at all.

    Gate 4's terminal pattern ends at ``[[:space:]]*$``, so ``[COMPLETE]oops``
    and a bare ``[DEFERRED]`` count as pending there. Writing one would report
    success in Gate 3 and block at Phase 8 with a diagnostic that points at the
    map rather than at the command that wrote it. The guard runs before either
    write, so a rejected status leaves both artifacts untouched.
    """
    comment_map = _write_comment_map(tmp_path, ("123",))
    task_list = _write_task_list(tmp_path, ("123",))
    task_list_before = task_list.read_text(encoding="utf-8")

    result = _run_gate_three(
        TEMPLATE,
        comment_map=comment_map,
        task_list=task_list,
        comment_id="123",
        terminal_status=terminal_status,
    )

    assert result.returncode == 1, (
        f"Gate 3 wrote {terminal_status!r}, which Gate 4 counts as pending: {result.stdout!r}"
    )
    assert "[BLOCKED] TERMINAL_STATUS is not a terminal value" in result.stdout
    assert _status_lines(comment_map) == [f"**Status**: {INITIAL_STATUS}"]
    assert task_list.read_text(encoding="utf-8") == task_list_before


@pytest.mark.parametrize("path", CARRIER_PATHS, ids=_carrier_id)
def test_gate_three_screens_against_gate_fours_own_pattern(path: Path) -> None:
    """The guard must reuse the canonical terminal pattern, not a near copy.

    A guard one alternation short would refuse a status the later gates accept,
    or admit one they reject. Either way the two disagree about what done means,
    which is the split-contract failure issue #4054 names.
    """
    fence = _gate_three_fence(path)
    assert TERMINAL_STATUS_GUARD_GREP in fence, (
        f"{_carrier_id(path)} Gate 3 screens TERMINAL_STATUS with a pattern "
        f"that is not Gate 4's canonical {TERMINAL_PATTERN!r}"
    )


# Every carrier must publish the write-back, and every step that marks a
# comment addressed must route through it.


@pytest.mark.parametrize("path", CARRIER_PATHS, ids=_carrier_id)
def test_every_carrier_publishes_the_gate_three_writeback(path: Path) -> None:
    """All nine carriers, in order. Drift here is how one platform regresses."""
    fence = _gate_three_fence(path)

    offsets: list[int] = []
    for step in REQUIRED_GATE_THREE_STEPS:
        assert step in fence, (
            f"{_carrier_id(path)} Gate 3 does not publish {step!r}, so the "
            f"comment map Gate 4 counts is never updated (issue #4054)"
        )
        offsets.append(fence.index(step))

    assert offsets == sorted(offsets), (
        f"{_carrier_id(path)} Gate 3 publishes its steps out of order; the "
        f"comment-id guard, the two writes, and the two verifications must run "
        f"in that order"
    )


@pytest.mark.parametrize("path", VOCABULARY_CARRIERS, ids=_carrier_id)
def test_step_six_five_names_the_comment_map(path: Path) -> None:
    """Step 6.5 must not tell the reader to update the task list alone.

    The step shipped as ``Mark task as complete in tasks.md``. Following it
    literally is what left ``comments.md`` at its starting status.
    """
    text = path.read_text(encoding="utf-8")
    heading = "#### Step 6.5:"
    assert heading in text, f"{_carrier_id(path)} publishes no Step 6.5"

    start = text.index(heading)
    end = text.find("\n### ", start)
    section = text[start : len(text) if end == -1 else end]

    assert "comments.md" in section, (
        f"{_carrier_id(path)} Step 6.5 names only the task list; the comment "
        f"map is the artifact every later gate counts (issue #4054)"
    )
    assert "Gate 3" in section, (
        f"{_carrier_id(path)} Step 6.5 must route through Gate 3 rather than "
        f"restate the commands and drift from them"
    )


@pytest.mark.parametrize("path", VOCABULARY_CARRIERS, ids=_carrier_id)
def test_phase_five_records_its_terminal_outcomes(path: Path) -> None:
    """Won't Fix and Duplicate never reach Phase 6, so Phase 5 must record them.

    Phase 5 replies and moves on. Those comments are terminal but skip the
    implementation loop entirely, so without a write-back here they stay
    pending and block Phase 8 exactly like an unworked comment.
    """
    text = path.read_text(encoding="utf-8")
    heading = "### Phase 5: Immediate Replies"
    assert heading in text, f"{_carrier_id(path)} publishes no Phase 5"

    start = text.index(heading)
    end = text.index("### Phase 6", start)
    section = text[start:end]

    assert "comments.md" in section, (
        f"{_carrier_id(path)} Phase 5 never records a terminal status, so a "
        f"[WONTFIX] comment stays pending forever (issue #4054)"
    )
    assert "Gate 3" in section, (
        f"{_carrier_id(path)} Phase 5 must route through Gate 3 rather than "
        f"restate the commands and drift from them"
    )


@pytest.mark.parametrize("path", WORKFLOW_CARRIERS, ids=_carrier_id)
def test_workflow_reference_names_both_artifacts(path: Path) -> None:
    """The condensed workflow restates the checklist, so it carries the defect.

    Its Phase 6 read ``4. Update task list``. A reader who follows the short
    form instead of the agent prompt hits the same block. The assertion is
    scoped to that section: ``comments.md`` appears elsewhere in the file for
    unrelated reasons, so a file-wide search would pass without the fix.
    """
    text = path.read_text(encoding="utf-8")
    heading = "## Phase 6: Implementation"
    assert heading in text, f"{_carrier_id(path)} publishes no Phase 6"

    start = text.index(heading)
    section = text[start : text.index("## Phase 7", start)]

    assert "comments.md" in section, (
        f"{_carrier_id(path)} Phase 6 tells the reader to update the task list "
        f"without naming the comment map every gate counts (issue #4054)"
    )
    assert "Gate 3" in section, (
        f"{_carrier_id(path)} Phase 6 must route through Gate 3 rather than "
        f"restate the commands and drift from them"
    )
