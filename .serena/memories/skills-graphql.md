# GraphQL Skills

**Created**: 2025-12-20
**Source**: PR #212 retrospective

## Skill-GraphQL-001: Mutation Single-Line Format Requirement

**Statement**: Format GraphQL mutations as single-line strings in `gh api graphql -f query='...'`

**Context**: When calling GraphQL mutations via gh CLI

**Evidence**: PR #212 - Multiple retry iterations until single-line format discovered

**Atomicity**: 97%

**Tag**: helpful (prevents syntax errors)

**Impact**: 8/10 (saves retry iterations)

**Created**: 2025-12-20

**Problem**:

```bash
# WRONG - Multi-line formatted mutation causes syntax errors
gh api graphql -f query='
mutation($id: ID!) {
  resolveReviewThread(input: {threadId: $id}) {
    thread { isResolved }
  }
}'
```

**Solution**:

```bash
# CORRECT - Single-line format
gh api graphql -f query='mutation($id: ID!) { resolveReviewThread(input: {threadId: $id}) { thread { isResolved } } }'
```

**Why It Matters**:

The `gh api graphql` command requires the `-f query='...'` parameter to be a single-line string. Multi-line formatted GraphQL (while valid GraphQL syntax) causes parsing errors when passed through bash/PowerShell command-line arguments.

**Pattern**:

```bash
# Template for GraphQL mutations via gh CLI
gh api graphql -f query='mutation($var: Type!) { operation(input: {field: $var}) { result { field } } }' -f var="value"

# Example: Reply to PR review thread
gh api graphql -f query='mutation($id: ID!, $body: String!) { addPullRequestReviewThreadReply(input: {pullRequestReviewThreadId: $id, body: $body}) { comment { id } } }' -f id="PRRT_xxx" -f body="Reply text"

# Example: Resolve PR review thread
gh api graphql -f query='mutation($id: ID!) { resolveReviewThread(input: {threadId: $id}) { thread { isResolved } } }' -f id="PRRT_xxx"
```

**Anti-Pattern**:

```bash
# Unsafe - multi-line format
gh api graphql -f query='
mutation($id: ID!) {
  resolveReviewThread(input: {
    threadId: $id
  }) {
    thread {
      isResolved
    }
  }
}'
```

**Validation**: 1 (PR #212)

---

## Common GraphQL Mutation Patterns

### Pull Request Review Threads

#### Reply to Review Thread

```bash
gh api graphql \
  -f query='mutation($id: ID!, $body: String!) { addPullRequestReviewThreadReply(input: {pullRequestReviewThreadId: $id, body: $body}) { comment { id } } }' \
  -f id="PRRT_kwDOAbCdEf4GHIJKL" \
  -f body="Thanks for the review! Fixed in commit abc123."
```

#### Resolve Review Thread

```bash
gh api graphql \
  -f query='mutation($id: ID!) { resolveReviewThread(input: {threadId: $id}) { thread { isResolved } } }' \
  -f id="PRRT_kwDOAbCdEf4GHIJKL"
```

#### Unresolve Review Thread

```bash
gh api graphql \
  -f query='mutation($id: ID!) { unresolveReviewThread(input: {threadId: $id}) { thread { isResolved } } }' \
  -f id="PRRT_kwDOAbCdEf4GHIJKL"
```

### Issue Comments

#### Add Comment to Issue/PR

```bash
gh api graphql \
  -f query='mutation($id: ID!, $body: String!) { addComment(input: {subjectId: $id, body: $body}) { commentEdge { node { id } } } }' \
  -f id="I_kwDOAbCdEf4GHIJKL" \
  -f body="Comment text"
```

### Pull Request Reactions

#### Add Reaction to Comment

```bash
gh api graphql \
  -f query='mutation($id: ID!, $content: ReactionContent!) { addReaction(input: {subjectId: $id, content: $content}) { reaction { id } } }' \
  -f id="IC_kwDOAbCdEf4GHIJKL" \
  -f content="THUMBS_UP"
```

**Reaction Content Values**: `THUMBS_UP`, `THUMBS_DOWN`, `LAUGH`, `HOORAY`, `CONFUSED`, `HEART`, `ROCKET`, `EYES`

---

## GraphQL vs REST API Decision Matrix

| Use Case | GraphQL | REST API | Rationale |
|----------|---------|----------|-----------|
| Reply to review thread | ✅ | ✅ | GraphQL if you have thread ID (PRRT_xxx), REST if you have comment ID (numeric) |
| Resolve review thread | ✅ | ❌ | GraphQL only (no REST endpoint) |
| Add reaction | ✅ | ✅ | REST simpler: `gh api repos/OWNER/REPO/issues/comments/ID/reactions -X POST -f content=eyes` |
| Batch operations | ✅ | ❌ | GraphQL supports multiple mutations in one call |
| Query with nested data | ✅ | ❌ | GraphQL avoids multiple REST calls |

---

## Troubleshooting

### Syntax Errors

**Problem**: `Parse error on "mutation" (error)`

**Cause**: Multi-line formatted query

**Fix**: Convert to single-line format

### Variable Type Errors

**Problem**: `Variable $id of type String! was provided invalid value`

**Cause**: Variable type mismatch (e.g., passing string when ID expected)

**Fix**: Verify variable types in mutation signature

### Authentication Errors

**Problem**: `Your token has not been granted the required scopes`

**Cause**: Insufficient token permissions

**Fix**: Ensure token has required scopes:

- `repo` for repository operations
- `write:discussion` for comments/reactions

---

## Related Skills

- Skill-PR-004: Review reply endpoint (REST alternative)
- Skill-PR-Comment-001: Eyes reaction acknowledgment

## References

- PR #212: GraphQL mutation syntax discovery
- [GitHub GraphQL API Documentation](https://docs.github.com/en/graphql)
- [GitHub GraphQL Explorer](https://docs.github.com/en/graphql/overview/explorer)
