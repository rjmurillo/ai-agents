# ADR Debate Log: Skill Phase Gates → Routing-Level Enforcement

## Summary

- **Original ADR**: ADR-032: Skill Phase Gates
- **Final ADR**: ADR-033: Routing-Level Enforcement Gates
- **Rounds**: 2 (Phase 1 independent review + Phase 2 consolidation/resolution)
- **Outcome**: PIVOT - Original ADR superseded, new ADR created at correct abstraction layer
- **Final Status**: ADR-032 superseded, ADR-033 proposed

## Phase 0: Related Work Research

### Critical Finding: ADR Numbering Conflict

PR #557 (OPEN) already claims ADR-032 for "Exit Code Standardization"

### Related Issues Identified

| Issue | Title | Relevance |
|-------|-------|-----------|
| #265 | Pre-PR Validation EPIC | Directly addresses same problem domain |
| #258 | QA pre-PR quality gate | Being completed by PR #562 |
| #219 | Session State MCP | Protocol enforcement infrastructure |

## Phase 1: Independent Reviews

### Agent Positions

| Agent | Verdict | Key Argument |
|-------|---------|--------------|
| Architect | NEEDS_CHANGES | P0 numbering conflict, MADR non-compliance |
| Critic | NEEDS_REVISION | Evidence gaps, soft enforcement risk |
| Independent-thinker | CONDITIONAL | Wrong abstraction layer - problem is agent-level |
| Security | CONDITIONAL | "ACK in thoughts" provides zero security |
| Analyst | NEEDS_REVISION | 60% baseline statistically invalid (n=8) |
| High-level-advisor | WITHDRAW | Complete EPIC #265 first |

### Consensus Points

1. ADR numbering conflict is P0 blocker (all 6 agents)
2. Problem is real (PR #226, protocol violations) (all 6 agents)
3. "ACK in thoughts" is weak enforcement (3 agents)

### Conflicts Identified

| Conflict | Positions |
|----------|-----------|
| Scope alignment | Skill-level (architect/critic) vs Agent-level (independent-thinker/HLA) |
| EPIC #265 overlap | Coordinate (analyst) vs Complete first (HLA) |
| Evidence quality | Sufficient (ADR) vs Insufficient (analyst) |

## Phase 2: Consolidation

### Conflict Resolution (High-Level-Advisor)

**Conflict 1: Scope Alignment**
- **Winner**: Independent-thinker/HLA position
- **Rationale**: PR #226 retrospective explicitly states agent bypassed ALL protocols, not just skill-internal steps

**Conflict 2: EPIC #265 Overlap**
- **Winner**: Modified - proceed but acknowledge #265
- **Rationale**: PR #562 completing #265; hooks complement agent-level enforcement

**Conflict 3: Evidence Quality**
- **Winner**: Analyst position acknowledged
- **Rationale**: 60% statistic retained as approximate; formal baseline to be established

### New Context: vexjoy "Do Router"

User provided additional context: https://vexjoy.com/posts/the-do-router/

Key insight: "Over-routing is cheap. Under-routing compounds."

This supports routing-level enforcement over skill-internal gates.

## Phase 3: Resolution

### Decision: PIVOT to ADR-033

Instead of withdrawing, the debate produced a **better ADR**:

| Aspect | ADR-032 (Original) | ADR-033 (Revised) |
|--------|-------------------|-------------------|
| Layer | Skill-internal | Routing-level |
| Mechanism | Documentation + ACK | Claude hooks (exit code 2) |
| Enforcement | Trust-based | Deterministic |
| Bypass risk | High | Near-zero |

### Changes Made

1. Created ADR-033: Routing-Level Enforcement Gates
2. Marked ADR-032 as superseded
3. Updated governance docs to reference both
4. Incorporated "Do Router" principles
5. Added Claude hooks implementation details

## Agent Positions After Resolution

| Agent | Position | Notes |
|-------|----------|-------|
| Architect | Pending convergence | ADR-033 needs review |
| Critic | Pending convergence | ADR-033 addresses concerns |
| Independent-thinker | Accept (expected) | Correct layer now |
| Security | Pending convergence | Hook enforcement is secure |
| Analyst | Pending convergence | Evidence still needs baseline |
| High-level-advisor | Disagree-and-Commit | Preferred EPIC #265 first |

## Key Learnings

### 1. Abstraction Layer Matters

The debate revealed a fundamental scope mismatch. Skill-internal gates don't help when agents bypass skills entirely.

### 2. vexjoy Patterns Have Merit

Both "Everything Deterministic" and "Do Router" informed the final design. The insight about routing-level enforcement came from combining these with our failure evidence.

### 3. Multi-Agent Debate Works

6 agents with different perspectives produced a better outcome than single-agent analysis would have.

### 4. Evidence Quality Scrutiny

Analyst's challenge to the 60% baseline forced acknowledgment of statistical limitations.

## Artifacts Created

| Artifact | Path | Status |
|----------|------|--------|
| Original ADR | ~~`.agents/architecture/ADR-032-skill-phase-gates.md`~~ | Deleted (ADR-032 reserved for exit codes per PR #557) |
| Revised ADR | `.agents/architecture/ADR-033-routing-level-enforcement-gates.md` | Active |
| Governance (gates) | `.agents/governance/SKILL-PHASE-GATES.md` | Active |
| Governance (criteria) | `.agents/governance/SKILL-CREATION-CRITERIA.md` | Active |
| Debate log | `.agents/critique/ADR-032-033-debate-log.md` | Active |

## Next Steps

1. **Phase 4**: Run convergence check on ADR-033
2. **Implementation**: Create `.claude/hooks/enforce-routing-gates.py`
3. **Integration**: Coordinate with PR #562 (completing EPIC #265)
4. **Validation**: Establish baseline metrics before enforcement

---

*Debate conducted: 2025-12-30*
*Participating agents: architect, critic, independent-thinker, security, analyst, high-level-advisor*
*Orchestrator: Main session*
