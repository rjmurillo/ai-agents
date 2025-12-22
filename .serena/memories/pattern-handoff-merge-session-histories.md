# Pattern: HANDOFF.md Session History Merge

Category: Merge Conflict Resolution
Source: PR #201 merge conflict incident (2025-12-21)
Atomicity: 92%

## Summary

When resolving HANDOFF.md merge conflicts involving session history tables, MERGE both branches' sessions chronologically rather than replacing one with the other.

## Trigger

- Merge conflict in `.agents/HANDOFF.md`
- Conflict markers in "Session History" table section
- Feature branch and main have different session entries

## Anti-Pattern (WRONG)

Discarding feature branch session history by keeping only main's sessions:

```markdown
<<<<<<< HEAD
| Session 57-PR201 | 2025-12-21 | PR Review | #201 | ... |
| Session 56-PR201 | 2025-12-21 | PR Review | #201 | ... |
=======
| Session 61 | 2025-12-21 | PR Response | #223 | ... |
| Session 60 | 2025-12-21 | Follow-Up | #53 | ... |
>>>>>>> origin/main

# WRONG: Taking only main's sessions, losing PR #201 work history
```

## Correct Pattern

Merge ALL sessions from both branches in chronological order (highest session number first):

```markdown
| Session 61 | 2025-12-21 | PR Response | #223 | ... |
| Session 60 | 2025-12-21 | Follow-Up | #53 | ... |
| Session 59 | 2025-12-21 | Merge Resolution | #53 | ... |
| Session 58 | 2025-12-21 | Thread Resolution | #53 | ... |
| Session 57 | 2025-12-21 | PR Review Response | #222 | ... |
| Session 57-PR201 | 2025-12-21 | PR Review | #201 | ... |  # Parallel work preserved
| Session 56 | 2025-12-21 | Retrospective | #222 | ... |
| Session 56-PR201 | 2025-12-21 | PR Review | #201 | ... |  # Parallel work preserved
```

## Resolution Steps

1. **Identify all sessions** from both HEAD and incoming branch
2. **Combine into single list** preserving all unique entries
3. **Sort by session number** (descending, most recent first)
4. **Preserve parallel sessions** with same number but different PR suffixes
5. **Expand table size** if needed (e.g., "Last 5" to "Last 10") to capture parallel work

## Rationale

- HANDOFF.md tracks project-wide context across all work streams
- Feature branches represent parallel development that must be preserved
- Discarding feature branch sessions loses important project history
- Session numbers can overlap when multiple worktrees are active simultaneously

## Evidence

- PR #201: Initial merge discarded PR #201 sessions, user corrected
- Commit `1127745`: Fixed merge to include all sessions from both branches

## Related

- Skill-Workflow-011: Merge session histories chronologically
- skills-workflow memory: Session management patterns
