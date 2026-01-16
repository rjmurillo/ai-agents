# Skill Observations: testing

**Last Updated**: 2026-01-16
**Sessions Analyzed**: 1

## Purpose

This memory captures learnings from testing strategies, test coverage, and cross-platform validation patterns across sessions.

## Constraints (HIGH confidence)

These are corrections that MUST be followed:

- Integration tests must test end-to-end behavior, not just structure - verifying function names exist is insufficient (Session 2026-01-16-session-07, 2026-01-16)
- Test inputs must align with script's actual matching logic, not hoped-for behavior - verify assumptions match reality (Session 2026-01-16-session-07, 2026-01-16)
- Fixes without tests lead to regressions - add tests covering both old AND new scenarios before claiming success (Session 2026-01-16-session-07, 2026-01-16)
- Cross-platform features require testing on all target platforms BEFORE merge (Session 2026-01-16-session-07, 2026-01-16)
- Test plans must be completed before merge - unchecked test plan items = untested code = regressions. Block merge if checklist incomplete OR remove unchecked items from plan (Session 2026-01-16-session-07, 2026-01-16)

## Preferences (MED confidence)

These are preferences that SHOULD be followed:

- Use CI matrix builds for multi-platform validation to prevent regression cycles (Session 2026-01-16-session-07, 2026-01-16)

## Edge Cases (MED confidence)

These are scenarios to handle:

- Large PRs (500+ files) hit pagination limits - emit explicit warning when truncating or use --paginate to fetch all files (Session 2026-01-16-session-07, 2026-01-16)

## Notes for Review (LOW confidence)

These are observations that may become patterns:

## History

| Date | Session | Type | Learning |
|------|---------|------|----------|
| 2026-01-16 | 2026-01-16-session-07 | HIGH | Integration tests must test end-to-end behavior, not just structure |
| 2026-01-16 | 2026-01-16-session-07 | HIGH | Test inputs must align with actual matching logic |
| 2026-01-16 | 2026-01-16-session-07 | HIGH | Fixes without tests lead to regressions |
| 2026-01-16 | 2026-01-16-session-07 | HIGH | Cross-platform features require testing on all platforms before merge |
| 2026-01-16 | 2026-01-16-session-07 | HIGH | Test plans must be completed before merge |
| 2026-01-16 | 2026-01-16-session-07 | MED | Use CI matrix builds for multi-platform validation |
| 2026-01-16 | 2026-01-16-session-07 | MED | Large PRs hit pagination limits - emit warning when truncating |

## Related

- [testing-002-test-first-development](testing-002-test-first-development.md)
- [testing-003-script-execution-isolation](testing-003-script-execution-isolation.md)
- [testing-004-coverage-pragmatism](testing-004-coverage-pragmatism.md)
- [testing-007-contract-testing](testing-007-contract-testing.md)
- [testing-008-entry-point-isolation](testing-008-entry-point-isolation.md)
- [testing-coverage-philosophy-integration](testing-coverage-philosophy-integration.md)
- [testing-coverage-requirements](testing-coverage-requirements.md)
- [testing-get-pr-checks-skill](testing-get-pr-checks-skill.md)
- [testing-mock-fidelity](testing-mock-fidelity.md)
