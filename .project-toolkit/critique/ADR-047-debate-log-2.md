# ADR-047 Debate Log 2: 2026-11-24 amendment

Prior debate log: `.project-toolkit/critique/ADR-047-debate-log.md`.
Claims ledger: `.project-toolkit/critique/ADR-047-claims-ledger.md` (18 rows).
Scope: the amendment "Skill scripts that load the shared parser prefer their own lib".
Panel: reduced (architect and critic). The amendment is prose only and changes no enforcement code.
Owner direction: "fix the issues", which covered the open item from PR #7531's architect review.

## Pre-review gates

| Gate | Result |
|------|--------|
| Claims ledger | VERIFIED: 15 rows before review, 18 after |
| Documentation accuracy | VERIFIED by the refuting seat against the cited source files |
| Self-consistency | VERIFIED: Change, Why, the compatibility table, and Trade-off agree |
| Refuting seat (analyst) | Two sentences refuted and three qualified. All five were reworded before round 1 |

## Round 1

| Agent | Position |
|-------|----------|
| architect | Disagree-and-Commit: lines 48 and 74 still state the MUST with no pointer to the exception |
| critic | Disagree-and-Commit: "three shapes" undercounts the older skill-script bootstraps, and line 74 conflicts |

### Key Issues Addressed

- **P1**: Lines 48 and 74 now name the amendment as the exception to the boilerplate rule.
- **P1**: "Three shapes" was false. An "Out of scope" paragraph now records the older skill-script bootstraps and their counting rule.
- **P2**: The text now covers:
  - environment-variable precedence (`COPILOT_PLUGIN_ROOT` first);
  - a table row for a copied script with no environment root;
  - the exit-1 versus ADR-035 exit-2 difference;
  - the shallow-depth `IndexError`;
  - the test's blind spot for copies in another shape;
  - a rejected parser-version alternative.
- **P2**: ADR-121 is added to Related Decisions.

## Round 2

| Agent | Position |
|-------|----------|
| architect | Accept. One P2 left: drop "third" from "third bootstrap shape". Applied |
| critic | Accept. Two P2s left: drop the ordinal (applied), and state the counting rule behind "15" (applied) |

## Outcome

Consensus: Accept (2 of 2). Status unchanged: `accepted`, `implemented: true`.

## Follow-up for the owner

The older skill-script bootstraps (15 by the stated rule) still read the environment root first. Converting them to own-lib-first changes resolution for shipped scripts. It is outside this amendment and is left for the owner.
