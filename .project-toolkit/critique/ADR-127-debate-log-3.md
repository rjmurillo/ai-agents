# ADR Debate Log 3: ADR-127 Workflow Skills Are Script Drivers, and Evals Gate Skill Rewrites

## Summary

- **Rounds**: 1 of 10
- **Prior debate log**: `.project-toolkit/critique/ADR-127-debate-log-2.md`
- **Outcome**: Consensus (2 Accept)
- **Final Status**: accepted
- **Panel**: reduced, architect and critic. The edit is prose only and changes no rule.
- **Date**: 2026-11-25

## Why a third debate

The second debate closed by consensus. Two things then changed ADR prose.

1. `scripts/validation/pre_pr.py` failed one gate on commit `5420aaac52` (2026-11-25): Citation Freshness.
   The Context section cited a gstack file as `path:line`. That file is not tracked in this repository.
2. The analyst review axis held that the title overclaimed. It said "Every Skill Rewrite".
   Decision 7 names one case outside the gate.

Carried forward from the second log: three standing dissents and no unresolved P0.

## Round 1 Summary

### Major Changes Made

- Context: the gstack source sentence names the module and points to audit rule A3 for the lines.
- Title: "Evals Gate Skill Rewrites". The file name and the id did not change.
- References: the line names all three debate logs.

No decision, number, or trigger changed.

### Agent Positions

| Agent | Position | Notes |
|---|---|---|
| architect | Accept | Confirmed neither change alters a decision. `check_adr_lifecycle.py` passed. |
| critic | Accept | Confirmed the title now matches decision 7's stated exception. |

## Dissent standing after all three debates

The three dissents in the second log stand unchanged: the critic's, the analyst's, and the high-level-advisor's.

## Next Steps

Unchanged from the second log.
