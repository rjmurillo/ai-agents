# Skill Observations: quality-gates

**Last Updated**: 2026-01-16
**Sessions Analyzed**: 2

## Purpose

This memory captures learnings from quality gate patterns, PR validation workflows, and shift-left testing strategies across sessions.

## Constraints (HIGH confidence)

These are corrections that MUST be followed:

- Apply PR Type Detection, Expected Patterns, and Context-Aware CRITICAL_FAIL patterns when modifying AI quality gate prompts - reduces false positives (Session 2026-01-16-session-07, Issue #357)

## Preferences (MED confidence)

These are preferences that SHOULD be followed:

- Shift-left pattern - run CI quality gates locally before push (Session 2026-01-16-session-07, 2026-01-16)
- Parallel agent execution for efficiency (Session 2026-01-16-session-07, 2026-01-16)
- Model selection by complexity: Opus for reasoning (architect, roadmap), Sonnet for standard (security, qa, analyst, devops) (Session 2026-01-16-session-07, 2026-01-16)
- Meta orchestrator aggregates verdicts for overall PASS/FAIL (Session 2026-01-16-session-07, 2026-01-16)
- Pre-PR validation gates: commits ≤20, files ≤10, no BLOCKING synthesis flag - prevents review overload (Session 2026-01-16-session-07, Issue #357)

## Edge Cases (MED confidence)

These are scenarios to handle:

- MCP tool wildcards intentional and safe within Claude Code security model (Session 2026-01-16-session-07, 2026-01-16)

## Notes for Review (LOW confidence)

These are observations that may become patterns:

## History

| Date | Session | Type | Learning |
|------|---------|------|----------|
| 2026-01-16 | 2026-01-16-session-07 | HIGH | Apply prompt engineering patterns for AI quality gate prompts |
| 2026-01-16 | 2026-01-16-session-07 | MED | Shift-left pattern - run CI quality gates locally before push |
| 2026-01-16 | 2026-01-16-session-07 | MED | Parallel agent execution for efficiency |
| 2026-01-16 | 2026-01-16-session-07 | MED | Model selection by complexity: Opus for reasoning, Sonnet for standard |
| 2026-01-16 | 2026-01-16-session-07 | MED | Meta orchestrator aggregates verdicts for overall PASS/FAIL |
| 2026-01-16 | 2026-01-16-session-07 | MED | MCP tool wildcards intentional and safe within Claude Code security model |
| 2026-01-16 | 2026-01-16-session-07 | MED | Pre-PR validation gates thresholds prevent review overload |

## Related

- [quality-basic-testing](quality-basic-testing.md)
- [quality-definition-of-done](quality-definition-of-done.md)
- [quality-prompt-engineering-gates](quality-prompt-engineering-gates.md)
- [quality-qa-routing](quality-qa-routing.md)
- [quality-shift-left-gate](quality-shift-left-gate.md)
