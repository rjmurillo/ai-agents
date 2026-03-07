# Skill Sidecar Learnings: Tool Usage

**Last Updated**: 2026-01-16
**Sessions Analyzed**: 1 (Session 07)

## Constraints (HIGH confidence)

- Call Read tool before Edit to ensure old_string matches file content exactly (Session 07, 2026-01-16)
  - Evidence: PR #212 - edit failures resolved by reading file first, prevents edit failures from mismatched old_string, 98% atomicity

## Preferences (MED confidence)

- Format GraphQL mutations as single-line strings in `gh api graphql -f query='...'` (Session 07, 2026-01-16)
  - Evidence: PR #212 - multi-line formatted mutations caused syntax errors requiring multiple retry iterations, single-line format discovered through trial, 97% atomicity

## Edge Cases (MED confidence)

- None yet

## Notes for Review (LOW confidence)

- None yet
