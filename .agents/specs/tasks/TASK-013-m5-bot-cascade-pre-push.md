---
type: task
id: TASK-013
title: M5 bot-cascade pre-push warning
status: done
priority: P1
complexity: S
estimate: 3.5h
related:
  - REQ-013
  - DESIGN-013
blocked_by: []
blocks: []
created: 2026-05-10
updated: 2026-05-11
---

# TASK-013: M5 Bot-Cascade Pre-Push Warning

## Design Context

DESIGN-013 specifies Phase 5c added to `.githooks/pre-push` between Phase 5b (drift detection) and Phase 6 (Summary). The phase emits one of `record_skip`, `record_warn`, or `record_pass` based on:

- whether a PR exists for the current branch,
- whether the unresolved-thread snapshot is trustworthy (`success == true` AND `fetched_pages_complete == true`),
- the unresolved-thread count,
- the age of the most recent bot review.

Warn-only. Never invokes `record_fail`. Mirrors the existing Phase 5b drift check in shape and integration.

## Scope

In scope:

- Add Phase 5c to `.githooks/pre-push`.
- Add structural verification tests in `tests/hooks/test_bot_cascade_warning.py` covering REQ-013-01..05.
- Spec artifacts: REQ-011, DESIGN-013, TASK-011.
- Self-apply gate against the milestone PR (REQ-013-06).

Out of scope:

- Per-bot tracking (DESIGN-013 trade-off 3 defers this).
- 120-second threshold tuning beyond initial selection (DESIGN-013 trade-off 2; deferred-tunable).
- Refactor of the hook into sourceable functions for unit-test isolation (deferred; structural verification suffices for this milestone).
- Fixes to `get_unresolved_review_threads.py` thread-shape inconsistency (Issue #2012; out of REQ-011 scope).

## Acceptance Criteria

Maps directly to REQ-013-01..06:

- [x] REQ-013-01: unresolved threads emit `record_warn` (not `record_fail`).
- [x] REQ-013-02: incomplete snapshot (`fetched_pages_complete=false` OR `success=false`) emits `record_skip`, never `record_pass`.
- [x] REQ-013-03: recent bot review under 120s emits `record_warn`.
- [x] REQ-013-04: `gh api ... reviews` failure emits `record_skip` with explicit exit code; no `|| true` fall-through.
- [x] REQ-013-05: structural tests pin each AC; `bash -n` clean; `record_skip` / `record_warn` / `record_pass` each have at least one call site.
- [x] REQ-013-06: self-apply gate exercised against PR #2011; runtime evidence in PR description.

## Objective

Implement REQ-011 via TDD-first sequence per `.claude/commands/build.md`. Add Phase 5c to `.githooks/pre-push`. Cover all four bot-cascade conditions. Self-apply gate verified before final commit.

## Subtasks

### TASK-013-01: Capture structural test foundation

**Files**:
- `tests/hooks/test_bot_cascade_warning.py` (new test file)
- `tests/hooks/__init__.py` if absent

**AC**: REQ-013-05.

**Done definition**: Test file uses the same structural verification pattern as `tests/hooks/test_drift_check.py` (Phase 5b). Each test scopes assertions to the Phase 5c block via a regex with a lookahead to the next phase header. Original draft specified PATH-stubbed fixtures; replaced with structural verification per DESIGN-013 revised test strategy.

**Hours**: 30 minutes.

### TASK-013-02: TDD red phase

**Files**:
- `tests/hooks/test_bot_cascade_warning.py`

**AC**: REQ-013-05 (test file exists), REQ-013-01..04 (one test per AC).

**Done definition**:
- One test per AC with docstring citing the AC identifier.
- All tests FAIL on a hook without Phase 5c (because the Phase 5c block does not exist yet).
- Commit with subject `test(hooks): pin REQ-011 ACs via structural verification (TDD red)`.

**Hours**: 1 hour 15 minutes.

### TASK-013-03: TDD green phase

**Files**:
- `.githooks/pre-push` (extend with Phase 5c block after Phase 5b)

**AC**: REQ-013-01, REQ-013-02, REQ-013-03, REQ-013-04.

**Done definition**:
- Phase 5c block in `.githooks/pre-push` after the existing Phase 5b drift check.
- All tests from TASK-013-02 pass.
- argv-vector subprocess only (no shell concatenation).
- No `|| true` on the `gh api ... reviews` call.
- No `|| true` on the `gh pr view` call (PR #2011 review feedback generalized REQ-013-04 to all gh calls in Phase 5c).
- Both `success == true` and `fetched_pages_complete == true` required before trusting the unresolved count.
- Commit with subject `feat(hooks): bot-cascade pre-push warning Phase 5c (REQ-013-01..04)`.

**Hours**: 1 hour.

### TASK-013-04: Self-apply gate

**AC**: REQ-013-06.

**Done definition**:
- Implementer runs `.githooks/pre-push` against the current branch before final commit.
- Output captured in PR description.
- If unresolved threads exist on the PR, the hook emits `record_warn` for them.
- Commit with subject `chore(hooks): self-apply gate verification (TASK-013-04)`.

**Hours**: 30 minutes.

## Total Effort

3 hours 15 minutes (under 3.5h Q4 wedge estimate).

## Files Affected

| File | Action | Description |
|---|---|---|
| `tests/hooks/test_bot_cascade_warning.py` | Create | One test per AC; structural verification on Phase 5c block |
| `.githooks/pre-push` | Modify | Add Phase 5c block after Phase 5b |
| `.agents/specs/requirements/REQ-013-m5-bot-cascade-pre-push.md` | Create | Acceptance criteria |
| `.agents/specs/design/DESIGN-013-m5-bot-cascade-pre-push.md` | Create | Architecture, test strategy |
| `.agents/specs/tasks/TASK-013-m5-bot-cascade-pre-push.md` | Create | This file |
| `.agents/sessions/2026-05-11-session-1832.json` | Create | Session log |
| `.serena/memories/implementation/implementation-009-req011-tdd-first-shipment.md` | Create | TDD lessons |

## References

- REQ-011 (acceptance criteria).
- DESIGN-013 (architecture, test strategy).
- `.claude/commands/build.md` (TDD-first sequence).
- `.serena/memories/implementation/implementation-009-req011-tdd-first-shipment.md`.
- Issue #2012 (downstream script-shape work, out of REQ-011 scope).
