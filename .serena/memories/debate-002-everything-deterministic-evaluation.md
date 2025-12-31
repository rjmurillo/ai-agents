# Debate 002: Everything Deterministic Philosophy Evaluation

**Date**: 2025-12-30
**Source**: https://vexjoy.com/posts/everything-that-can-be-deterministic-should-be-my-claude-code-setup/
**Verdict**: APPROVE WITH CONDITIONS
**Critique**: `.agents/critique/001-everything-deterministic-philosophy-evaluation.md`

## Overview

Evaluated vexjoy's "Everything Deterministic" philosophy (Router → Agent → Skill → Programs) for adoption in ai-agents system. Found 80% overlap with existing patterns, 20% valuable gap.

## Key Findings

### 80% Overlap (Already Implemented)

1. **Deterministic Programs**: ADR-005 (PowerShell-only), 32 skills in `.claude/skills/github/`
2. **Domain Separation**: 19 specialized agents with knowledge, not methodology
3. **Context Density**: ADR-003 reduced tools from 58 blanket to 3-9 role-specific
4. **Phase Gates**: Critic gate (before merge), QA gate (after code changes)

### 20% Gap (Valuable Additions)

1. **Router Layer**: Orchestrator combines routing + coordination (63KB bloat)
2. **Phase Gates Within Agents**: Currently only BETWEEN agents, not WITHIN workflows
3. **Skill Creation Criteria**: Implicit "solved vs unsolved" classification

## Architecture Comparison

| Layer | vexjoy | Our Current | After Adoption |
|-------|--------|-------------|----------------|
| Router | Separate | Orchestrator 63KB | router.md 10KB |
| Agent | 35 agents, 234MB | 19 agents, 424KB | 20 agents (add router) |
| Skill | 68 skills | 32 PowerShell scripts | 32+ (no change) |
| Programs | Wraps system calls | PowerShell modules | PowerShell modules |

## Failure Mode Analysis

**Our Actual Failures** (from retrospectives):
- Protocol violations: 60% CRITICAL_FAIL (PR #226)
- Skill bypasses: 3+ per session (Session 15)
- Scope explosions: 17x line count (PR #395)
- Security misses: 1 HIGH (CWE-20/78, PR #211)

**vexjoy Prevention**:
- Protocol violations: NO
- Skill bypasses: YES (indirect invocation)
- Scope explosions: PARTIAL (phase gates)
- Security misses: NO

**Critical Insight**: Philosophy prevents skill bypass but NOT our top 3 failure modes.

## Conditions for Adoption

1. **Router Split**: Must demonstrate measurable benefit (token reduction, routing accuracy improvement) before migration
2. **Phase Gates**: Document for analyst, planner, retrospective with enforcement mechanism
3. **Skill Criteria**: Document in `.agents/governance/SKILL-CREATION-CRITERIA.md`
4. **Indirect Invocation**: REJECT - strengthen existing skill-usage-mandatory protocol instead

## Critical Issues Identified

### Issue 1: Missing Router Layer

**Problem**: Orchestrator is 63KB - 26% larger than next largest (50KB)

**Root Cause**: Combines routing (task classification) and coordination (workflow management)

**Solution**: Split into router.md (10KB) + orchestrator.md (30KB)

**Timeline**: Phase 1.6

### Issue 2: Informal Phase Gates

**Problem**: Phase gates exist BETWEEN agents, not WITHIN agent workflows

**Evidence**: No enforcement preventing analyst from skipping verification step (observed in PR #226)

**Solution**: Document and enforce phase gates for complex agents:

```markdown
## Analyst Workflow

1. GATHER - Collect data
2. VERIFY - Confirm accuracy
3. ANALYZE - Identify root cause
4. VALIDATE - Cross-check with experts

BLOCKING: Do NOT proceed to ANALYZE until VERIFY confirms accuracy
```

**Timeline**: Phase 1.6

### Issue 3: No Skill Creation Criteria

**Problem**: Implicit understanding of when to create skill vs expand agent

**Solution**: Document classification:

**SOLVED PROBLEMS** (create skill):
- File search (ripgrep patterns)
- Test execution (Pester with parameters)
- API calls (GitHub API structure)
- Parsing (YAML/JSON with schema)

**UNSOLVED PROBLEMS** (expand agent):
- Diagnosis (interpretation)
- Root cause analysis (context)
- Design decisions (trade-offs)
- Strategic planning (cross-system)

**Timeline**: Phase 1.5 (documentation-only)

## Recommendations

### Adopt: Router/Agent Separation

**Action**: Split orchestrator.md into router.md + orchestrator.md

**Evidence**: Proven pattern, addresses 63KB bloat

**Risk**: Migration effort, routing quality regression

### Adopt: Phase Gate Documentation

**Action**: Document phase gates for analyst, planner, retrospective

**Evidence**: Prevents skipped steps (PR #226 autonomous execution)

**Risk**: Adds complexity, may slow simple analyses

### Reject: Indirect Skill Invocation

**Action**: Keep agents invoking skills directly

**Rationale**: No evidence that direct invocation causes failures. Failures are from BYPASSING skills, not MISUSING them.

**Alternative**: Strengthen pre-commit hook WARNING → BLOCKING for skill violations

### Adopt: Skill Creation Criteria

**Action**: Create `.agents/governance/SKILL-CREATION-CRITERIA.md`

**Evidence**: vexjoy's explicit classification prevents ambiguity

**Risk**: None - clarifies existing practice

## Numeric Evidence

### Verified Facts

| Fact | Value | Source |
|------|-------|--------|
| Agent count | 19 | `src/claude/*.md` file count |
| Skill count | 32 PowerShell scripts | `.claude/skills/github/scripts/` |
| Context size | 424KB | `du -sh src/claude/` |
| Orchestrator size | 63KB | `ls -lh src/claude/orchestrator.md` |
| Next largest agent | 50KB (pr-comment-responder) | `ls -lh src/claude/` |
| Protocol violation rate | 60% CRITICAL_FAIL | Memory: `autonomous-execution-guardrails-lessons` |
| Skill bypass frequency | 3+ per session | Memory: `session-init-skill-validation` |
| Scope explosion factor | 17x line count | Memory: `orchestration-copilot-swe-anti-patterns` |
| Security miss count | 1 HIGH (CWE-20/78) | Retrospective 2025-12-27 |

### Architecture Metrics

| Metric | Before | After Adoption |
|--------|--------|----------------|
| Total agents | 19 | 20 (add router) |
| Orchestrator size | 63KB | router 10KB + orchestrator 30KB |
| Context overhead | 424KB | 434KB (+2.4%) |
| Phase gate enforcement | BETWEEN agents | WITHIN + BETWEEN |

## Related Artifacts

- **Critique**: `.agents/critique/001-everything-deterministic-philosophy-evaluation.md`
- **Session Log**: `.agents/sessions/2025-12-30-session-01-determinism-debate.md`
- **vexjoy Blog**: https://vexjoy.com/posts/everything-that-can-be-deterministic-should-be-my-claude-code-setup/
- **ADR-003**: Agent Tool Selection Criteria
- **ADR-005**: PowerShell-only scripting
- **SESSION-PROTOCOL**: `.agents/SESSION-PROTOCOL.md` v1.4

## Skills Referenced

- `architecture-tool-allocation` - Role-specific tool allocation pattern
- `autonomous-execution-guardrails-lessons` - Protocol violation patterns
- `session-init-skill-validation` - Skill bypass detection
- `orchestration-copilot-swe-anti-patterns` - Scope explosion patterns

## Next Steps

1. **Phase 1.5**: Document skill creation criteria
2. **Phase 1.6**: Split router from orchestrator (require proof of benefit first)
3. **Phase 1.6**: Document phase gates for analyst, planner, retrospective
4. **Phase 1.7**: Strengthen skill violation enforcement (WARNING → BLOCKING)

## Verdict Summary

**APPROVE WITH CONDITIONS** because:

1. 80% overlap - core patterns already implemented
2. 20% gap (Router split, phase gates) addresses real issues (bloat, skipped steps)
3. Evidence-based adoption - require Router split performance proof
4. Reject unnecessary complexity - indirect invocation adds failure points

**The philosophy is sound, but wholesale adoption would be over-engineering. Targeted adoption of missing pieces provides value without disruption.**
