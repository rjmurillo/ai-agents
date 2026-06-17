# ADR-074 Architect Design-Review Note (single-reviewer, pre-debate)

Scope: this is a single-reviewer architect design-review of the Proposed ADR-074 (PR-autofix branch-ownership lease), authored alongside the ADR to record the architectural assessment before the ADR lands as `Proposed`. It is NOT the 6-agent adr-review debate (architect, critic, independent-thinker, security, analyst, high-level-advisor). The full multi-agent adr-review debate and human acceptance remain the required next gate before the ADR's status can move from `proposed` to `accepted`. This note exists so a Proposed draft can be opened for that review, not to substitute for it.

Issue: #2615. Triggering incident: PR #2611.

## What was reviewed

The decision to coordinate local `pr-autofix` and remote review/autofix loops on a shared PR branch via a PR-comment-backed, advisory, fail-open lease with a 15-minute TTL, sitting beside (never replacing) the existing Force-Push Safety SHA gate.

## Architect assessment

Boundary direction is correct. The lease is advisory and the SHA gate stays the single hard safety boundary. This keeps the forgeable signal (a PR comment anyone can write) out of the safety decision (a real git SHA compare). A design that let the lease authorize a push would invert that and create a false safety story; the ADR explicitly rejects it.

Store choice is consistent with the existing seam. The lease reuses the PR timeline that `check_pr_live_state.py` already reads, and the ACT/SKIP verdict shape and ADR-035 exit codes already in use for the pre-action probe. No new infrastructure, no parallel mechanism. This satisfies the "reuse, do not duplicate" boundary rule and answers acceptance criterion 3 (timeline records the owner) directly, because the lease comment is the timeline record.

Concurrency honesty is the strongest part. The ADR does not claim mutual exclusion it cannot deliver: PR comments have no atomic compare-and-set, so a sub-second acquire race is possible, and the ADR says so and shows the SHA gate absorbs it. This is the correct DDIA posture (no exactly-once wishful thinking; advisory claim plus a hard freshness guard).

Fail-open is mandatory and correctly placed. A comment-store outage degrades to today's behavior, not to a workflow outage. This matches ADR-066 (hook fail-open reconciliation) and the release-it integration-point rules.

Phasing is sound. Phase 1 (local-only) ships value without the externally-gated Phase 2 (remote CI integration behind a BOT_PAT audit). The expensive, uncertain half is deferred behind an explicit audit, not assumed.

## Open points the multi-agent debate should press

1. Security (for the security agent): the lease comment is untrusted input; confirm the strict-parse / fail-open-on-malformed treatment is sufficient and that forgery is bounded to a self-DoS for one TTL. The ADR's Security section makes this claim; the debate should verify it.
2. Critic / independent-thinker: is 15 minutes the right fixed TTL, and is "no atomic CAS, residual race absorbed by SHA gate" an acceptable permanent posture or a deferral that needs revisiting if collision frequency rises?
3. Analyst: success metric is "collision rate drops, zero force-push overwrites." Confirm that is measurable from existing signals before Phase 1 ships.

## Verdict

APPROVE-AS-PROPOSED for opening the ADR as `status: proposed`. The decision is internally consistent, reuses existing seams, and is honest about its limits. It MUST clear the full 6-agent adr-review debate and human acceptance before `accepted`. No code ships on the ADR alone.
