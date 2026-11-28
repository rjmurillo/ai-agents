# ADR-105 Amendment 2026-11-26: Debate Log

**ADR**: `.project-toolkit/architecture/ADR-105-terminal-state-completion-contract.md`
**Amendment**: section `## Amendment 2026-11-26`, items 1 to 6. The Task Completion Contract moves from `builder-ethos.md` section 4 to `core.md`. The always-on invariant does not change.
**Triggering context**: PR #7730 and ADR-129, which remove `builder-ethos` and `voice` from the always-on set.
**Claims ledger**: `.project-toolkit/critique/ADR-129-claims-ledger.md`, rows 35 to 37, 56, 58, 64, 69, 74, 76 and 77.
**Companion log**: `.project-toolkit/critique/ADR-129-debate-log.md`. It holds the mechanism, its limits and Phase 0.
**Date**: 2026-11-26
**Panel**: full panel (architect, critic, independent-thinker, security, analyst, high-level-advisor), reviewed together with ADR-129.

## Summary

- **Rounds**: 2 of 10
- **Prior debate log**: `.project-toolkit/critique/ADR-105-amendment-2026-10-13-debate-log.md`
- **Outcome**: Consensus. Five seats voted Accept and one voted Disagree-and-Commit in round 2.
- **Final Status**: accepted (unchanged; ADR-105 was already accepted)

## Round 1 Summary

Three seats ran in round 1. The other three first read the amendment in round 2.

### Key Issues Addressed

- architect (P1, Block): `.agents/governance/FAILURE-MODES.md` entry 12 still named `builder-ethos.md` and `voice.md` as the always-on owners. ADR-105 Decision item 3 requires that entry to track the rule.
- architect (P1): the amendment covered Decision items 1, 2 and 4 only. The Alternatives row marked chosen, the Impact row and the Negative bullets still named the old owner.
- critic (P2): older lines still describe `builder-ethos` as owner, with no note on how to read them.

### Major Changes Made

- `FAILURE-MODES.md` entry 12 now names `core.md` in its gate table and its references.
- The amendment gained item 5 (failure-mode entry) and item 6 (older sections record history, and how to read them).

### Agent Positions

| Agent | Position | Main finding |
|---|---|---|
| architect | Block | Stale owner in `FAILURE-MODES.md` and in older ADR-105 sections |
| critic | Accept | One P2 note on older lines |
| independent-thinker | Accept | Low confidence; read only the heading |
| security | Not run in round 1 | First read the amendment in round 2 |
| analyst | Not run in round 1 | First read the amendment in round 2 |
| high-level-advisor | Not run in round 1 | First read the amendment in round 2 |

## Round 2 Summary

### Key Issues Addressed

| Seat | Priority | Finding | Disposition |
|---|---|---|---|
| architect | P2 | The amendment did not say why this is not a superseding record for an implemented ADR | Fixed. The Why paragraph states that the decision stands and only the carrying file moved, as on 2026-09-15 |
| critic | P2 | Item 6 did not name the always-on location of sovereignty precedence | Fixed. Item 6 names `core.md` clause 5, clause 6 and `### Precedence` |
| analyst | P2 | `builder-ethos.md` line 114 called the Precedence Stack "the always-on summary" | Fixed in the template, its fixture and generated copies |
| independent-thinker | P2 | The Negative bullet on `FAILURE-MODES.md` still names the old owner | Covered. Item 5 says how to read that bullet |
| independent-thinker, architect | P2 | Frontmatter `date` moved from 2026-09-03 to 2026-11-26 | Not changed. `adr-generator` Amend mode step 3 says to update `date`, and ADR-073 defines it as last updated. Item 6 keeps the 2026-09-03 decision date in prose |

### Major Changes Made

- Three sentences on amendment against supersession.
- One sentence in item 6 on where precedence lives on the always-on path.

### Agent Positions

| Agent | Position | Note |
|---|---|---|
| architect | Disagree-and-Commit | Block lifted. Dissent: the amend-or-supersede reasoning was missing when the seat voted. It was added after the vote |
| critic | Accept | Items 5 and 6 close the stale-owner gap |
| independent-thinker | Accept | Confidence raised from low to medium. Would restore the original `date` |
| security | Accept | The precedence line and the terminal predicate are unchanged and still always-on |
| analyst | Accept | Items 1 to 6 match the files |
| high-level-advisor | Accept | One always-on owner is kept; the file move is recorded |

### Dissent kept on record

- architect and independent-thinker: the frontmatter `date` now hides the 2026-09-03 decision date. The two earlier amendments left `date` alone.

### Gate escapes

None.

### Next Steps

None. ADR-105 keeps `status: accepted` and `implemented: true`.
