# Skill Sidecar Learnings: Validation

**Last Updated**: 2026-01-18
**Sessions Analyzed**: 1 (batch 28)

## Constraints (HIGH confidence)

### Skill-Validation-007: Cross-Validation Gap Between Validators
**Pattern**: Multi-script validation systems must ensure cross-validation checks span validator boundaries. ADR-017 enforcement gap: `Validate-SkillFormat.ps1` excludes index files (lines 55, 68), while `Validate-MemoryIndex.ps1` `Test-FileReferences` only checks file existence not naming convention. Result: Index entries can reference deprecated `skill-` prefixed files without detection.

**Evidence**: Critique 002-adr-017-naming-gap-analysis identified Gap 1 with specific line numbers (session-83, 2025-12-23). No existing mitigation. Recommended fix: Add naming validation to Test-FileReferences after line 167 to reject entries with `skill-` prefix.

**When Applied**: When building multi-script validation systems where different validators have complementary responsibilities.

**Anti-Pattern**: Assuming each validator catches all violations in its domain without verifying coverage gaps at validator boundaries.

**Session**: batch-28, 2026-01-18

---

### Skill-Validation-008: Orphan Detection Pattern Blindness
**Pattern**: Pattern-based orphan detection must include explicit default handling for unmatched items. ADR-017 `Get-OrphanedFiles` (Validate-MemoryIndex.ps1 lines 282-283) uses domain-specific patterns (`^pr-`, `^issue-`) to identify files. Files like `skill-pr-001.md` silently bypass both domain pattern matching AND exclusion list - neither reported as orphan nor validated.

**Evidence**: Critique 002 Gap 4 analysis (session-83, 2025-12-23). Files matching no pattern are invisibly ignored rather than flagged.

**When Applied**: When building orphan detection systems that use pattern matching to categorize files.

**Anti-Pattern**: Pattern-based detection without catch-all for non-matches, leading to silent validation bypasses.

**Session**: batch-28, 2026-01-18

---

## Preferences (MED confidence)

None yet.

## Edge Cases (MED confidence)

None yet.

## Notes for Review (LOW confidence)

None yet.

## Related

- [skills-agent-workflow-index](skills-agent-workflow-index.md)
- [skills-analysis-index](skills-analysis-index.md)
- [skills-architecture-index](skills-architecture-index.md)
- [skills-architecture-observations](skills-architecture-observations.md)
- [skills-autonomous-execution-index](skills-autonomous-execution-index.md)
