# ADR-090 Debate Log

## Summary

ADR review ran on 2026-07-27 for `ADR-090: PR Branch Holder Lease`. The first draft got no clean approval. Reviewers agreed that the direction was correct, but found blocking gaps in rollout, identity, ordering, and override authorization.

## Reviewers

| Reviewer | Verdict | Main findings |
|----------|---------|---------------|
| architect | Needs changes | v1 to v2 migration missing, latest marker semantics unclear, generated holder fallback unsafe. |
| independent-thinker | Approve with changes | 45 minute TTL was too long with renewal, override needed an authorization boundary, store consistency needed sharper ordering. |
| security | Blocked until fixed | Override could become an unauthenticated bypass. Body-declared actor and owner must not authorize anything. |
| analyst | Needs revision | Caller inventory needed `.github/actions/ai-review`; measurement needed a date window; renewal failure behavior was unspecified. |
| critic | Revise | The draft was directionally right but incomplete on staleness, identity fallback, and migration. |
| high-level-advisor | No-go until P0 fixed | The ADR solves the right problem at the right layer but was not implementation-ready. |

## P0 findings and resolution

| Finding | Resolution in ADR-090 revision |
|---------|--------------------------------|
| v1 to v2 migration path missing | v2 scanners read both markers. Live v1 markers are treated as foreign live holders until expiry or authorized override. |
| Generated invocation id undermines fail-closed | Generated holder ids are banned for enforced acquire, renew, release, override, and verify operations. |
| Latest marker semantics ambiguous | Highest valid GitHub issue comment id wins. Timestamps never decide ordering. Edits do not create newer state. |
| Override authorization missing | Override requires repository `maintain` or `admin` permission verified through GitHub API. |

## P1 findings and resolution

| Finding | Resolution in ADR-090 revision |
|---------|--------------------------------|
| 45 minute TTL crash-block too long | TTL changed to 30 minutes. Renewal changed to every 5 minutes during long operations. |
| Renewal failure behavior unspecified | Enforcement-mode renewal failure aborts the operation with exit 3 or 4. |
| Exit code collision with safe push | Lease checks reuse safe-push exit taxonomy and require machine-readable reasons. |
| Scan bound missing | Scanner reads newest 100 issue comments and fails closed on store or auth failure. |
| Replay and ordering protection missing | Comment id ordering is authoritative. Body timestamps are informational. |
| Measurement window missing | Workflow run measurement window added: 2026-07-25T11:27:15Z to 2026-07-27T20:32:37Z. |
| `.github/actions/ai-review` caller omitted | Caller table now lists it as read-only for this ADR's branch-mutation scope. |

## Remaining accepted risks

- The PR comment store has no atomic compare-and-set. Exact-SHA push verification remains the final safety gate.
- A crashed holder can block a branch for up to 30 minutes.
- Raw `git push` callers remain out of scope until migrated to `safe_push_pr_branch.py`.
- PR timelines will get more machine comments because state transitions post new markers.

## Debate outcome

Revised ADR-090 is ready for PR review as a proposed ADR. It should not be marked accepted until repository review agrees that the override authorization and v1 to v2 rollout plan are sufficient.

## Recheck

A focused critic recheck ran after the revision. It found no remaining P0 blockers. Three P1 clarity gaps were fixed in the ADR: `base_sha` is audit-only, v1 expiry parsing references ADR-076 `expires_at` and `owner: none`, and kill criteria now name their data sources plus structured lease events.
