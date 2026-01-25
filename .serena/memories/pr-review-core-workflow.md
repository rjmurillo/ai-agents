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

## Skill-PR-Review-004: Thread Resolution Protocol

**Statement**: Review comment replies do NOT automatically resolve threads. Must execute separate GraphQL `resolveReviewThread` mutation after replying.

**Atomicity**: 95% | **Impact**: 10/10 | **Tag**: critical | **Validated**: 2

**Pattern** (2-step process):

1. Reply via REST or GraphQL
2. Resolve thread (separate GraphQL mutation):

```bash
gh api graphql -f query='mutation($id: ID!) { resolveReviewThread(input: {threadId: $id}) { thread { isResolved } } }' -f id="PRRT_xxx"
```

**Verification**:

```bash
gh api graphql -f query='query { repository(owner: "owner", name: "repo") { pullRequest(number: N) { reviewThreads(first: 100) { nodes { id isResolved } } } } }' --jq '.data.repository.pullRequest.reviewThreads.nodes | map(select(.isResolved == false)) | length'
```

## Skill-PR-Review-005: Batch Thread Resolution Efficiency

**Statement**: Use GraphQL mutation aliases to resolve multiple threads in single API call. Reduces API calls by N-1.

**Atomicity**: 93% | **Impact**: 6/10 | **Validated**: 1

**Pattern**:

```graphql
mutation {
  t1: resolveReviewThread(input: {threadId: "PRRT_xxx"}) { thread { id isResolved } }
  t2: resolveReviewThread(input: {threadId: "PRRT_yyy"}) { thread { id isResolved } }
  # ... add more as needed
}
```

**Benefits**: 1 API call for N threads (vs N calls), atomic operation

**When to use**: 2+ threads to resolve

## Skill-PR-Review-006: PR Merge State Verification

**Statement**: Verify PR merge state via GraphQL before starting review. `gh pr view` may return stale "OPEN" for recently merged PRs.

**Atomicity**: 92% | **Impact**: 7/10 | **Validated**: 1

**Pattern** (first step in pr-review/pr-comment-responder workflows):

```bash
gh api graphql -f query='query { repository(owner: "owner", name: "repo") { pullRequest(number: N) { state merged mergedAt } } }' --jq '.data.repository.pullRequest | {state, merged, mergedAt}'
```

**Anti-pattern**: Relying on `gh pr view --json state` → may return stale data

**If merged=true**: Skip review work

## Related

- [pr-156-review-findings](pr-156-review-findings.md)
- [pr-320c2b3-refactoring-analysis](pr-320c2b3-refactoring-analysis.md)
- [pr-52-retrospective-learnings](pr-52-retrospective-learnings.md)
- [pr-52-symlink-retrospective](pr-52-symlink-retrospective.md)
- [pr-753-remediation-learnings](pr-753-remediation-learnings.md)
