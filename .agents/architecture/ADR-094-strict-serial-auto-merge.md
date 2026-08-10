---
id: ADR-094
status: accepted
date: 2026-08-09
decision-makers: [rjmurillo]
supersedes: []
superseded-by: null
explainer: null
implemented: false
---

# ADR-094: Strict freshness with one-front auto-merge

## Status

Accepted after unanimous six-role review. Implementation is pending merge of
the protocol, retrospective, and Serena memory updates in this change.

## Date

2026-08-09

## Context

This user-owned repository cannot use GitHub's native merge queue. A Trunk.io
trial created 18 draft pull requests and 695 workflow runs in the measured
incident window, then merged zero pull requests. The integration was removed.

Restoring strict branch freshness closed stale-merge races. Updating 41 behind
branches in parallel then triggered 820 queued or in-progress workflow runs.
The first merge would invalidate the other 40 matrices. Auto-merge was disabled
on 41 PRs and 818 runs were cancelled. Those cancellations removed the only
producer of several required status contexts and stalled the backlog.

The repository needs both:

1. a server-side stale-merge guard; and
2. a cost control that does not refresh the full backlog on every merge.

## Decision

Keep ruleset `11104075`
`strict_required_status_checks_policy: true`.

Drain the backlog with one front PR at a time:

1. Acquire the fixed repository landing lease
   `refs/heads/merge-drain-lock`.
2. Disable auto-merge on every other open PR.
3. Update only the front PR to current main.
4. Run local deterministic checks and canonical AI prompts.
5. Let required CI finish.
6. Enable GitHub squash auto-merge.
7. If main moves, GitHub strict freshness blocks the merge. Refresh only the
   front PR.
8. Wait until the PR reaches `MERGED`.
9. Require green push workflows on the new main commit before advancing.
10. Release the landing lease only after main is green.

Dependent new changes should use stacked PRs. Unrelated backlog work must not
be stacked.

Changes under `.agents/governance/**` require human maintainer approval and
cannot use auto-merge.

## Prior Art Investigation

### What Currently Exists

- **Structure/pattern being changed**:
  [`.agents/SESSION-PROTOCOL.md`](../SESSION-PROTOCOL.md), introduced as the
  canonical session contract.
- **When introduced**: commit `fd7d1d61d`, PR #59, 2025-12-18.
- **Original purpose**: replace trust-based agent behavior with observable,
  verified gates.

The investigation found 418 files or references dependent on the protocol.
Related decisions include ADR-008, ADR-014, ADR-049, and ADR-050.

### Historical Rationale

Strict freshness was enabled to close issue #3755: a PR could merge after main
moved, although its checks had never seen the new main content.

The later Trunk trial attempted to improve throughput by testing combined
results. Its draft-PR mode did not fit this repository's required metadata
checks and multiplied paid AI review runs.

### Why Change Now

The original stale-merge problem still exists, so strict freshness is
preserved. The new evidence changes only the cost strategy: refreshing every
branch before the first merge produces work guaranteed to become stale.

## Rationale

### Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
|-------------|------|------|----------------|
| Strict true, refresh all PRs | Server-side safety | O(N²) matrices while draining | Measured 820 runs from 41 updates |
| Strict false, one front | O(N × R) CI cost | Stale-merge TOCTOU remains | Safety regression |
| Trunk.io merge queue | Combined-result testing | 18 drafts, 695 runs, zero merges | Removed after failed trial |
| GitHub native merge queue | Platform queue | Not available to user-owned repositories | Unavailable |
| Strict true, one front | Server-side safety and O(N × R) cost | Serial throughput | Chosen |

### Trade-offs

One-front landing is slower than a working native queue. It avoids paying for
CI matrices that strict freshness will invalidate. Stacked PRs retain
parallel development for dependent work without arming unrelated PRs.

## Consequences

### Positive

- GitHub blocks stale merges at merge time.
- Only one branch update and test matrix runs per merge attempt.
- Atomic Git ref creation prevents two landing sessions from arming PRs
  concurrently.
- A red main push halts the drain before another PR lands.
- Required CI cancellation is no longer part of normal backlog control.

### Negative

- Backlog landing is serial.
- A slow or flaky front PR blocks following PRs.
- Dependent stacks require retargeting after the parent merges.

### Neutral

- Existing required checks and squash-only policy remain unchanged.

## Impact on Dependent Components

| Component | Dependency Type | Required Update | Risk |
|-----------|----------------|-----------------|------|
| `SESSION-PROTOCOL.md` | Direct | Add one-front landing procedure | High |
| `GOTCHAS.md` | Direct | Record O(N²) and cancellation traps | Medium |
| Serena CI memories | Direct | Remove active Trunk and strict-false guidance | High |
| GitHub skill scripts | Indirect | Use existing merge and auto-merge commands | Low |
| PR automation agents | Indirect | Arm at most one front PR | High |
| Git refs | Direct | Add fixed fail-closed landing lease ref | Medium |

## Implementation Notes

- Issue #4827 tracks PR workflows that omit `reopened`.
- Issue #4835 tracks a fail-closed workflow cancellation guard.
- The incident retrospective is
  [2026-08-09-trunk-ci-cancellation-incident.md](../retrospective/2026-08-09-trunk-ci-cancellation-incident.md).
- The formal review record is
  [ADR-094-debate-log.md](../critique/ADR-094-debate-log.md).
- The machine-readable consensus is
  [decision-2026-08-10T08-38-56-548676+00-00.json](../decisions/decision-2026-08-10T08-38-56-548676+00-00.json).

## Related Decisions

- [ADR-008: Protocol Automation via Lifecycle Hooks](ADR-008-protocol-automation-lifecycle-hooks.md)
- [ADR-014: Distributed Handoff Architecture](ADR-014-distributed-handoff-architecture.md)
- [ADR-049: Pre-PR Validation Gates](ADR-049-pre-pr-validation-gates.md)
- [ADR-050: ADR-to-Protocol Sync Process](ADR-050-adr-protocol-sync.md)

## References

- [Issue #3755](https://github.com/rjmurillo/ai-agents/issues/3755)
- [Issue #4815](https://github.com/rjmurillo/ai-agents/issues/4815)
- [PR #4814](https://github.com/rjmurillo/ai-agents/pull/4814)
- [Issue #4820](https://github.com/rjmurillo/ai-agents/issues/4820)
- [Issue #4827](https://github.com/rjmurillo/ai-agents/issues/4827)
- [Issue #4835](https://github.com/rjmurillo/ai-agents/issues/4835)
