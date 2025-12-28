# Skill-PR-008: Session State Continuity Check

**Statement**: Check for existing PR comment session state before starting new work.

**Context**: PR comment responder workflow initialization

**Evidence**: Session 87 PR 354 - Prevented re-processing already handled comments by checking for existing session directory.

**Atomicity**: 75% | **Impact**: 8/10

## Pattern

Before processing PR comments, check if session state exists:

```bash
SESSION_DIR=".agents/pr-comments/PR-[number]"

if [ -d "$SESSION_DIR" ]; then
  # Load existing state
  # Filter for NEW comments only (not already in comments.md)
  # Skip to verification if no new comments
fi
```

## Session State Files

| File | Purpose |
|------|---------|
| `comments.md` | Comment map with status tracking |
| `tasks.md` | Prioritized task list |
| `session-summary.md` | Session outcomes |

## Benefits

1. **Token efficiency**: Avoid re-analyzing already triaged comments
2. **Time savings**: Skip to verification if nothing new
3. **State preservation**: Continue from previous session checkpoint

## Anti-Pattern

```bash
# WRONG: Always fetch all comments and process from scratch
gh pr view --json comments | jq ...
```

## Related

- **ENABLES**: Incremental PR comment handling across sessions
- **BLOCKS**: Duplicate work on already addressed comments
