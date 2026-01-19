# Skill Observations: architecture

**Last Updated**: 2026-01-17
**Sessions Analyzed**: 10

## Purpose

This memory captures learnings from architecture and ADR compliance work across sessions.

## Constraints (HIGH confidence)

These are corrections that MUST be followed:

- Multi-tier architecture pattern for tool integrations: Tier 1 (CI/CD enforcement), Tier 2 (Local fast feedback), Tier 3 (Automatic background) (Session 2026-01-16-session-07, 2026-01-16)
- Fail-open for infrastructure errors, fail-closed for protocol violations (Session 2026-01-16-session-07, 2026-01-16)
- Multi-agent ADR review catches P0 structural violations - architect found 2 P0 MADR violations in Issue #357 that were invisible to single reviewer (Session 2026-01-16-session-07, Issue #357)
- Memory-first architecture (ADR-007): For agent-facing patterns (detection, routing, decision logic), document in Serena memory FIRST before writing executable code. Only create scripts if pattern cannot be executed by agent reasoning alone. Memory retrieval MUST precede reasoning to ensure cross-session context prevents repeated mistakes (Session 07, 2026-01-16)
  - Evidence: Session 42 - Created `Detect-CopilotFollowUpPR.ps1` and `detect-copilot-followup.sh` instead of documenting pattern in memory, violating memory-first mandate, 96% atomicity
- Distributed handoff architecture: Use read-only HANDOFF.md instead of centralized writes. Solved 80%+ merge conflicts, prevented exponential cost growth (ADR-014, Session 07, 2026-01-16)
- Thin workflows, testable modules: ALL logic in PowerShell scripts, workflows orchestrate only. 1-5 min feedback loop with workflows vs seconds with modules (ADR-006, Session 07, 2026-01-16)
- Role-specific tool allocation: 3-9 curated tools per agent role, not 58 tools for everyone. Reduces context bloat and improves focus (ADR-003, Session 07, 2026-01-16)

## Preferences (MED confidence)

These are preferences that SHOULD be followed:

- When fixing ADR-017 violations, preserve intuitiveness and keyword clustering (Session 2026-01-14, 2026-01-14)
- Database caching at local development tier (Tier 2) provides significant performance improvement (60-120s → 10-20s) (Session 2026-01-16-session-07, 2026-01-16)
- Non-blocking PostToolUse hooks with timeout (30s) for automatic tier (Session 2026-01-16-session-07, 2026-01-16)
- Educational warnings (3x) before blocking for protocol enforcement (Session 2026-01-16-session-07, 2026-01-16)
- Date-based counter reset for educational thresholds prevents permanent blocking (Session 2026-01-16-session-07, 2026-01-16)
- Template drift prevention: validate session logs match canonical template structure before commit (Session 2026-01-16-session-07, Session Protocol Mass Failure)
- Tiered memory index architecture: 82% token reduction for memory retrieval. Domain indexes enable targeted discovery (ADR-017, Session 07, 2026-01-16)
- Skills pattern superiority: 63-78% latency reduction vs PowerShell wrappers. Check skill inventory before using direct commands (ADR-030, Session 07, 2026-01-16)
- Leverage existing modules instead of duplicating functionality - reuse GitHubCore.psm1, GitHelpers.psm1, SchemaValidation.psm1 when implementing new features rather than creating parallel implementations (Session 379, 2026-01-11)
  - Evidence: Session evidence verification planning - identified existing modules could handle path validation, schema validation, and GitHub operations instead of creating new helper functions
- Fix error visibility first, then fix root cause - two-step debugging pattern for cryptic failures (Session 6, PR #954, 2026-01-16)
  - Evidence: Had to fix stderr suppression to see actual CodeQL errors, then could diagnose and fix missing parent directory issue
- Metadata-based cache validation for performance optimization - combine git HEAD SHA, config file hash, and script hashes to invalidate cache only when source changes (Session 05, 2026-01-15)
  - Evidence: CodeQL PostToolUse hook - validates cache using metadata object with GitHead + ConfigHash + ScriptsHash + ConfigDirHash, prevents unnecessary database rebuilds on every commit
- ADR review DISAGREE_AND_COMMIT verdict allows P1 non-blocking issues to defer to follow-up - production readiness doesn't require perfection (Session 382, 2026-01-16)
  - Evidence: ADR-041 review completed with 90% confidence DISAGREE_AND_COMMIT verdict. Implementation production-ready with one P1 non-blocking issue (PowerShell language coverage documentation inconsistency) tracked for follow-up commit
- 4-phase integration plan prioritizing high-value low-effort changes first - enables incremental rollout and iteration (Session 819, 2026-01-10)
  - Evidence: GitHub keywords integration plan - Phase 1+2 (3-5 hours) provide highest impact via validation infrastructure and agent prompt updates, Phase 3+4 (advanced features) deferred as optional
- Enhance existing skill infrastructure vs creating standalone skills - avoid premature abstraction, can extract later if complexity grows (Session 819, 2026-01-10)
  - Evidence: Test-PRDescription.ps1 designed as GitHub skill enhancement rather than standalone skill. Leverages existing github skill infrastructure, allows extraction to dedicated skill later if validation logic grows complex

## Edge Cases (MED confidence)

These are scenarios to handle:

- Exit code 2 signals BLOCKING to Claude (convention across all hooks) (Session 2026-01-16-session-07, 2026-01-16)
- Auto-trigger verification checkpoints prevent reactive work - ADR review should auto-trigger after ADR creation, not wait for manual invocation (Session 2026-01-16-session-07, Issue #357)

## Notes for Review (LOW confidence)

These are observations that may become patterns:

## History

| Date | Session | Type | Learning |
|------|---------|------|----------|
| 2026-01-14 | 2026-01-14 | MED | When fixing ADR-017 violations preserve intuitiveness and keyword clustering |
| 2026-01-16 | 2026-01-16-session-07 | HIGH | Multi-tier architecture pattern for tool integrations |
| 2026-01-16 | 2026-01-16-session-07 | HIGH | Fail-open for infrastructure errors, fail-closed for protocol violations |
| 2026-01-16 | 2026-01-16-session-07 | HIGH | Multi-agent ADR review catches P0 structural violations |
| 2026-01-16 | Session 07 | HIGH | Memory-first architecture: document patterns in memory before code |
| 2026-01-16 | Session 07 | HIGH | Distributed handoff architecture (ADR-014) |
| 2026-01-16 | Session 07 | HIGH | Thin workflows testable modules (ADR-006) |
| 2026-01-16 | Session 07 | HIGH | Role-specific tool allocation (ADR-003) |
| 2026-01-16 | 2026-01-16-session-07 | MED | Database caching at Tier 2 provides 3-5x performance improvement |
| 2026-01-16 | 2026-01-16-session-07 | MED | Non-blocking PostToolUse hooks with timeout for automatic tier |
| 2026-01-16 | 2026-01-16-session-07 | MED | Educational warnings (3x) before blocking |
| 2026-01-16 | 2026-01-16-session-07 | MED | Date-based counter reset for educational thresholds |
| 2026-01-16 | Session 07 | MED | Tiered memory index 82% token reduction (ADR-017) |
| 2026-01-16 | Session 07 | MED | Skills pattern 63-78% latency reduction (ADR-030) |
| 2026-01-16 | 2026-01-16-session-07 | MED | Exit code 2 signals BLOCKING to Claude |
| 2026-01-16 | 2026-01-16-session-07 | MED | Template drift prevention with pre-commit validation |
| 2026-01-16 | 2026-01-16-session-07 | MED | Auto-trigger verification checkpoints prevent reactive work |
| 2026-01-11 | Session 379 | MED | Leverage existing modules instead of duplicating functionality |
| 2026-01-16 | Session 6, PR #954 | MED | Fix error visibility first, then root cause |
| 2026-01-15 | Session 05 | MED | Metadata-based cache validation for performance optimization |
| 2026-01-16 | Session 382 | MED | ADR review DISAGREE_AND_COMMIT with P1 non-blocking deferred |
| 2026-01-10 | Session 819 | MED | 4-phase integration plan prioritizing high-value low-effort |
| 2026-01-10 | Session 819 | MED | Enhance existing skills vs creating new ones to avoid premature abstraction |

## Related

- [architecture-003-dry-exception-deployment](architecture-003-dry-exception-deployment.md)
- [architecture-015-deployment-path-validation](architecture-015-deployment-path-validation.md)
- [architecture-016-adr-number-check](architecture-016-adr-number-check.md)
- [architecture-adr-compliance-documentation](architecture-adr-compliance-documentation.md)
- [architecture-composite-action](architecture-composite-action.md)
- [architecture-model-selection](architecture-model-selection.md)
- [architecture-observations](architecture-observations.md)
- [architecture-producer-consumer](architecture-producer-consumer.md)
- [architecture-template-variant-maintenance](architecture-template-variant-maintenance.md)
- [architecture-tool-allocation](architecture-tool-allocation.md)
