# PR-Autofix Lease Renewal Comment Spam

## Statement

`pr_autofix_lease.py`'s self-renew path POSTs a brand-new `PR-AUTOFIX-LEASE`
marker comment on every `renew` call with no throttle against its own
15-minute TTL. A caller polling far tighter than the TTL requires turns this
into hundreds of PR comments with zero code progress, burying real review
signal. Confirmed live on PR #5078: ~514 of 523 comments were lease-renewal
spam from a session renewing every 6-20 seconds, continuously, for 33+ hours,
while HEAD never moved. Fixed in issue #5160 / commit `a1617fd`: a confirmed
self-renew now skips the write when the held lease still has more than 5
minutes of its TTL left, returning `ACT`/`self-renew-noop` instead of posting.
Does not change ADR-076's immutable-claims storage model.

The calling loop that was polling this tightly on PR #5078 was not found in
this session: `pr_autofix_lease.py` itself has no internal polling (each CLI
invocation is one-shot), so the tight cadence originates in an external
wrapper/session not identified. `mcp__Claude_Code_Remote__list_sessions`
showed no session whose id matched the lease comments' embedded session
strings (`copilot-pr5078-...`), and no GitHub Actions workflow was
in-progress on that branch. Worth a fresh look if the spam recurs.

## Tooling gotcha

`mcp__github__list_pull_requests`'s `merged` field is stale/unreliable in bulk
listings: it reported `false` for PR #5126, which `mcp__github__pull_request_read`
method=`get` correctly showed as `merged: true` with a real `merged_at` and
`merged_by`. Always cross-check bulk PR merge status with `pull_request_read`
(or `search_pull_requests`' `is:merged` query) before drawing conclusions from
`list_pull_requests`.

## Cross-reference: recurring redundant critical-review sessions

This session's "critical review the open issue/PR backlog" task closely
duplicates `audits/2026-08-17-governance-bureaucracy-critical-review.md` from
two days earlier (same finding shape: ~94%/100% of open issues are the repo's
own CI/governance machinery, not product work). `list_sessions` at
2026-08-19T11:22Z showed ~25 Claude Code Remote sessions active or recently
active against this same repo, several targeting the same issues
concurrently (one had a merge-resolver actively in flight on PR #5036 while
this session was independently investigating it). The backlog regrew from 92
to 76+ open issues in the two days between audits despite active closure
work both times. The likely dominant cost driver is not any single validator
bug but the uncoordinated parallel-session fleet itself repeatedly
re-discovering and partially re-fixing the same ground. Worth a structural
fix (a shared work queue, a fleet-visibility dashboard, or capping concurrent
sessions per repo) rather than another one-off audit.

## Evidence

`.agents/sessions/2026-08-19-session-99919-bc967748c-critical-review-open-issues-prs.json`.
PR #5078 comment/review data pulled directly via `pull_request_read`
`get_comments`/`get_reviews` (all pages). Issue #5160.
