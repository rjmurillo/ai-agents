# Execution Plan: Knowledge Integration into Skills and Agents

## Metadata

| Field | Value |
|-------|-------|
| **Status** | In Progress |
| **Created** | 2026-04-11 |
| **Owner** | orchestrator |
| **Complexity** | High |

## Objectives (Phase 1: Proof-First)

- [ ] Verify references/ auto-loading works in Claude Code (M0 probe)
- [ ] Baseline quality measured on 5 skills (30 prompts, scored)
- [ ] 20-30 high-value reference files created and injected
- [ ] After-injection quality measured with same prompts
- [ ] Kill gate decision made with evidence
- [ ] All reference files under 8KB, all skill totals under 40KB
- [ ] No SKILL.md exceeds 500 lines
- [ ] Summarization methodology and naming conventions documented

## Decision Log

| Date | Decision | Rationale | Alternatives Considered |
|------|----------|-----------|------------------------|
| 2026-04-11 | Per-skill references/ only, no shared .agents/knowledge/ | Discoverability, each skill owns its references | Shared .agents/knowledge/ dir (rejected: search ambiguity) |
| 2026-04-11 | Summarized LLM-optimized format, not pipe-delimited | Preserves semantic fidelity better than pipe-delimited | Pipe-delimited (rejected: strips narrative structure), raw copy (rejected: too large) |
| 2026-04-11 | Triage Modernization for non-internal .NET content | Valuable .NET patterns worth including | Quarantine all (rejected: loses useful content) |
| 2026-04-11 | Import all Osmani and gstack skills as resources | Broadens agent knowledge base | Selective import (rejected: user wants comprehensive import) |
| 2026-04-11 | Use SkillForge for new skills when no existing skill fits | Consistent skill creation with validation | Manual skill creation (rejected: no validation) |
| 2026-04-11 | Smoke tests written BEFORE summarization, not after | Tests fidelity by comparing against known expected answers | Post-injection tests (rejected: tests recall not fidelity) |

## Milestones (Revised: Proof-First)

| # | Name | Effort | Dependencies | Status |
|---|------|--------|-------------|--------|
| M0 | Probe Test (references/ auto-loading) | 1 hour | None | COMPLETE |
| M1 | Baseline Measurement (5 skills, 30 prompts) | Half day | M0 | COMPLETE |
| M2 | Resource Selection + Creation (22 files) | 2 days | M1 | COMPLETE |
| M3 | After-Injection + Kill Gate | Half day | M2 | COMPLETE (PROCEED) |
| M4 | Scale Decision (contingent) | TBD | M3 pass | READY |

Critical path: M0 + M1 + M2 + M3 = 3 days to kill gate.

## Key Artifacts

| Artifact | Path |
|----------|------|
| Spec | `.agents/planning/SPEC-knowledge-integration.md` |
| Plan (detailed) | `.agents/planning/004-knowledge-integration-plan.md` |
| Tasks | `.agents/planning/TASKS-004-knowledge-integration.md` |
| Wiki manifest | `.agents/planning/wiki-manifest.csv` (to be created) |

## Progress Log

| Date | Update | Agent |
|------|--------|-------|
| 2026-04-11 | Created spec, plan, and task breakdown. Resolved 4 open questions. Expanded scope to 3 sources (wiki + Osmani + gstack). | orchestrator |
| 2026-04-11 | /autoplan review: CEO (6/6 consensus), Eng (4/6), DX (5/5). Plan revised from bulk import (283 files) to proof-first (20-30 files with kill gate). Key fixes: references/ not resources/, agents removed from target list, M0 probe test added, summarization methodology required before M2, naming conventions and size enforcement added. 15 auto-decisions, 1 user challenge resolved. | autoplan |
| 2026-04-11 | M0-M3 complete. 22 reference files created across 5 skills. Kill gate PROCEED: +1.6 avg delta, 5/5 skills improved, 0 regressions. Biggest impact: golden-principles (+2.5, from scope-mismatched 2.2 to functional 4.7). PR #1614 open. Phase 2 (scale to remaining content) now READY. | implementer |

## Blockers

- None

## Related

- Spec: `.agents/planning/SPEC-knowledge-integration.md`
- Prior plan (superseded): `.agents/planning/2026-04-11-wiki-knowledge-integration-plan.md`
- Prior tasks (superseded): `.agents/planning/TASKS-wiki-knowledge-integration.md`
