# PR Review: Core Workflow

## Skill-PR-Review-001: Conversation Resolution Requirement

**Statement**: Before merging, ALL review conversations MUST be resolved. Unresolved threads block merge due to branch protection.

**Atomicity**: 95% | **Impact**: 9/10

**Query unresolved threads** (GraphQL only - `gh pr view` doesn't support reviewThreads):

```bash
gh api graphql -f query='query($owner: String!, $repo: String!, $number: Int!) { repository(owner: $owner, name: $repo) { pullRequest(number: $number) { reviewThreads(first: 100) { nodes { id isResolved path comments(first: 3) { nodes { id body author { login } } } } } } } }' -f owner=OWNER -f repo=REPO -F number=PR_NUMBER
```

## Skill-PR-Review-002: Conversation Resolution Protocol

**Statement**: Reply with resolution details, THEN mark resolved. Pushing fixes alone does NOT resolve.

**Atomicity**: 98% | **Impact**: 10/10 | **Tag**: critical

**Protocol** - Reply with ONE of:

1. **Fix applied**: `Fixed in commit abc1234. [Brief description]`
2. **Won't fix**: `Won't fix: [Rationale for different approach]`
3. **Action required**: `@reviewer Could you clarify [question]?`

**Then resolve**:

```bash
# Reply to thread
gh api graphql -f query='mutation($id: ID!, $body: String!) { addPullRequestReviewThreadReply(input: {pullRequestReviewThreadId: $id, body: $body}) { comment { id } } }' -f id="PRRT_xxx" -f body="Reply"

# Resolve thread
gh api graphql -f query='mutation($id: ID!) { resolveReviewThread(input: {threadId: $id}) { thread { isResolved } } }' -f id="PRRT_xxx"
```

## Skill-PR-Review-003: API Selection (REST vs GraphQL)

**Statement**: REST for simple replies with comment IDs; GraphQL for thread resolution or thread IDs.

| ID Type | Format | API |
|---------|--------|-----|
| Comment ID | Numeric `2616639895` | REST `in_reply_to` |
| Thread ID | `PRRT_kwDO...` | GraphQL mutations |

| Need | Use |
|------|-----|
| Simple reply, have comment ID | REST |
| Need to resolve thread | GraphQL (only option) |
| Have thread ID only | GraphQL |
