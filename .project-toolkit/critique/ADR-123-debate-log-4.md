# ADR Debate Log: ADR-123 phrase-report correction

## Summary

- **Rounds**: 1 of 10
- **Prior debate log**: `.project-toolkit/critique/ADR-123-debate-log-3.md` (closed, consensus)
- **Outcome**: Consensus
- **Final Status**: accepted

The change corrects the section "Routing changes in the same change, outside this record".
A report-only phrase layer in DESIGN-036 was folded into the `Skill Trigger Phrase Resolution (ratchet)` gate.
That gate arrived by merging the `fix/adr-generator-selection` branch.
The edit is prose and changes no enforcement in this record, so the reduced panel ran.

## Round 1 Summary

### Votes

| Agent | Vote |
|-------|------|
| architect | Accept |
| critic | Disagree-and-Commit |

### Key Issues Addressed

| # | Issue | Pri | Resolution |
|---|-------|-----|------------|
| 1 | "The six phrases that miss today" had no anchor once the report was gone. | P2 | Anchored to `b8bedf583` on 2026-11-19. |
| 2 | `pre_pr_sequence.py` was unmerged in the index. | P3 | Resolved and staged with the merge commit. |
| 3 | The ratchet's name lacked its registered suffix. | P3 | Now `Skill Trigger Phrase Resolution (ratchet)`. |
| 4 | Status linked this log before it existed. | Note | This file. |

### Claims Checked

| Claim | Result |
|---|---|
| The routing evidence no longer computes a phrase report; intent reachability remains | VERIFIED |
| `check_skill_trigger_resolution.py` exists and is registered in `pre_pr_sequence.py` | VERIFIED |
| DESIGN-036 matches the ADR's description | VERIFIED |
