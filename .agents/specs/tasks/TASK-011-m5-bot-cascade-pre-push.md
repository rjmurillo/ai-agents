---
type: task
id: TASK-011
title: M5 bot-cascade pre-push warning
status: todo
priority: P1
complexity: S
estimate: 3.5h
related:
  - REQ-011
  - DESIGN-011
blocked_by: []
blocks: []
created: 2026-05-10
updated: 2026-05-10
---

# TASK-011: M5 Bot-Cascade Pre-Push Warning

## Objective

Implement REQ-011 via TDD-first sequence per `.claude/commands/build.md`. Add Phase 5c to `.githooks/pre-push`. Cover all four bot-cascade conditions. Self-apply gate verified before final commit.

## Subtasks

### TASK-011-01: Capture stub fixtures

**Files**:
- `tests/hooks/fixtures/gh_pr_view_pr_2004.json` (real captured)
- `tests/hooks/fixtures/get_unresolved_unresolved_count_3.json` (synthesized to match captured schema)
- `tests/hooks/fixtures/get_unresolved_incomplete.json` (synthesized)
- `tests/hooks/fixtures/gh_api_reviews_recent.json` (synthesized to match captured schema)
- `tests/hooks/fixtures/gh_api_reviews_old.json` (synthesized)
- `tests/hooks/fixtures/gh_api_reviews_empty.json` (synthesized)

**AC**: REQ-011-05.

**Done definition**: All fixture files exist with shapes matching captured real output.

**Hours**: 30 minutes.

### TASK-011-02: TDD red phase

**Files**:
- `tests/hooks/test_bot_cascade_warning.py` (new test file)
- `tests/hooks/__init__.py` if absent

**AC**: REQ-011-05 (test file exists), REQ-011-01..04 (one test per AC).

**Done definition**:
- One test per AC with docstring citing the AC identifier.
- All tests FAIL (because Phase 5c is not yet implemented).
- Tests stub subprocess via PATH override or environment-variable injection.
- Commit with subject `test(hooks): pin REQ-011 ACs via stubbed PR contexts (TDD red)`.

**Hours**: 1 hour 15 minutes.

### TASK-011-03: TDD green phase

**Files**:
- `.githooks/pre-push` (extend with Phase 5c block after Phase 5b)

**AC**: REQ-011-01, REQ-011-02, REQ-011-03, REQ-011-04.

**Done definition**:
- Phase 5c block in `.githooks/pre-push` after the existing Phase 5b drift check.
- All 8 tests from TASK-011-02 pass.
- argv-vector subprocess only (no shell concatenation).
- No `|| true` on the `gh api ... reviews` call.
- Commit with subject `feat(hooks): bot-cascade pre-push warning Phase 5c (REQ-011-01..04)`.

**Hours**: 1 hour.

### TASK-011-04: Self-apply gate

**AC**: REQ-011-06.

**Done definition**:
- Implementer runs `.githooks/pre-push` against the current branch before final commit.
- Output captured in PR description.
- If unresolved threads exist on the PR, the hook emits `record_warn` for them.
- Commit with subject `chore(hooks): self-apply gate verification (TASK-011-04)`.

**Hours**: 30 minutes.

## Total Effort

3 hours 15 minutes (under 3.5h Q4 wedge estimate).

## Files Affected

| File | Action | Description |
|---|---|---|
| `tests/hooks/fixtures/*.json` | Create | Fixture files matching real captured schema |
| `tests/hooks/test_bot_cascade_warning.py` | Create | One test per AC |
| `.githooks/pre-push` | Modify | Add Phase 5c block after Phase 5b |

## References

- REQ-011 (acceptance criteria)
- DESIGN-011 (architecture, test strategy)
- `.claude/commands/build.md` (TDD-first sequence)
- `.serena/memories/implementation/implementation-007-pr1989-recursive-failure-learnings.md`
