# ADR-063 Architect Review Record (Maintainer-Authorized Acceptance)

## Scope

ADR: `.agents/architecture/ADR-063-memory-skill-decomposition.md`
Action under review: status flip from Proposed to Accepted.
Date: 2026-06-17.

This is a maintainer-authorized acceptance record, not a fresh multi-round
design debate. The maintainer accepted ADR-063 on 2026-06-17. Under the
AGENTS.md "Ask First" authority, the human decision settles the architecture
choice; the adr-review debate exists to surface concerns before a human
decides, and that decision has now been made. No fabricated multi-round
transcript is recorded here. What follows is the single-pass architect-review
state that supports the acceptance.

## Decision Under Acceptance

ADR-063 Decision codifies five binding points, unchanged by this acceptance:

1. Split by operation, not by tier (search, episode extraction, causal-graph
   update, the Memory-First Gate, maintenance).
2. `memory` survives as a thin router that delegates to operation sub-skills.
3. The Memory-First Gate lives either in the router or in a dedicated
   `memory-gate` sibling. This single sub-point is left open for a later
   decision; the acceptance does not close it.
4. Boundaries from ADR-007, ADR-037, ADR-038, ADR-056 are preserved.
5. No behavior change for callers; the `memory` name keeps resolving.

## Architect Findings

- Structure and coherence: the Decision is internal-consistent. The thin-router
  continuation honors ADR-037; schemas (ADR-038) and the output envelope
  (ADR-056) are untouched. No structural P0.
- Alternatives: the Rationale table records four rejected axes (tier, source
  ownership, call frequency, all-passive) with stated reasons. The chosen
  operation axis is justified against the caller-difference criterion. No gap
  requiring a new round.
- Reversibility: the ADR records a file-move reversibility path and three kill
  criteria. Acceptable.
- Open item: Decision point 3 (gate location) is explicitly deferred to
  implementation debate. This is a recorded, bounded open question, not a P0
  blocker on acceptance.

## Verdict

APPROVED for acceptance. No open P0 issues. The single deferred sub-decision
(gate location, Decision point 3) is tracked in the ADR text and in the M3
implementation (issue #1948); it does not block the status flip.

## Phase 1 Implementation Note

Issue #1948 Phase 1 implements only the smallest reversible slice the ADR
commits to: extract the Tier 1 search operation into a `memory-search`
sub-skill, with `memory` remaining the thin router. The gate-location
sub-decision and the remaining operation sub-skills (episode, causal,
maintenance) are out of Phase 1 scope and flagged in the PR body.
