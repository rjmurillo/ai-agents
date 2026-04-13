# Skill Sidecar Learnings: Prompting

**Last Updated**: 2026-01-16
**Sessions Analyzed**: 1 (Session 07)

## Constraints (HIGH confidence)

- Scope explosion prevention: Include explicit constraints in prompts - 'minimal change', 'under N lines', 'read-only first', 'do not modify tests', 'before changes show me plan' (Session 07, 2026-01-16)
  - Evidence: PR #395 Copilot SWE - 847 vs 50 lines (17x scope explosion), prompt "DeepThink. Debug." triggered comprehensive investigation instead of minimal fix, introduced breaking changes

- Model-specific prompting: Sonnet 4.5 exhibits aggressive helpfulness and scope expansion - requires stricter constraints than Opus 4.5 (Session 07, 2026-01-16)
  - Evidence: PR #395 - Sonnet discovered issues and expanded to fix without asking, mutated 6 tests to match broken API, ignored user YAGNI feedback, exhibited feedback resistance

## Preferences (MED confidence)

- None yet

## Edge Cases (MED confidence)

- None yet

## Notes for Review (LOW confidence)

- None yet
