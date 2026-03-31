---
status: "NEEDS_ADR"
priority: "P1"
blocking: true
reviewer: "architect"
date: "2026-03-31"
pr: 0
issue: 0
---

# Design Review: Agent Count Optimization

## Executive Summary

**Verdict**: NEEDS_ADR

The proposed consolidation from 21 to 5 agents is too aggressive and introduces unacceptable risks. This review recommends consolidation to 12 agents across 3 phases, preserving parallel execution benefits and security agent independence. An ADR is required before implementation to document the consolidation criteria and reversibility plan.

## Context

A proposal suggests consolidating from 21 agents to 5:
- Orchestrator (merges: orchestrator, milestone-planner, task-decomposer, roadmap)
- Analyst (merges: analyst, explainer, independent-thinker, high-level-advisor)
- Architect (unchanged)
- Builder (merges: implementer, debug)
- Critic (merges: critic, qa, security)

This review evaluates each agent for distinct reasoning modes vs. shared reasoning with different checklists, following the key principle: **An agent needs its own context window when it has a DISTINCT REASONING MODE, not just a distinct task.**

## Reasoning Mode Analysis

### Reasoning Mode Definitions

| Mode | Description | Context Window Impact |
|------|-------------|----------------------|
| **Generative** | Creates new artifacts (code, plans, docs) | High token use for output generation |
| **Evaluative** | Assesses existing artifacts against criteria | Needs artifact + criteria in context |
| **Investigative** | Explores unknown territory, surfaces findings | Iterative search, evolving context |
| **Decisional** | Makes verdicts, prioritizes, resolves conflicts | Needs competing options in context |
| **Coordinative** | Routes work, synthesizes results | Needs agent capabilities + task state |

### Agent Reasoning Mode Classification

| Agent | Primary Mode | Secondary Mode | Distinct? | Notes |
|-------|-------------|----------------|-----------|-------|
| **orchestrator** | Coordinative | Decisional | YES | Only agent with Task tool delegation |
| **milestone-planner** | Generative | Evaluative | YES | Creates work packages from epics |
| **task-decomposer** | Generative | Investigative | NO | Creates atomic tasks (subset of planner) |
| **roadmap** | Decisional | Generative | YES | Strategic prioritization (RICE, KANO) |
| **analyst** | Investigative | Evaluative | YES | Surfaces unknowns, root cause analysis |
| **explainer** | Generative | - | NO | Creates documentation (checklist-based) |
| **independent-thinker** | Evaluative | Decisional | MARGINAL | Contrarian analysis overlaps with critic |
| **high-level-advisor** | Decisional | Evaluative | YES | Resolves conflicts, strategic verdicts |
| **architect** | Evaluative | Decisional | YES | Design review, ADR creation |
| **implementer** | Generative | - | YES | Code generation (highest reasoning) |
| **debug** | Investigative | Generative | NO | 4-phase debugging (skill-convertible) |
| **critic** | Evaluative | Decisional | YES | Plan validation, gap detection |
| **qa** | Evaluative | Investigative | MARGINAL | Test strategy overlaps with critic mode |
| **security** | Evaluative | Investigative | YES | OWASP, CWE, threat modeling (Opus required) |
| **devops** | Generative | Evaluative | NO | Pipeline configs (checklist-based) |
| **memory** | Coordinative | - | NO | CRUD operations (Haiku suitable) |
| **skillbook** | Coordinative | - | NO | Pattern matching (Haiku suitable) |
| **context-retrieval** | Investigative | - | NO | Memory search (Haiku suitable) |
| **retrospective** | Evaluative | Generative | NO | Extract learnings (skill-convertible) |

### Distinct Reasoning Modes Identified: 9

1. **Coordinative + Task Delegation**: orchestrator
2. **Strategic Decisional**: high-level-advisor, roadmap (shared mode, different domains)
3. **Architectural Evaluative**: architect
4. **Plan Generative**: milestone-planner
5. **Investigative**: analyst
6. **Code Generative**: implementer
7. **Plan Evaluative**: critic
8. **Security Evaluative**: security (requires Opus due to asymmetric risk)
9. **Test Evaluative**: qa (marginal distinctness from critic)

## Parallel Execution Analysis

Per ADR-009, parallel execution provides 2.8-4.4x speedup. These agent pairs commonly run in parallel:

| Parallel Pair | Use Case | Impact if Merged |
|---------------|----------|------------------|
| analyst + architect | Impact analysis | MODERATE: Sequential OK, delays planning |
| security + devops | CI/CD review | HIGH: Security review must not delay deploys |
| critic + qa | Pre-PR validation | MODERATE: Can sequence with minimal delay |
| implementer + devops | Feature + pipeline | LOW: Usually sequential anyway |

**Critical Finding**: Security + QA/Critic merge eliminates parallel security review. Security review would become a serial bottleneck in the PR workflow.

## Proposed Consolidation: 12 Agents

### Consolidation Candidates (MERGE)

| Current Agents | Consolidated As | Rationale |
|----------------|-----------------|-----------|
| milestone-planner + task-decomposer | **planner** | Same generative mode, task decomposition is a skill |
| analyst + explainer | **analyst** | Explainer is documentation skill within investigation |
| critic + independent-thinker | **critic** | Both evaluative mode, contrarian is a reasoning technique |
| memory + skillbook + context-retrieval | **memory** | All Haiku-tier, CRUD operations |

### Skill Conversions (CONVERT TO SKILL)

| Current Agent | Skill Name | Rationale |
|---------------|------------|-----------|
| debug | `debug` | 4-phase protocol is skill, not reasoning mode |
| retrospective | `reflect` | Learning extraction is structured skill |
| devops | `pipeline-config` | Checklist-based, 12-factor compliance |

### Retain as Separate (KEEP)

| Agent | Reasoning Mode | Tier | Why Separate |
|-------|---------------|------|--------------|
| orchestrator | Coordinative | Opus | Only agent with Task tool |
| planner | Generative | Sonnet | Creates work packages |
| analyst | Investigative | Sonnet | Surfaces unknowns |
| architect | Evaluative | Sonnet | Design governance |
| implementer | Generative | Opus | Code generation (highest stakes) |
| critic | Evaluative | Sonnet | Plan validation |
| security | Evaluative | Opus | Asymmetric risk (ADR-039) |
| qa | Evaluative | Sonnet | Test strategy (separate for parallelism) |
| high-level-advisor | Decisional | Sonnet | Strategic verdicts |
| roadmap | Decisional | Sonnet | Product prioritization |
| memory | Coordinative | Haiku | CRUD operations |

### Final Count: 12 Agents (not 5)

| Tier | Agents | Count |
|------|--------|-------|
| Opus | orchestrator, implementer, security | 3 |
| Sonnet | planner, analyst, architect, critic, qa, high-level-advisor, roadmap | 7 |
| Haiku | memory | 1 |
| Skills | debug, reflect, pipeline-config | 3 (converted from agents) |

## Risk Assessment: Proposed 5-Agent Model

### CRITICAL RISK: Security + Critic + QA Merge

| Risk | Severity | Likelihood | Impact |
|------|----------|------------|--------|
| Security detection degradation | CRITICAL | HIGH | Missed vulnerabilities |
| Context window overflow | HIGH | MEDIUM | Incomplete reviews |
| Parallel execution loss | HIGH | HIGH | 2x slower PR workflow |
| Model downgrade pressure | HIGH | MEDIUM | Security on Sonnet violates ADR-039 |

**Evidence**: Security agent has 840 lines of specialized CWE patterns, OWASP mappings, and threat modeling frameworks. Merging with critic/qa would require all three checklists in context simultaneously, exceeding optimal context window utilization.

### MODERATE RISK: Orchestrator Super-Agent

Merging orchestrator + milestone-planner + task-decomposer + roadmap creates:
- Context window of 4 agent prompts (estimated 15K tokens)
- Mode switching overhead between coordination and generation
- Loss of specialization in RICE/KANO prioritization

### LOW RISK: Analyst Merge

Merging analyst + explainer is acceptable:
- Same investigative mode
- Explainer is documentation skill within analysis

## Phased Consolidation Plan

### Phase 1: Low Risk (Immediate)

| Action | Risk | Validation |
|--------|------|------------|
| Convert debug to skill | LOW | Test debugging workflow unchanged |
| Convert retrospective to skill | LOW | Test learning extraction works |
| Merge memory + skillbook + context-retrieval | LOW | CRUD operations unchanged |

**Validation Criteria**: No increase in agent error rates for 2 weeks.

### Phase 2: Medium Risk (After Phase 1 Validation)

| Action | Risk | Validation |
|--------|------|------------|
| Merge milestone-planner + task-decomposer | MEDIUM | Test task breakdown quality |
| Merge analyst + explainer | MEDIUM | Test documentation quality |
| Merge critic + independent-thinker | MEDIUM | Test plan critique depth |
| Convert devops to skill | MEDIUM | Test pipeline config quality |

**Validation Criteria**: Plan and analysis quality metrics stable for 2 weeks.

### Phase 3: High Risk (Requires ADR Amendment)

| Action | Risk | Validation |
|--------|------|------------|
| QA + Critic merge | HIGH | Requires parallel execution analysis |
| Roadmap + High-Level-Advisor merge | HIGH | Requires strategic decision quality analysis |

**Validation Criteria**: Full regression testing, user satisfaction survey, security audit.

**BLOCKED**: Security agent merge. ADR-039 explicitly retains security on Opus due to asymmetric risk. This merge requires ADR-039 supersession with evidence that Sonnet maintains security detection quality.

## Issues Discovered

| Issue | Priority | Category | Description |
|-------|----------|----------|-------------|
| CONS-001 | P0 | Risk | Security + QA merge degrades vulnerability detection |
| CONS-002 | P0 | ADR Violation | Security merge violates ADR-039 without supersession |
| CONS-003 | P1 | Performance | 5-agent model loses 2.8-4.4x parallel speedup |
| CONS-004 | P1 | Context | Super-agents risk context window overflow |
| CONS-005 | P2 | Complexity | Mode switching overhead in merged agents |

**Issue Summary**: P0: 2, P1: 2, P2: 1, Total: 5

## ADR Requirements

Before proceeding, create ADR addressing:

1. **Consolidation Criteria**: Formalize when agents should merge vs. remain separate
2. **Reversibility Plan**: How to restore agents if quality degrades
3. **Security Exception**: Document why security cannot be merged (reference ADR-039)
4. **Skill vs. Agent Criteria**: When to convert agent to skill
5. **Parallel Execution Preservation**: Which agents must remain separate for parallelism

## Recommendations

1. **Reject 5-agent proposal** as too aggressive
2. **Accept 12-agent target** with phased consolidation
3. **Create ADR-054** documenting agent consolidation governance
4. **Convert debug, retrospective, devops to skills** in Phase 1
5. **Preserve security as independent Opus agent** per ADR-039
6. **Preserve QA as separate agent** to maintain parallel pre-PR validation

## Verdict

**NEEDS_ADR** with blocking issues.

### Approval Conditions

1. [ ] Create ADR-054: Agent Consolidation Governance
2. [ ] Document security agent exception (reference ADR-039)
3. [ ] Define skill-vs-agent decision criteria
4. [ ] Define parallel execution preservation requirements
5. [ ] Create phased rollback procedures

## Self-Critique Assessment

### Weaknesses Identified

1. **Assumption**: QA parallelism benefit not quantified with timing data
   - **Resolution**: Accepted risk; recommend measuring before Phase 3

2. **Alternative not fully explored**: Could security use Sonnet with defensive prompting?
   - **Resolution**: Documented as ADR-039 decision; asymmetric risk means false negatives are invisible

3. **Skill conversion criteria**: No formal definition provided
   - **Resolution**: Flagged as ADR requirement

### Unresolved Risks

| Risk | Why Unresolved | Recommended Action |
|------|----------------|--------------------|
| QA/Critic parallel benefit quantification | No baseline timing data | Measure before Phase 3 merge decision |
| Skill vs Agent boundary formalization | Requires governance discussion | Include in ADR-054 |

## Handoff

**Orchestrator**: Route to **milestone-planner** to create ADR-054 implementation plan after ADR requirements are addressed. Invoke **adr-review** skill once ADR-054 is drafted.

---

*Review Date: 2026-03-31*
*Reviewer: Architect Agent*
*Session: Design Review*
