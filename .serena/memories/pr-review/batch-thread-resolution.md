# Batch Thread Resolution (Existing Capability)

## Tools Already Available
- `resolve_pr_review_thread.py --pull-request N --all` resolves all unresolved threads in one call
- `add_pr_review_thread_reply.py --thread-id PRRT_xxx --body "text" --resolve` replies and resolves atomically
- GraphQL batch mutation can resolve multiple threads in 1 API call

## Decision
Evaluated as skill candidate from PR #1589 retrospective. Verdict: DROP. No new tooling needed. Existing scripts cover the full workflow.