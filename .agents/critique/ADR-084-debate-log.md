# ADR-084 Review Debate Log: Vendored-Hook ROI Bar

**Artifact**: `.agents/architecture/ADR-084-vendored-hook-roi-bar.md` (Proposed)
**Protocol**: ADR Review Protocol, 6-agent debate (architect, critic, independent-thinker, security, analyst, high-level-advisor)
**Date**: 2026-07-17
**Context**: issue #3215, part of the #3197 vendored-hook ROI review. One joint adr-review pass over this ADR and the ADR-062 amendment (issue #3214). The repo owner approved the ROI bar substance; this debate records consensus. The status:accepted flip is owner-authorized.

## Decision under review

A hook may ship in a vendored plugin surface only if it delivers consumer-repo value. Five rules: (1) consumer-repo value required, "enforces our protocol" disqualifying; (2) internal enforcement to `.githooks`/CI only; (3) prefer zero-spawn host-native surfaces where they achieve the same effect; (4) self-neutering vendored hooks banned; (5) one-line customer-value docstring plus a CI presence check.

## Votes

| Agent | Vote | Core position |
|-------|------|---------------|
| architect | Accept | Five rules internally consistent and mutually reinforcing: rules 1 and 4 draw the boundary, rule 2 names the alternative home (`.githooks`/CI, confirmed to exist), rule 3 sets a cost preference, rule 5 adds a mechanical ratchet. No conflict with ADR-068 (dispatch), ADR-073 (frontmatter matches), or ADR-078 (routing). |
| critic | Accept | Rule 2's enumerated internal list does not catch any consumer-value hook (verified `invoke_security_gate.py`, `invoke_markdownlint_guard.py`, `invoke_branch_protection_guard.py` are not `skip_if_consumer_repo` gated and run in consumer repos). Rule 5's presence check is implementable as a docstring grep. |
| independent-thinker | Accept | Rule 3's "prefer" is not a ban; the load-bearing "achieves the same effect" clause is sufficient and now made explicit. Rule 1's "enforces our protocol is disqualifying" is a factual filter (a consumer does not run this protocol), not a values judgment. Rule 5 is a trip-wire, not a semantic judge, the right division of labor. |
| security | Accept | Rule 2 moves only internal-protocol hooks that already self-neuter in consumer repos (verified `guards.py` lines 17-23, 162-190). No consumer-facing security property changes. Deferring the portable auth-edit rebuild to #3219 is responsible; the active security gates stay in place. |
| analyst | Accept | Verified `guards.py` contains `skip_if_consumer_repo` (lines 162-190, gates on `_PROJECT_REPO_NAME = "ai-agents"`), `.githooks/` exists (commit-msg, pre-commit, pre-push). The structural "most hooks no-op in consumer repos" claim is well-supported; the exact 12-of-13 count is illustrative framing, not a load-bearing technical claim. |
| high-level-advisor | Accept | A bounded lake, not an ocean: five rules, one CI check, one audience distinction. The bar is the right ratchet because the failure mode is structural re-accretion. Rule 5 converts policy into a PR-time gate. Governs additions, not existing code; defers deletion to the implementation issues. |

**Consensus: ACCEPTED (6/6 Accept). Zero P0.**

## P1 findings

Folded into the ADR:

- Rule 3 read as a soft ban could foreclose legitimate dynamic hooks (independent-thinker). Added an explicit clause: when the host surface cannot express the required logic (runtime inspection, conditional branching), a spawning hook is the right tool and the rule does not apply.
- A future reviewer could misapply the ROI bar to an actual security control (security). Added a bullet to "What this ADR does NOT do": the active security gates (`invoke_security_gate.py`, `invoke_security_commit_gate.py`) are not `skip_if_consumer_repo` gated, enforce a security property, and are out of scope for ROI-driven retirement.
- Rule 5 did not specify the docstring format (critic). Added the `Customer value:` prefix convention so the CI check is a presence grep, not a semantic judge.
- The "12 of 13" count is not enumerated in the ADR (critic, analyst, high-level-advisor). Added a citation that the per-hook enumeration and the single survivor live in the #3197 ROI review; this ADR sets the bar and does not restate the census.

Recorded as a follow-up for the implementation chain, not filed unilaterally:

- Rule 5's CI presence check has no tracking issue yet (architect). Recommended: the #3216 to #3218 chain, or a dedicated issue, should carry the check so the ratchet ships as an enforced gate rather than a policy-only convention.
