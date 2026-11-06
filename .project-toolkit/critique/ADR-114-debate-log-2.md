# ADR Debate Log: ADR-114 Plugin CLI Smoke Turns Advisory

## Summary

- **Rounds**: 2
- **Panel**: full (architect, critic, independent-thinker, security, analyst, high-level-advisor). The change edits `advisory_agent_workflows`, a rule the readiness check reads.
- **Outcome**: Consensus, 5 Accept and 1 Disagree-and-Commit, no Block
- **Final Status**: ADR-114 stays `proposed` and gains one dated amendment.
- **Prior debate log**: [ADR-114-debate-log.md](ADR-114-debate-log.md)

## Context

The owner decided on 2026-11-05 that no critical path may depend on anything AI, including provider credentials or an approval click. That reverses the Decision 13 exception. The panel reviewed whether the amendment states the decision accurately and completely.

## Agent Positions

| Agent | Vote | Key finding |
|-------|------|-------------|
| architect | Disagree-and-Commit | Decision 5, the Consequences lines, and the rollback row still contradict the amendment. |
| critic | Disagree-and-Commit | Same stale lines. The rollback order conflicted with the withdrawn item 8. |
| independent-thinker | Disagree-and-Commit | The Codex and Pi legs read no credential, so the rationale does not cover them. Local coverage was overstated. |
| security | Accept | Self-exemption, CWE-829, and `security.md` MUST 7 all pass. The smoke is not a security review. |
| analyst | Accept | Loader and hook claims hold. Local coverage wording was too broad. |
| high-level-advisor | Accept | Proportionate, nothing blocks shipping. The title is stale. |

## Resolutions

- **Stale text (P1)**: the amendment now names each superseded passage. The decision text stays unchanged, as in the 2026-10-11 amendments.
- **Rollback (P1, P2)**: the amendment states the loader behavior, that item 8 stays withdrawn, and that the Decision 13 Reversibility row no longer applies.
- **Local coverage (P1)**: the accepted risk now says the hooks run only on matching paths on one operating system.
- **Codex and Pi legs (P1)**: the amendment records that these legs turn advisory too, and it names the split-job alternative.
- **Ruleset state (P2)**: the live ruleset was read on 2026-11-05, and its required list does not hold `CLI Smoke Result`.
- **Exemption claim (P2)**: `_exempt_advisory_checks` was read. It drains both non-required buckets.
- **Vacuous test claim (P1, security and analyst)**: rejected. The test asserts absence from the recorded required contexts, so a new ruleset row fails it.
- **ADR-071 (P1, deferred with reason)**: the amendment points readers from ADR-071 to this decision. An edit to ADR-071 itself crosses the ADR size-cap baseline, and raising that baseline is not allowed to clear a change. ADR-071 already defers gate policy to Decision 13.
- **Title (P2, deferred with reason)**: the title stays, as sibling amendments leave decision text alone. The amendment names it as superseded.

## Round 2 Convergence

The architect and critic seats moved to Accept after the revision. The independent-thinker seat stayed at Disagree-and-Commit. The security, analyst, and high-level-advisor seats had already accepted in round 1.

## Post-Consensus Edit

Owner review on PR #7098 added the Decision 13 lead sentence to the superseded list. No seat's position depended on that omission.

## Dissent

The independent-thinker seat prefers to keep a blocking, ungated check for the zero-token load legs. The owner's decision stands, and the split stays open as later work.

## Decision

Every seat accepts or disagrees and commits. All P0 and P1 items are resolved or deferred above.
