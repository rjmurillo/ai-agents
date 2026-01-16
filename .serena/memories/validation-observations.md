# Skill Sidecar Learnings: Validation

**Last Updated**: 2026-01-16
**Sessions Analyzed**: 1 (Session 07)

## Constraints (HIGH confidence)

- Background agent work requires completion verification - validate file count matches plan, add completion markers to commits. Format validation alone insufficient (Session 07, 2026-01-16)
  - Evidence: Memory split failure - created 16 of 49 files (33%), Validate-SkillFormat.ps1 passed format check but missed incompleteness, required 8-minute revert
  
- Recursive validation (critic + QA iterations) catches implementation gaps - cross-reference scanning required before 'complete' claim (Session 07, 2026-01-16)
  - Evidence: Issue #474 - 3 critic + 2 QA iterations caught workflow comments and ADR cross-references that implementer missed

## Preferences (MED confidence)

- None yet

## Edge Cases (MED confidence)

- None yet

## Notes for Review (LOW confidence)

- None yet

## Related

- [validation-006-self-report-verification](validation-006-self-report-verification.md)
- [validation-007-cross-reference-verification](validation-007-cross-reference-verification.md)
- [validation-007-frontmatter-validation-compliance](validation-007-frontmatter-validation-compliance.md)
- [validation-474-adr-numbering-qa-final](validation-474-adr-numbering-qa-final.md)
- [validation-anti-patterns](validation-anti-patterns.md)
