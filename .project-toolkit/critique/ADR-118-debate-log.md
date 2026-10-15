# ADR Debate Log: Widen FM-11 to Cover Hand-Authored Cross-Harness Instructions

## Summary

- **Rounds**: 1
- **Outcome**: Consensus. Both seats Accept after the fixes below.
- **Final Status**: proposed. The owner merges and accepts.
- **Panel**: reduced (architect and critic). The change edits a taxonomy entry in `.agents/governance/FAILURE-MODES.md`. No script parses its class list or titles, and no gate reads it. AGENTS.md reserves the full panel for executable enforcement or a rule other gates read.
- **Method note**: the task runner could not spawn fresh agents. One agent ran both seats as separate passes over the artifact, after drafting it. That is a closed loop, not two independent reviews. The independent check is the owner's merge review under `governance.md` MUST 1.

## Owner decision

Issue #5461 left the choice among widening FM-11, adding a sibling class, and rejecting to the owner. The owner delegated it on 2026-10-11. Rule: pick the option the issue recommends; if none, pick the option with the best evidence and smallest blast radius. The issue labels option 1 (widen FM-11) the cheapest and does not recommend another. Option A in the ADR is option 1.

## Round 1 Summary

### Key Issues Addressed

| # | Seat | Priority | Finding | Resolution |
|---|------|----------|---------|------------|
| 1 | architect | P1 | The issue proposes "FM-12" for the sibling option. `origin/main` already holds FM-12 (ADR-105) and FM-13 (ADR-117). | Fixed. The ADR names the sibling option FM-14. |
| 2 | architect | P1 | ADR-116 is held by open PR #6445. The next free number is 118. | Fixed. The ADR is ADR-118. No remote branch holds 118 or higher. |
| 3 | critic | P1 | The first FM-11 text said the detection and enforcement rows "apply as written". The Committed-artifact gate (`validate_hook_anchoring.py`) and the hook smoke only fit generated hooks. | Fixed. The text now scopes those two rows to generated hooks and adds one row for the hand-authored variant, anchored to `tests/claude_mem/test_importer_cli_contract.py`. |
| 4 | critic | P1 | The ADR claimed no script parses the class list or titles. That is an absence claim. | Verified. `git grep` for `FM-1`, `FM #1`, `Failure Mode Classification`, and `FAILURE-MODES` across `scripts`, `build`, `tests`, and `.github` finds a comment in `validate-plugin-manifests.yml` and one test file that lists the path. Neither parses titles. |
| 5 | critic | P2 | Every added normative line under `.agents/governance/` needs an evidence anchor (`governance.md` MUST 4). | Met. The variant paragraph, Trigger, Detection, and principle sit beside the #4780 evidence bullet, the retrospective path, and ADR-118 in References. |
| 6 | critic | P2 | The retrospective correction must append, not edit (`retros.md` MUST NOT 1). | Met. A dated section is appended. Landed text is untouched. |
| 7 | architect | P2 | Renaming the title could break anchor links. | Verified. `git grep` for `FAILURE-MODES.md#` finds anchors for sections 1 and 10 only. None for section 11. |
| 8 | critic | P2 | The secondary observation, a taste-lint for `in (0, 1)` assertions, could expand scope. | Deferred. The ADR records a detection line and says the lint is a separate change. One idea per PR. |
| 9 | critic | P2 | "When to Read" says "eight patterns", and the failure-archaeology skill table stops at FM-11. | Deferred. Both were stale before this change. Flagged in the ADR Consequences. |

### Major Changes Made

- Named the sibling option FM-14 and renumbered the ADR to 118.
- Scoped the "apply" claim and added a hand-authored enforcement row.
- Ran the absence and anchor searches and recorded them in Prior Art.

### Agent Positions

| Agent | Position |
|-------|----------|
| architect | Accept. Option A is the smallest change that gives a retrospective a class to cite. A sibling class would copy FM-11's detection and remedy rows. |
| critic | Accept. All P1 findings are fixed. The P2 deferrals are out of scope and recorded. |

### Next Steps

The owner reviews the PR. If PR #6445 lands first and takes ADR-116, no renumbering is needed here.

**Verdict**: Continue
