# GraphQL PR Operations

**Statement**: Common PR review thread mutations for gh CLI

**Context**: Responding to PR review comments

**Atomicity**: 95%

**Impact**: 9/10

## Reply to Review Thread

```bash
gh api graphql \
  -f query='mutation($id: ID!, $body: String!) { addPullRequestReviewThreadReply(input: {pullRequestReviewThreadId: $id, body: $body}) { comment { id } } }' \
  -f id="PRRT_kwDOAbCdEf4GHIJKL" \
  -f body="Thanks for the review! Fixed in commit abc123."
```

## Resolve Review Thread

```bash
gh api graphql \
  -f query='mutation($id: ID!) { resolveReviewThread(input: {threadId: $id}) { thread { isResolved } } }' \
  -f id="PRRT_kwDOAbCdEf4GHIJKL"
```

## Unresolve Review Thread

```bash
gh api graphql \
  -f query='mutation($id: ID!) { unresolveReviewThread(input: {threadId: $id}) { thread { isResolved } } }' \
  -f id="PRRT_kwDOAbCdEf4GHIJKL"
```

## Add Reaction

```bash
gh api graphql \
  -f query='mutation($id: ID!, $content: ReactionContent!) { addReaction(input: {subjectId: $id, content: $content}) { reaction { id } } }' \
  -f id="IC_kwDOAbCdEf4GHIJKL" \
  -f content="THUMBS_UP"
```

**Reaction Values**: `THUMBS_UP`, `THUMBS_DOWN`, `LAUGH`, `HOORAY`, `CONFUSED`, `HEART`, `ROCKET`, `EYES`
