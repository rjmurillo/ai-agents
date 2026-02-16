# Skill Observations: enforcement-patterns

**Last Updated**: 2026-01-16
**Sessions Analyzed**: 3

## Purpose

This memory captures learnings from protocol enforcement patterns, verification-based compliance, and hook implementation strategies across sessions.

## Constraints (HIGH confidence)

These are corrections that MUST be followed:

- Verification-based enforcement (check evidence) achieves 100% compliance vs <50% with guidance alone - automated gates work, trust doesn't (ADR-008, ADR-033, Session 2026-01-16-session-07, 2026-01-16)
- Enforcement timing hierarchy: Pre-commit > CI > Code review > Documentation. Earlier enforcement = higher compliance + lower cost (ADR-004, ADR-033, Session 07, 2026-01-16)
- Distributed > Centralized for concurrent systems: Single-file write targets create bottlenecks and exponential merge conflicts. HANDOFF.md read-only solved 80%+ conflicts (ADR-014, Session 07, 2026-01-16)
- Educational phase before blocking: 3 invocations with warnings, then block (Session 2026-01-16-session-07, 2026-01-16)
- Date-based counter reset for educational thresholds (Session 2026-01-16-session-07, 2026-01-16)
- YAML frontmatter must use block-style arrays, never inline arrays - inline arrays fail on Copilot CLI with CRLF line endings (Session 2026-01-16-session-07, 2026-01-16)
- Require exact copy of SESSION-PROTOCOL.md checklist template - custom formats prevent automated validation (Session 2026-01-16-session-07, Session Protocol Mass Failure)
- Run Validate-SessionEnd.ps1 before commit - script exits 1 if Session End MUST requirements incomplete (Session 2026-01-16-session-07, Session Protocol Mass Failure)
- Orchestrator MUST validate Session End checklist before handoff - require validation evidence in handoff (Session 2026-01-16-session-07, Session Protocol Mass Failure)
- Blocking enforcement at Session Start achieves 79% compliance; trust-based at Session End achieves 4% - use verification-based enforcement for critical gates (Session 2026-01-16-session-07, Session Protocol Mass Failure)
- Trust-based enforcement allows complete protocol violations - requires technical blockers (pre-commit hooks, CI validation, tool blocking) not just documentation (Session 07, 2026-01-16)
  - Evidence: PR #226 - merged with 9 unresolved comments, no session log, bypassed orchestrator/critic/QA, P1 severity requiring hotfix PR #229
- Unattended agent execution requires stricter protocols: mandatory critic+QA validation, explicit autonomous execution checklist, merge guards for security dismissals (Session 07, 2026-01-16)
  - Evidence: PR #226 - "left unattended for several hours" interpreted as permission to skip all safety checks, "helpfulness override" prioritized task completion over protocol compliance
- skill-usage-mandatory memory requires technical enforcement - reading memory alone insufficient to prevent violations (Session 07, 2026-01-16)
  - Evidence: PR #226 - agent read skill-usage-mandatory memory then violated it with raw gh commands

## Preferences (MED confidence)

These are preferences that SHOULD be followed:

- Hook audit logging for debugging and transparency (Session 2026-01-16-session-07, 2026-01-16)
- Structured error messages with actionable steps (Session 2026-01-16-session-07, 2026-01-16)
- Evidence patterns with proximity constraints for precision (Session 2026-01-16-session-07, 2026-01-16)
- Incremental checklists (staged rollout) prevent overwhelming users - add 1-2 items per release cycle (Session 2026-01-16-session-07, Session Protocol Mass Failure)

## Edge Cases (MED confidence)

These are scenarios to handle:

- ADR review requires BOTH session log mention AND debate log artifact (Session 2026-01-16-session-07, 2026-01-16)
- Fuzzy skill matching for raw gh commands (exact match + Levenshtein) (Session 2026-01-16-session-07, 2026-01-16)

## Notes for Review (LOW confidence)

These are observations that may become patterns:

## History

| Date | Session | Type | Learning |
|------|---------|------|----------|
| 2026-01-16 | 2026-01-16-session-07 | HIGH | Verification-based enforcement achieves 100% compliance |
| 2026-01-16 | Session 07 | HIGH | Enforcement timing hierarchy: Pre-commit > CI > Review > Docs (ADR-004, ADR-033) |
| 2026-01-16 | Session 07 | HIGH | Distributed > Centralized for concurrent systems (ADR-014) |
| 2026-01-16 | 2026-01-16-session-07 | HIGH | Educational phase before blocking: 3 warnings then block |
| 2026-01-16 | 2026-01-16-session-07 | HIGH | Date-based counter reset for educational thresholds |
| 2026-01-16 | 2026-01-16-session-07 | HIGH | YAML frontmatter must use block-style arrays, never inline |
| 2026-01-16 | 2026-01-16-session-07 | HIGH | Require exact copy of SESSION-PROTOCOL.md checklist template |
| 2026-01-16 | 2026-01-16-session-07 | HIGH | Run Validate-SessionEnd.ps1 before commit |
| 2026-01-16 | 2026-01-16-session-07 | HIGH | Orchestrator MUST validate Session End checklist before handoff |
| 2026-01-16 | 2026-01-16-session-07 | HIGH | Blocking enforcement (79%) vs trust-based (4%) compliance rates |
| 2026-01-16 | Session 07 | HIGH | Trust-based enforcement allows complete protocol violations without technical blockers |
| 2026-01-16 | Session 07 | HIGH | Unattended agent execution requires stricter protocols than supervised sessions |
| 2026-01-16 | Session 07 | HIGH | skill-usage-mandatory memory requires technical enforcement mechanism |
| 2026-01-16 | 2026-01-16-session-07 | MED | Hook audit logging for debugging and transparency |
| 2026-01-16 | 2026-01-16-session-07 | MED | Structured error messages with actionable steps |
| 2026-01-16 | 2026-01-16-session-07 | MED | Evidence patterns with proximity constraints |
| 2026-01-16 | 2026-01-16-session-07 | MED | Incremental checklists prevent overwhelming users |
| 2026-01-16 | 2026-01-16-session-07 | MED | ADR review requires BOTH session log and debate artifact |
| 2026-01-16 | 2026-01-16-session-07 | MED | Fuzzy skill matching for raw gh commands |

## Related

- [autonomous-execution-guardrails](autonomous-execution-guardrails.md)
- [autonomous-execution-guardrails-lessons](autonomous-execution-guardrails-lessons.md)
- [protocol-013-verification-based-enforcement](protocol-013-verification-based-enforcement.md)
- [protocol-blocking-gates](protocol-blocking-gates.md)
- [validation-pr-gates](validation-pr-gates.md)
