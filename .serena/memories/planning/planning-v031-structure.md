# v0.3.1 Planning Structure

**Date**: 2026-02-08
**Context**: PowerShell-to-Python migration milestone planning
**Authority**: ADR-042 (Python-first migration strategy)

## Plan Location

`.agents/planning/v0.3.1/PLAN.md` - Comprehensive 12-month migration plan

## Structure

**Based on**: v0.3.0 PLAN.md format (proven agent-ready structure)

### Key Sections

1. **Quick Start**: Agent work assignment with 5 parallel tracks
2. **Agent Quick Context**: Token-efficient summary with P0 blockers
3. **Dependency Flowchart**: Mermaid diagram showing issue dependencies
4. **Gantt Timeline**: 12-month schedule with phase overlaps
5. **Critical Path**: Shared modules (#1053) blocking 50+ consumer scripts
6. **Phase Breakdown**: P0-P5 with detailed checklists
7. **Parallel Execution Plan**: Worktree setup, instance allocation, merge strategy
8. **Migration Checklist**: Per-script template with exit criteria

## Track Structure (5 Tracks)

| Track | Issues | Duration | Critical Path? |
|-------|--------|----------|----------------|
| A: Cleanup | #1050-#1052 | 2 months | Enables Track B |
| B: Modules+Scripts | #1053-#1055 | 2 months | **YES - Blocks C, D, E** |
| C: CI Infrastructure | #1056-#1058 | 2 months | No |
| D: Skills | #1060-#1062 | 3 months | No |
| E: Long Tail | #1063-#1066 | 4 months | No |

## Critical Path: #1053 (Shared Modules)

**Why critical**: 5 PowerShell modules block 50+ consumer scripts

| Module | Consumers | Blocks |
|--------|-----------|--------|
| GitHubCore.psm1 | 23 scripts | #1055, #1060 |
| AIReviewCommon.psm1 | 3 workflows | #1054, #1056, #1057 |
| HookUtilities.psm1 | 12 hooks | #1065 |

**Migration order**: GitHubCore first (highest consumer count)

## Design Decisions

1. **No deprecation period**: Delete PS1 immediately after Python passes tests
2. **Expand-contract**: Add Python, verify, delete PS1 (zero dual maintenance)
3. **Module pattern**: Python packages with `__init__.py`
4. **Naming**: snake_case for .py (PEP 8 compliance)
5. **Test parity**: pytest coverage >= Pester coverage (per-script requirement)

## Success Metrics

| Metric | Target |
|--------|--------|
| PowerShell files remaining | 0 |
| pytest coverage | >= Pester |
| CI failures during migration | 0 |
| Pester workflow status | Retired |
| PSScriptAnalyzer workflow status | Retired |

## Agent Readiness

**Immediate actions for agents**:
1. Read `.agents/planning/v0.3.1/PLAN.md`
2. Check Track Status Tracker for available work
3. Use worktree setup commands for parallel execution
4. Start with Track A (#1050) if no other work in progress

## Related

- ADR-042: Python migration strategy (accepted)
- ADR-005: PowerShell-only scripting (superseded)
- Epic #1049: PowerShell-to-Python migration
- Milestone v0.3.1: https://github.com/rjmurillo/ai-agents/milestone/7
