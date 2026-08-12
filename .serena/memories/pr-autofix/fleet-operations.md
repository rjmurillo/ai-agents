# PR Autofix Fleet Operations

## Lease discipline

- Check lease status before delegating work. Skip live holders without mutation.
- When a held lease becomes free, acquire it before fresh triage. The free window is a race.
- Renew leases on a timer during long test or investigation phases, not only before mutations.

## Live-state discipline

- Treat a late live-state skip as correct behavior. Release the lease, refresh readiness, and retry only from new evidence.
- Main-branch merges can restart CI for every remaining PR. Re-read head SHA, base SHA, checks, and threads after each main advance.

## Check interpretation

- A helper-green result that conflicts with a required-check blocker needs full latest-run-per-context analysis. See [use-get-pr-checks-not-raw-rollup](../pr-review/use-get-pr-checks-not-raw-rollup.md).
- Do not infer a human approval requirement from a generic branch-protection message. Read the current ruleset and review decision.

## QA evidence after base refresh

Merging main can stale QA evidence because non-evidence paths appear after `qaCommit`. Land code changes first, then rebind the QA report and session evidence to the refreshed commit.

## Tool contract cautions

PR helper scripts do not all share one JSON shape or option set. Read each script's help before composing fleet automation.

- `pr_autofix_lease.py` may leave `Data.held_by` empty on a SKIP result. The holder is encoded in `Data.reason` as `held-by:<owner>`.
- `get_unresolved_review_threads.py` returns a bare top-level object with `threads`, not the standard `Data` envelope.
- `set_pr_auto_merge.py` does not accept `--output-format`; passing it exits with an argument error.

## Evidence

Consolidated from the 2026-08-11 pr-autofix batch A, batch B, PR #4721, and fleet-retry session records.
