# PR Review Skills

Collection of proven strategies for GitHub pull request review and merge workflows in rjmurillo/ai-agents.

---

## Skill-PR-Review-001: Conversation Resolution Requirement

**Statement**: Before merging a PR in rjmurillo/ai-agents, ALL review conversations MUST be resolved. Unresolved threads block the merge due to branch protection rules.

**Context**: GitHub PR review and merge workflow

**Evidence**: Maintainer guidance from 2025-12-20 session - branch protection rules require conversation resolution before merge.

**Atomicity**: 95%

**Tag**: helpful

**Impact**: 9/10

**Created**: 2025-12-19

**Validated**: 3

**Pattern**:

```bash
# Check for unresolved conversations before attempting merge
# NOTE: gh pr view does NOT support reviewThreads - must use GraphQL API
gh api graphql -f query='
query($owner: String!, $repo: String!, $number: Int!) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $number) {
      reviewThreads(first: 100) {
        nodes {
          id
          isResolved
          path
          line
          comments(first: 3) {
            nodes { id body author { login } }
          }
        }
      }
    }
  }
}' -f owner=OWNER -f repo=REPO -F number=PR_NUMBER
```

**Invalid Pattern** (does not work):

```bash
# This fails - reviewThreads is not a valid field for gh pr view
gh pr view <PR_NUMBER> --json reviewThreads  # ERROR: Unknown JSON field
```

**Anti-Pattern**:

- Attempting to merge with unresolved conversations → merge will be blocked
- Using `--admin` flag to bypass → violates repository policy
- Pushing fixes without replying/resolving → threads remain unresolved

---

## Skill-PR-Review-002: Conversation Resolution Protocol

**Statement**: When addressing PR review feedback, ALWAYS reply to the conversation with resolution details, then mark the thread as resolved. Pushing fixes alone does NOT resolve conversations.

**Context**: GitHub PR review workflow - responding to reviewer comments

**Evidence**: Maintainer guidance from 2025-12-20 session - "each conversation needs a reply with either 1) the fix and link to commit SHA, or 2) explanation why not fixing, or 3) action for commenter to take"

**Atomicity**: 98%

**Tag**: critical

**Impact**: 10/10

**Created**: 2025-12-20

**Validated**: 1

**Protocol**:

For each unresolved conversation, reply with ONE of:

1. **Fix applied**: Link to commit SHA that addresses the feedback
   ```
   Fixed in commit abc1234. [Brief description of change]
   ```

2. **Won't fix with explanation**: Clear rationale why the suggestion wasn't applied
   ```
   Won't fix: [Detailed explanation why this approach was chosen instead]
   ```

3. **Action required from reviewer**: @ mention the reviewer with specific ask
   ```
   @reviewer-username Could you clarify [specific question]? I need more context to address this.
   ```

**After replying, RESOLVE the thread** using:

```bash
# Reply to the thread
gh api graphql -f query='
mutation($threadId: ID!, $body: String!) {
  addPullRequestReviewThreadReply(input: {pullRequestReviewThreadId: $threadId, body: $body}) {
    comment { id }
  }
}' -f threadId=THREAD_ID -f body="REPLY_TEXT"

# Resolve the thread
gh api graphql -f query='
mutation($threadId: ID!) {
  resolveReviewThread(input: {threadId: $threadId}) {
    thread { isResolved }
  }
}' -f threadId=THREAD_ID
```

**Common Mistake**:

- Pushing commit with fix but NOT replying to thread → thread stays unresolved
- Replying but NOT resolving → thread stays unresolved (blocking merge)
- Only resolving without reply → reviewer doesn't know how feedback was addressed

**Notes**:

- This is the complete workflow: Code fix → Reply → Resolve
- Thread IDs are obtained via GraphQL query (see Skill-PR-Review-001)
- Resolving requires the thread ID, not the comment ID

---

## Related Skills

- Skill-PR-Review-001: Conversation Resolution Requirement
- Skill-PR-Review-002: Conversation Resolution Protocol
