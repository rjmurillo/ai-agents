# Skill-Artifacts-005: Synchronize Artifact State

**Statement**: Synchronize artifact state with every external state change

**Context**: After any API call that changes state (post comment, resolve thread, add reaction)

**Trigger**: Immediately after successful API call that modifies GitHub state

**Action**: Update corresponding artifact file to reflect new state

**Evidence**: Artifact file shows current state, not stale state

**Anti-pattern**: API success without artifact update

**Atomicity**: 94%

**Tag**: critical

**Impact**: 9/10

**Created**: 2025-12-20

**Validated**: 1 (PR #147 - Thread resolved via GraphQL but tasks.md not updated)

**Category**: Artifacts

**Source**: PR #147 retrospective analysis (2025-12-20-pr-147-comment-2637248710-failure.md)

## Synchronization Pattern

```bash
# CORRECT: Artifact update IMMEDIATELY after API call

# 1. API Call
gh api graphql -f query='mutation($id: ID!) { resolveReviewThread(input: {threadId: $id}) { thread { isResolved } } }' -f id="PRRT_xxx"

# 2. Verify API success
if [ $? -eq 0 ]; then
  # 3. Update artifact IMMEDIATELY
  # Edit .agents/planning/tasks.md - mark task [x]
  # Edit session log - record state change
fi

# INCORRECT: Batch artifact updates at end
# 1. API call
# 2. Another API call
# 3. More API calls
# ... batch update at session end (STALE)
```

## State Change Triggers

Update artifacts after these API calls:

| API Call | Artifact | Update |
|----------|----------|--------|
| `gh api .../reactions -f content="eyes"` | tasks.md | Mark acknowledgment complete |
| `gh api .../comments -F in_reply_to=ID` | tasks.md | Mark reply posted |
| `resolveReviewThread` | tasks.md | Mark task complete |
| `gh pr merge` | HANDOFF.md | Update PR status |

## Verification

Before phase transition:

```bash
# Check artifact reflects latest API state
LATEST_COMMIT=$(git log -1 --format="%H" .agents/planning/tasks.md)
LATEST_API_CALL=$(git log -1 --grep="resolve thread" --format="%H")

# Artifact commit should be >= API call commit
```

## Related Skills

- Skill-Tracking-001: Update artifact status atomically with fix application
- Skill-Verification-003: Verify artifact state matches API state using diff
- Skill-PR-Comment-003: API Verification Before Phase Completion
