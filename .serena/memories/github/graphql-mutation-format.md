# Skill-GraphQL-001: Mutation Single-Line Format

**Statement**: Format GraphQL mutations as single-line strings in `gh api graphql -f query='...'`

**Context**: When calling GraphQL mutations via gh CLI

**Evidence**: PR #212 - Multiple retry iterations until single-line format discovered

**Atomicity**: 97%

**Impact**: 8/10

## Problem

```bash
# WRONG - Multi-line formatted mutation causes syntax errors
gh api graphql -f query='
mutation($id: ID!) {
  resolveReviewThread(input: {threadId: $id}) {
    thread { isResolved }
  }
}'
```

## Solution

```bash
# CORRECT - Single-line format
gh api graphql -f query='mutation($id: ID!) { resolveReviewThread(input: {threadId: $id}) { thread { isResolved } } }' -f id="PRRT_xxx"
```

## Why

The `gh api graphql` command requires `-f query='...'` to be single-line. Multi-line GraphQL causes parsing errors through bash/PowerShell.

## Related

- [graphql-pr-operations](graphql-pr-operations.md)
- [graphql-troubleshooting](graphql-troubleshooting.md)
- [graphql-vs-rest](graphql-vs-rest.md)
