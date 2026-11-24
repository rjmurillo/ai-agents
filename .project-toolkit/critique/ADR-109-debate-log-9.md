# ADR Debate Log: frontmatter dates for the 2026-11-20 amendments to ADR-068, ADR-071, and ADR-109

## Summary

- **Rounds**: 1 of 10
- **Prior debate log**: [`ADR-109-debate-log-8.md`](ADR-109-debate-log-8.md)
- **Outcome**: Consensus (self-review; no decision text changed)
- **Final Status**: accepted (no ADR status edit)
- **Scope**: the frontmatter `date` field of ADR-068, ADR-071, and ADR-109, set to 2026-11-20. Issue #7493.

The pre-PR `Doc Date Drift (advisory, added lines)` gate reported that each record's frontmatter date predated its 2026-11-20 amendment. The `adr-generator` Amend mode says to update the frontmatter `date` with an amendment. The amendments themselves were reviewed in `ADR-109-debate-log-7.md` (full panel) and `ADR-109-debate-log-8.md` (reduced panel).

## Round 1 Summary

### Key Issues Addressed

- Does the edit change any decision, status, or citation? No. Only the three `date:` lines change, plus the regenerated index rows that render them.
- Does the new date match the amendment date? Yes. Each record carries an amendment dated 2026-11-20.

### Agent Positions

| Agent | Position |
|-------|----------|
| self-review | Accept. Frontmatter-only correction that the doc-date-drift gate asked for. No panel needed, because no decision text, status, or rule changed. |
