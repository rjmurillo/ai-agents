# Skill-Tracking-001: Artifact Status Atomic Update

**Statement**: Update artifact status atomically with fix application

**Context**: After any code fix is committed

**Trigger**: After implementer commits fix, before API calls (post comment, resolve thread)

**Action**: Update tracking file (tasks.md) to mark task COMPLETE before proceeding

**Evidence**: Git diff shows both fix and artifact update in same commit or sequential commits

**Anti-pattern**: Committing fix without updating task status

**Atomicity**: 95%

**Tag**: critical

**Impact**: 10/10

**Created**: 2025-12-20

**Validated**: 1 (PR #147 - Task A-001 completed but tasks.md not updated until session end)

**Category**: Tracking

**Source**: PR #147 retrospective analysis (2025-12-20-pr-147-comment-2637248710-failure.md)

## Pattern

```markdown
# CORRECT: Artifact update BEFORE API calls

1. Commit fix (code change)
2. Edit .agents/planning/tasks.md - mark task COMPLETE
3. Post reply to GitHub (API call)
4. Resolve thread (API call)

# INCORRECT: Artifact update at session end

1. Commit fix
2. Post reply (API call)
3. Resolve thread (API call)
... work continues ...
N. Update tasks.md at session end (STALE)
```

## Verification

Before any GitHub API state change:

```bash
# Check artifact reflects current state
grep "A-001" .agents/planning/tasks.md
# Should show [ ] -> [x] transition
```

## Related Skills

- Skill-Artifacts-005: Synchronize artifact state with every external state change
- Skill-Verification-003: Verify artifact state matches API state using diff before phase transitions
- Skill-PR-Comment-002: Session log tracks 'NEW this session' separately from 'DONE prior sessions'
