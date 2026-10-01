# Triage packets go stale within hours

## What happened

On 2026-09-29 a triage packet listed issue #5767 as open work. PR #5986 had already closed it hours before the fix agent launched. The session built nothing and posted a comment on #5767 saying so.

## Practice

Re-read the issue state right before dispatching a fix. Use `get_issue_context.py` and check `state` and linked PRs. The packet records what was true when it was written, not when the agent starts.

## Related

- [live-state-gate-expires-during-the-work](live-state-gate-expires-during-the-work.md) covers the same expiry for PR state.

## Source

P1 triage session 2026-09-29, issue #5767 and PR #5986.
