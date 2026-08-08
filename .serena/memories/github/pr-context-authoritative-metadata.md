# Authoritative PR context metadata

GitHub PR context has two distinct response shapes.

- `gh pr view --json statusCheckRollup` returns a list of `CheckRun` and `StatusContext` objects. It may return `null` when no rollup exists. Treat `null` as zero checks, but treat a missing requested key or malformed record as an external error.
- Review-thread counts require GraphQL `pullRequest.reviewThreads(first: 100, after: $cursor)`. Request `id` and `isResolved`, paginate every page, omit the cursor variable on the first request, and compare returned node count with `totalCount` before declaring the count complete.
- `PullRequestReviewThread` does not expose a `url` field in GitHub's GraphQL schema.

Evidence: issue #3912 implementation and live PR #4733 on 2026-08-08 returned 144 status records and 16 of 16 review threads, all unresolved.