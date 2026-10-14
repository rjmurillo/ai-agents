# ADR Debate Log: Add FM-13, State Conflation in a Boolean Guard, to the Failure Taxonomy

## Summary

- **Rounds**: 1
- **Outcome**: Consensus. Both seats Accept after the fixes below.
- **Final Status**: proposed. The owner merges and accepts.
- **Panel**: reduced (architect and critic). The change adds a taxonomy entry to `.agents/governance/FAILURE-MODES.md`. No script parses its class list, and no gate reads it. AGENTS.md reserves the full panel for executable enforcement or a rule other gates read.
- **Method note**: the task runner could not spawn fresh agents. One agent ran both seats as separate passes over the artifact, after drafting it. That is a closed loop, not two independent reviews. The independent check is the owner's merge review under `governance.md` MUST 1.

## Owner decision

Issue #5145 left the choice between a new class and "no new class" to the owner. The owner delegated it on 2026-10-11. Rule: pick the option the issue recommends. The issue recommends the new class. Option A in the ADR is that choice.

## Round 1 Summary

### Key Issues Addressed

| # | Seat | Priority | Finding | Resolution |
|---|------|----------|---------|------------|
| 1 | architect | P1 | The draft was numbered ADR-115. `origin/main` already holds `ADR-115-native-plugin-support-per-host.md`. Open PR #6445 holds ADR-116. | Fixed. Renumbered to ADR-117. |
| 2 | architect | P2 | PR #6445 also proposes a new class and leaves `FAILURE-MODES.md` unchanged until accepted. If both land, both claim FM-13. | Deferred. This PR lands FM-13 now. The later change renumbers its class at acceptance. Recorded in the PR body. |
| 3 | architect | P2 | FM-10 needs a pointer to its neighbor, or a reader who lands there never finds FM-13. | Met. FM-10 gains "Not this class: loud conflation". |
| 4 | critic | P1 | The ADR cited `retros.md` MUST-1 for "do not edit landed retros". That rule is MUST NOT 1. MUST 1 is the filename convention. | Fixed in the ADR. The landed 5097 retro uses the same loose label. It is left alone under MUST NOT 1. |
| 5 | critic | P1 | The ADR said the #5104 evidence rests on issue text only. The 2026-09-01 #5104 retrospective exists, says no class fits, and points at #5145. | Fixed. The ADR and FM-13 cite that retrospective. The negative consequence now names #1168, which has no retrospective. |
| 6 | critic | P2 | Every added normative line in a governance file needs an evidence anchor (`governance.md` MUST 4). | Met. FM-13 carries Evidence and References sections with issues, a PR, a retrospective, a test file, and this ADR. |
| 7 | critic | P2 | "When to Read" in `FAILURE-MODES.md` still says "eight patterns". | Deferred. The text was stale before this change. Out of scope for one idea per PR. Flagged in the ADR. |
| 8 | critic | P2 | The FM-10 / FM-13 split must be testable, not a taste call. | Met. The distinguisher is one question: does a reader of the output know something went wrong. |

### Major Changes Made

- Renumbered the ADR to 117 and updated the retrospective correction and the FM-13 reference.
- Fixed the `retros.md` rule citation.
- Added the #5104 retrospective as evidence.

### Agent Positions

| Agent | Position |
|-------|----------|
| architect | Accept. Option A is the smallest change that gives the retrospective a class to cite. Widening FM-10 loses its testable property. |
| critic | Accept. All P1 findings are fixed. The two P2 deferrals are out of scope and recorded. |

### Next Steps

The owner reviews the PR. If PR #6445 lands first, renumber FM-13 here before merge.
