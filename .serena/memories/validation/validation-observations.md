# Skill Observations: validation

**Last Updated**: 2026-01-17
**Sessions Analyzed**: 7

## Purpose

This memory captures learnings from validation strategies, error messaging, and verification patterns across sessions.

## Constraints (HIGH confidence)

These are corrections that MUST be followed:

- Background agent work requires completion verification - validate file count matches plan, add completion markers to commits. Format validation alone insufficient (Session 07, 2026-01-16)
  - Evidence: Memory split failure - created 16 of 49 files (33%), Validate-SkillFormat.ps1 passed format check but missed incompleteness, required 8-minute revert
- Recursive validation (critic + QA iterations) catches implementation gaps - cross-reference scanning required before 'complete' claim (Session 07, 2026-01-16)
  - Evidence: Issue #474 - 3 critic + 2 QA iterations caught workflow comments and ADR cross-references that implementer missed
- Pagination off-by-one errors: 500 files exactly is valid, not truncated. Use `>` not `>=` for truncation threshold check (Session 825, 2026-01-13)
  - Evidence: False positive warning at exactly 500 files, fixed with correct boundary condition in test-large-pr-handling.sh
- Pre-commit hooks must skip *-index.md files to prevent circular validation failures - index files require pure lookup table format per ADR-017 (Session 02, Issue #910, 2026-01-14)
  - Evidence: Improve-MemoryGraphDensity.ps1 added Related sections to index files that Validate-MemoryIndex.ps1 rejected, causing commit failures. Fixed by detecting -index suffix pattern and skipping, 33 skills index files validated successfully after fix
- Directory precondition validation for external tools - tools like CodeQL need parent directory to exist before subdirectory creation. Explicitly create parent dirs before calling external commands (Session 6, PR #954, 2026-01-16)
  - Evidence: CodeQL CLI requires .codeql/db/ to exist before creating .codeql/db/<language> subdirectories. CodeQL failed when parent directory didn't exist, required explicit creation

## Preferences (MED confidence)

These are preferences that SHOULD be followed:

- JSON parsing errors should include line/column context and common fix suggestions - improves debuggability and reduces support burden (Session 388, 2026-01-09)
  - Evidence: Enhanced Validate-SessionJson.ps1 with line/column extraction, context display, and actionable fix suggestions
- SkipValidation parameter pattern for post-population validation control - allows template instantiation without throwing on placeholder checks (Session 388, 2026-01-09)
  - Evidence: TemplateHelpers.psm1 SkipValidation parameter properly controls exception throwing for post-population placeholder validation
- Allow +/-1 file tolerance for metrics accuracy - handles submodules, symlinks, and .gitignore changes that cause exact file count mismatches (Session 379, 2026-01-11)
  - Evidence: Session evidence verification planning - identified that exact file count matching fails in edge cases like submodule updates or symlink changes

## Edge Cases (MED confidence)

These are scenarios to handle:

## Notes for Review (LOW confidence)

These are observations that may become patterns:

## History

| Date | Session | Type | Learning |
|------|---------|------|----------|
| 2026-01-16 | Session 07 | HIGH | Background work requires completion verification |
| 2026-01-16 | Session 07 | HIGH | Recursive validation catches implementation gaps |
| 2026-01-13 | Session 825 | HIGH | Pagination off-by-one: 500 exactly is valid |
| 2026-01-14 | Session 02, Issue #910 | HIGH | Pre-commit hooks must skip *-index.md files |
| 2026-01-09 | Session 388 | MED | JSON parsing errors need context and fix suggestions |
| 2026-01-09 | Session 388 | MED | SkipValidation parameter for post-population control |
| 2026-01-11 | Session 379 | MED | Allow +/-1 file tolerance for metrics accuracy |
| 2026-01-16 | Session 6, PR #954 | HIGH | Directory precondition validation for external tools |

## Related

- [validation-006-self-report-verification](validation-006-self-report-verification.md)
- [validation-007-cross-reference-verification](validation-007-cross-reference-verification.md)
- [validation-007-frontmatter-validation-compliance](validation-007-frontmatter-validation-compliance.md)
- [validation-474-adr-numbering-qa-final](validation-474-adr-numbering-qa-final.md)
- [validation-anti-patterns](validation-anti-patterns.md)
- [validation-baseline-triage](validation-baseline-triage.md)
- [validation-domain-index-format](validation-domain-index-format.md)
- [validation-error-messages](validation-error-messages.md)
- [validation-false-positives](validation-false-positives.md)
- [validation-observations](validation-observations.md)
- [validation-pre-pr-checklist](validation-pre-pr-checklist.md)
- [validation-pr-feedback](validation-pr-feedback.md)
- [validation-pr-gates](validation-pr-gates.md)
- [validation-skepticism](validation-skepticism.md)
- [validation-test-first](validation-test-first.md)
- [validation-tooling-patterns](validation-tooling-patterns.md)
