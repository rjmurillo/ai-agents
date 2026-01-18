# Skill Sidecar Learnings: Critique

**Last Updated**: 2026-01-18
**Sessions Analyzed**: 1 (batch 28)

## Constraints (HIGH confidence)

### Skill-Critic-005: ADR Design Principle vs Validation Requirement Distinction
**Pattern**: When critiquing validation gaps in ADRs, distinguish between "should" design principles (implementation guidance) and "must" enforceable requirements (validation checkpoints). ADR-017 stated "Pure lookup table. No title, no metadata" in IMPLEMENTATION section (line 254) as DESIGN PRINCIPLE, not VALIDATION REQUIREMENT.

**Evidence**: Critique 002 correctly identified Gap 3 as mischaracterization (session-83, 2025-12-23). Format validation exists via table parsing regex (lines 117-124); metadata above table is design choice not enforceable constraint. Confirmation section (lines 200-205) lists only 3 actual validation requirements: pre-commit hook, CI consistency check, keyword density.

**When Applied**: When reviewing ADR enforcement mechanisms or proposing validation additions. Verify whether stated constraint is architectural preference or blocking requirement.

**Anti-Pattern**: Treating architectural preferences as validation mandates, leading to over-engineering of enforcement mechanisms.

**Session**: batch-28, 2026-01-18

---

## Preferences (MED confidence)

None yet.

## Edge Cases (MED confidence)

None yet.

## Notes for Review (LOW confidence)

None yet.
