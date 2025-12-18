---
title: Agent System Documentation
version: 2.0
last_updated: 2025-12-17
maintainer: orchestrator
---

# Multi-Agent Orchestration System

## 1. Executive Summary

### Purpose

This multi-agent system coordinates specialized AI agents for software development tasks. Each agent has deep expertise in a specific domain, enabling high-quality outputs through division of labor and explicit quality gates.

### Key Benefits

| Benefit | Description |
|---------|-------------|
| **Specialization** | Each agent excels at one thing rather than being mediocre at many |
| **Quality Gates** | Critic and QA agents validate work before it proceeds |
| **Knowledge Persistence** | Memory system preserves learnings across sessions |
| **Clear Handoffs** | Explicit protocols prevent context loss between agents |
| **Traceability** | All decisions documented in `.agents/` directories |

### Quick Start

```python
# For complex tasks, start with orchestrator
Task(subagent_type="orchestrator", prompt="Implement user authentication feature")

# For specific domain work, invoke directly
Task(subagent_type="implementer", prompt="Fix null check in UserService.cs")
Task(subagent_type="analyst", prompt="Investigate API latency issues")
```

### Agent Count

This system includes **18 specialized agents** organized into 5 categories.

---

## 2. Agent Catalog

### 2.1 Coordination Agents

#### orchestrator

**File**: `src/claude/orchestrator.md`

**Role**: Central coordinator routing tasks to appropriate specialists

**Specialization**: Task analysis, agent selection, workflow management

**Input**:
- User request or task description
- Context from previous work (optional)

**Output**:
- Delegated work to appropriate agents
- Coordinated multi-agent workflows
- Final results aggregation

**Delegates To**: All agents (based on task analysis)

**Called By**: User (entry point), pr-comment-responder

**When to Use**:
- Complex multi-step tasks requiring multiple specialists
- When unsure which agent to use
- Tasks requiring coordination across domains

**Example Invocation**:
```text
@orchestrator Implement a rate limiting feature for the API endpoints.
Include security review and test coverage.
```

---

#### planner

**File**: `src/claude/planner.md`

**Role**: Creates milestones and work packages from epics and PRDs

**Specialization**: Task decomposition, dependency analysis, milestone definition

**Input**:
- Epic or PRD document
- Technical constraints
- Business requirements

**Output**:
- Milestone definitions with goals
- Work packages with dependencies
- Impact analysis requests to specialists

**Delegates To**: analyst, architect, qa, devops, security (for impact analysis)

**Called By**: orchestrator, roadmap

**When to Use**:
- Breaking down epics into implementable chunks
- Creating project milestones
- Understanding work dependencies

**Example Invocation**:
```text
@planner Break down EPIC-001 (User Authentication) into milestones
with clear acceptance criteria and dependencies.
```

---

#### task-generator

**File**: `src/claude/task-generator.md`

**Role**: Creates atomic tasks with acceptance criteria from milestones

**Specialization**: Task atomization, complexity estimation, sequencing

**Input**:
- Milestone or work package from planner
- PRD requirements

**Output**:
- Atomic task definitions (TASK-NNN format)
- Acceptance criteria per task
- Complexity estimates (XS/S/M/L/XL)
- Dependency graph

**Delegates To**: None (returns to orchestrator)

**Called By**: orchestrator, planner

**When to Use**:
- After PRD or milestone is created
- When breaking work into assignable units
- Generating implementation-ready task lists

**Example Invocation**:
```text
@task-generator Generate atomic tasks from the Authentication milestone.
Include complexity estimates and file impact.
```

---

### 2.2 Implementation Agents

#### implementer

**File**: `src/claude/implementer.md`

**Role**: Writes production-quality code following established patterns

**Specialization**: C#, .NET, test-driven development, SOLID principles

**Input**:
- Task specification with acceptance criteria
- Design decisions from architect
- Steering file context

**Output**:
- Implementation code
- Unit tests (100% coverage target)
- Documentation updates

**Delegates To**: None (returns to orchestrator)

**Called By**: orchestrator, planner

**When to Use**:
- Writing new code for defined tasks
- Fixing bugs with clear reproduction steps
- Refactoring with architect guidance

**Example Invocation**:
```text
@implementer Implement the GetUserPreferences method as specified in TASK-042.
Follow the design in ADR-015. Ensure 100% test coverage.
```

---

#### devops

**File**: `src/claude/devops.md`

**Role**: Designs CI/CD pipelines and deployment automation

**Specialization**: GitHub Actions, Azure Pipelines, MSBuild, infrastructure

**Input**:
- Pipeline requirements
- Deployment targets
- Infrastructure constraints

**Output**:
- Pipeline configurations (YAML)
- Build scripts
- Infrastructure documentation in `.agents/devops/`

**Delegates To**: None (returns to orchestrator)

**Called By**: orchestrator, planner

**When to Use**:
- Modifying `.github/workflows/`
- Configuring build systems
- Managing deployment processes

**Example Invocation**:
```text
@devops Create a GitHub Actions workflow for automated NuGet publishing
on release tags. Include security scanning.
```

---

#### security

**File**: `src/claude/security.md`

**Role**: Vulnerability assessment and threat modeling

**Specialization**: OWASP Top 10, STRIDE analysis, secure coding, CWE detection

**Input**:
- Code to review
- Feature design
- Change scope

**Output**:
- Threat models in `.agents/security/TM-NNN-*.md`
- Security reports in `.agents/security/SR-NNN-*.md`
- Post-Implementation Verification (PIV) reports

**Delegates To**: None (returns to orchestrator)

**Called By**: orchestrator, architect, devops

**When to Use**:
- Touching auth/authorization code
- Handling user data
- Adding external APIs
- Reviewing security-sensitive changes

**Example Invocation**:
```text
@security Review the OAuth implementation for vulnerabilities.
Create a threat model and identify required controls.
```

---

### 2.3 Quality Agents

#### critic

**File**: `src/claude/critic.md`

**Role**: Validates plans before implementation begins

**Specialization**: Plan review, risk identification, scope validation

**Input**:
- Planning artifacts (PRDs, task breakdowns)
- Acceptance criteria
- Business objectives

**Output**:
- Critique report in `.agents/critique/`
- Approval/rejection with rationale
- Specific improvement recommendations

**Delegates To**: None (returns to orchestrator)

**Called By**: orchestrator, planner

**When to Use**:
- After planning artifacts created
- Before implementation begins
- Validating scope and completeness

**Example Invocation**:
```text
@critic Review the implementation plan at .agents/planning/PLAN-auth.md
Validate scope, risks, and alignment with requirements.
```

---

#### qa

**File**: `src/claude/qa.md`

**Role**: Verifies implementation works correctly for users

**Specialization**: Test strategy, coverage validation, user scenario testing

**Input**:
- Implementation to verify
- Acceptance criteria
- Test requirements

**Output**:
- Test strategies in `.agents/qa/NNN-*-test-strategy.md`
- Test reports in `.agents/qa/NNN-*-test-report.md`
- Coverage analysis

**Delegates To**: None (returns to orchestrator)

**Called By**: orchestrator, implementer

**When to Use**:
- Immediately after implementer changes
- Verifying acceptance criteria
- Assessing test coverage

**Example Invocation**:
```text
@qa Verify the UserAuthentication implementation.
Run tests, check coverage, and validate user scenarios.
```

---

#### independent-thinker

**File**: `src/claude/independent-thinker.md`

**Role**: Challenges assumptions with evidence-based analysis

**Specialization**: Contrarian analysis, assumption testing, alternative viewpoints

**Input**:
- Decision or assumption to challenge
- Existing analysis or proposal
- Claims to fact-check

**Output**:
- Evidence-based challenge or validation
- Alternative perspectives with tradeoffs
- Uncertainty declarations

**Delegates To**: None (returns to orchestrator)

**Called By**: orchestrator, high-level-advisor

**When to Use**:
- Validating important decisions
- Challenging group consensus
- Needing devil's advocate perspective

**Example Invocation**:
```text
@independent-thinker Challenge the assumption that microservices
are the right architecture for this project. What alternatives
should we consider?
```

---

### 2.4 Design Agents

#### architect

**File**: `src/claude/architect.md`

**Role**: Maintains architectural coherence and technical governance

**Specialization**: ADRs, design patterns, system boundaries, impact analysis

**Input**:
- Design questions or proposals
- Technical change requests
- Cross-cutting concerns

**Output**:
- ADRs in `.agents/architecture/ADR-NNN-*.md`
- Design guidance
- Impact analysis

**Delegates To**: None (returns to orchestrator)

**Called By**: orchestrator, planner, roadmap

**When to Use**:
- Introducing new dependencies
- Changing system boundaries
- Making cross-cutting technical decisions

**Example Invocation**:
```text
@architect Design the caching layer for user sessions.
Document the decision in an ADR with tradeoff analysis.
```

---

#### analyst

**File**: `src/claude/analyst.md`

**Role**: Research and investigation specialist

**Specialization**: Root cause analysis, API research, requirements gathering, feature request evaluation

**Input**:
- Problem to investigate
- Feature request to evaluate
- Research topic

**Output**:
- Analysis reports in `.agents/analysis/`
- Root cause findings
- Requirements documentation
- Feature evaluation with RICE scoring

**Delegates To**: None (returns to orchestrator)

**Called By**: orchestrator, planner

**When to Use**:
- Investigating bugs (unclear cause)
- Evaluating feature requests
- Pre-implementation research
- Understanding external APIs

**Example Invocation**:
```text
@analyst Investigate why API responses are slow for large datasets.
Identify the bottleneck and recommend solutions.
```

---

#### explainer

**File**: `src/claude/explainer.md`

**Role**: Creates PRDs and technical documentation

**Specialization**: Product requirements, feature specs, junior-developer-friendly docs

**Input**:
- Feature concept or request
- Clarifying answers from user

**Output**:
- PRDs in `.agents/planning/PRD-*.md`
- Explainer documents
- Technical specifications

**Delegates To**: None (returns to orchestrator)

**Called By**: orchestrator, roadmap

**When to Use**:
- Creating feature specifications
- Documenting requirements
- Explaining complex features

**Example Invocation**:
```text
@explainer Create a PRD for the user notification system.
Ask clarifying questions before writing.
```

---

### 2.5 Strategy Agents

#### high-level-advisor

**File**: `src/claude/high-level-advisor.md`

**Role**: Brutally honest strategic advisor

**Specialization**: Ruthless triage, decision-making, priority conflicts

**Input**:
- Strategic decision or conflict
- Multi-agent disagreements
- Priority disputes

**Output**:
- Clear verdicts (do X, not options)
- Priority stack (P0/P1/P2/KILL)
- Continue/Pivot/Cut recommendations

**Delegates To**: None (returns to orchestrator)

**Called By**: orchestrator, roadmap

**When to Use**:
- Strategic impasses
- Conflicting agent recommendations
- Hard prioritization decisions
- Decision paralysis

**Example Invocation**:
```text
@high-level-advisor We're stuck between rewriting the auth system
or patching it. Team is split. Give us a verdict.
```

---

#### roadmap

**File**: `src/claude/roadmap.md`

**Role**: Strategic product owner defining WHAT and WHY

**Specialization**: Epic definition, RICE/KANO prioritization, product vision

**Input**:
- Feature vision or idea
- Business context
- User needs

**Output**:
- Epic definitions in `.agents/roadmap/`
- Roadmap updates
- Priority recommendations

**Delegates To**: None (returns to orchestrator)

**Called By**: orchestrator, high-level-advisor

**When to Use**:
- Defining new features
- Prioritizing backlog
- Validating work alignment with strategy

**Example Invocation**:
```text
@roadmap Define an epic for multi-tenant support.
Prioritize it against existing roadmap items.
```

---

#### retrospective

**File**: `src/claude/retrospective.md`

**Role**: Extracts learnings from execution

**Specialization**: Five Whys, Fishbone analysis, skill extraction

**Input**:
- Task or session to analyze
- Execution artifacts
- Feedback

**Output**:
- Retrospective reports in `.agents/retrospective/`
- Skill recommendations (ADD/UPDATE/TAG/REMOVE)
- Process improvements

**Delegates To**: skillbook (via orchestrator)

**Called By**: orchestrator

**When to Use**:
- After task completion
- After failures
- Session end
- Milestone completion

**Example Invocation**:
```text
@retrospective Analyze the authentication implementation session.
Extract learnings and recommend skill updates.
```

---

### 2.6 Support Agents

#### memory

**File**: `src/claude/memory.md`

**Role**: Cross-session context management

**Specialization**: Knowledge retrieval, context persistence, skill citation

**Input**:
- Context retrieval query
- Milestone summary to store

**Output**:
- Retrieved context
- Storage confirmation
- Skill citations

**Delegates To**: None (returns to orchestrator)

**Called By**: orchestrator (typically at session start/end)

**When to Use**:
- Session start for context retrieval
- Milestone completion for persistence
- Complex memory operations

**Example Invocation**:
```text
@memory Retrieve context about the authentication feature
implementation from previous sessions.
```

---

#### skillbook

**File**: `src/claude/skillbook.md`

**Role**: Manages learned strategies and patterns

**Specialization**: Skill storage, deduplication, quality gates

**Input**:
- Reflection with pattern, evidence, recommendation
- Skill update requests

**Output**:
- Skill entity creation/update
- Deduplication results
- Quality validation

**Delegates To**: None (returns to orchestrator)

**Called By**: orchestrator (after retrospective)

**When to Use**:
- After retrospective analysis
- Persisting proven strategies
- Removing harmful patterns

**Example Invocation**:
```text
@skillbook Add skill from retrospective:
## Pattern: Use /m:1 flag for CI builds
## Evidence: Reduced file locking errors by 100%
## Recommendation: ADD
```

---

#### pr-comment-responder

**File**: `src/claude/pr-comment-responder.md`

**Role**: Handles PR review comments

**Specialization**: Comment triage, reviewer communication, bot handling

**Input**:
- PR number
- Review comments to address

**Output**:
- Comment map in `.agents/pr-comments/PR-[N]/`
- Task lists
- Reply drafts

**Delegates To**: orchestrator (for analysis and implementation)

**Called By**: User (via /pr-comment-responder command)

**When to Use**:
- Responding to GitHub PR review comments
- Managing bot reviewer feedback
- Coordinating comment resolution

**Example Invocation**:
```text
@pr-comment-responder Address all review comments on PR #47.
Triage by priority and implement fixes.
```

---

## 3. Workflow Patterns

### 3.1 Standard Development Flow

For typical feature implementation with quality gates.

```
User Request
     │
     ▼
┌─────────────┐
│ orchestrator│
└──────┬──────┘
       │
       ▼
┌─────────────┐    Impact     ┌──────────┐
│   planner   │───Analysis───▶│specialists│
└──────┬──────┘               └──────────┘
       │
       ▼
┌─────────────┐
│   critic    │──Rejected?──▶ Back to planner
└──────┬──────┘
       │ Approved
       ▼
┌─────────────┐
│ implementer │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│     qa      │──Failed?──▶ Back to implementer
└──────┬──────┘
       │ Passed
       ▼
    Complete
```

**Agents**: `orchestrator → planner → critic → implementer → qa`

**Use When**: New features, significant changes

---

### 3.2 Quick Fix Flow

For simple, well-defined fixes.

```
User Request
     │
     ▼
┌─────────────┐
│ implementer │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│     qa      │
└──────┬──────┘
       │
       ▼
    Complete
```

**Agents**: `implementer → qa`

**Use When**: Bug fixes with clear reproduction, single-file changes

---

### 3.3 Ideation Flow

For exploring new feature ideas.

```
Vibe Prompt
     │
     ▼
┌─────────────┐
│ orchestrator│
└──────┬──────┘
       │
       ▼
┌─────────────┐
│   analyst   │──Research
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  architect  │──Design
└──────┬──────┘
       │
       ▼
┌─────────────┐
│   planner   │──Plan
└──────┬──────┘
       │
       ▼
┌──────────────┐
│task-generator│──Tasks
└──────────────┘
```

**Agents**: `orchestrator → analyst → architect → planner → task-generator`

**Use When**: Exploring new features, understanding scope

---

### 3.4 Strategic Decision Flow

For high-stakes decisions requiring challenge.

```
Decision Request
       │
       ▼
┌───────────────────┐
│independent-thinker│──Challenge
└────────┬──────────┘
         │
         ▼
┌──────────────────┐
│high-level-advisor│──Verdict
└────────┬─────────┘
         │
         ▼
┌──────────────┐
│task-generator│──Actions
└──────────────┘
```

**Agents**: `independent-thinker → high-level-advisor → task-generator`

**Use When**: Architecture decisions, priority conflicts, strategic pivots

---

### 3.5 Impact Analysis Flow

For understanding change implications across domains.

```
Change Request
       │
       ▼
┌─────────────┐
│   planner   │
└──────┬──────┘
       │
       ├───────────────┬───────────────┬──────────────┐
       ▼               ▼               ▼              ▼
┌──────────┐    ┌──────────┐    ┌─────────┐    ┌────────┐
│ architect│    │    qa    │    │ devops  │    │security│
└────┬─────┘    └────┬─────┘    └────┬────┘    └────┬───┘
     │               │               │              │
     └───────────────┴───────────────┴──────────────┘
                            │
                            ▼
                    ┌─────────────┐
                    │ Aggregation │
                    └──────┬──────┘
                           │
                           ▼
                       Decision
```

**Agents**: `planner → [architect, qa, devops, security] → aggregation`

**Use When**: Major changes, cross-cutting concerns, risk assessment

---

### 3.6 Learning Extraction Flow

For capturing institutional knowledge.

```
Task Completion
       │
       ▼
┌───────────────┐
│ retrospective │──Analyze
└───────┬───────┘
        │
        ▼
┌───────────────┐
│   skillbook   │──Persist
└───────────────┘
```

**Agents**: `retrospective → skillbook`

**Use When**: After task completion, failures, session end

---

## 4. Routing Heuristics

### Request Pattern Matching

| Request Pattern | Primary Agent | Fallback | Notes |
|-----------------|---------------|----------|-------|
| "implement", "code", "fix", "add" | implementer | architect | Direct coding tasks |
| "test", "coverage", "qa", "verify" | qa | implementer | Quality verification |
| "design", "architecture", "ADR" | architect | planner | Design decisions |
| "investigate", "research", "why" | analyst | explainer | Root cause analysis |
| "review", "critique", "validate" | critic | independent-thinker | Plan validation |
| "deploy", "ci", "pipeline", "build" | devops | implementer | Infrastructure |
| "security", "vulnerability", "threat" | security | analyst | Security review |
| "document", "explain", "PRD" | explainer | analyst | Documentation |
| "plan", "break down", "milestone" | planner | task-generator | Work decomposition |
| "task", "atomic", "estimate" | task-generator | planner | Task generation |
| "prioritize", "roadmap", "epic" | roadmap | high-level-advisor | Product strategy |
| "decide", "verdict", "stuck" | high-level-advisor | independent-thinker | Strategic decisions |
| "learn", "retro", "what went wrong" | retrospective | analyst | Learning extraction |
| "PR comment", "review feedback" | pr-comment-responder | orchestrator | PR management |

### Agent Selection Matrix

| Task Type | Primary | Secondary | Validator |
|-----------|---------|-----------|-----------|
| New feature | architect | planner | critic |
| Bug fix | analyst | implementer | qa |
| Refactor | architect | implementer | critic |
| Documentation | explainer | analyst | - |
| Security review | security | analyst | critic |
| Performance | analyst | implementer | qa |
| CI/CD change | devops | implementer | security |

---

## 5. Memory and Handoff System

### 5.1 Session Handoff

#### HANDOFF.md Structure

At session end, create a handoff document:

```markdown
# Session Handoff

**Date**: YYYY-MM-DD
**Session ID**: [unique identifier]

## Work Completed
- [Task 1]: [Status]
- [Task 2]: [Status]

## Context for Next Session
- [Important context 1]
- [Important context 2]

## Pending Items
- [ ] [Incomplete task]

## Decisions Made
- [Decision 1]: [Rationale]

## Files Modified
- [path/to/file]: [Change type]
```

#### Session Log Location

`.agents/sessions/YYYY-MM-DD-[scope].md`

### 5.2 Memory Protocol

All agents access memory via cloudmcp-manager tools:

```python
# Search for context (before work)
mcp__cloudmcp-manager__memory-search_nodes
Query: "[topic] [keywords]"

# Store learnings (after work)
mcp__cloudmcp-manager__memory-add_observations
{
  "observations": [{
    "entityName": "[Entity-Name]",
    "contents": ["[Observation with source]"]
  }]
}

# Create new entities
mcp__cloudmcp-manager__memory-create_entities
{
  "entities": [{
    "name": "[Entity-Name]",
    "entityType": "[Type]",
    "observations": ["[Initial observations]"]
  }]
}
```

### 5.3 Skill Persistence

Skills extracted from retrospectives are stored with:

| Field | Description |
|-------|-------------|
| Statement | Atomic strategy (max 15 words) |
| Context | When to apply |
| Evidence | Specific execution reference |
| Atomicity | Quality score (70%+ required) |
| Tag | helpful / harmful / neutral |

### 5.4 Artifact Locations

| Directory | Purpose | Agent |
|-----------|---------|-------|
| `.agents/analysis/` | Research findings | analyst |
| `.agents/architecture/` | ADRs, design decisions | architect |
| `.agents/planning/` | PRDs, plans, tasks | planner, explainer |
| `.agents/critique/` | Plan reviews | critic |
| `.agents/qa/` | Test strategies, reports | qa |
| `.agents/retrospective/` | Learning extractions | retrospective |
| `.agents/roadmap/` | Epic definitions | roadmap |
| `.agents/devops/` | Pipeline configs | devops |
| `.agents/security/` | Threat models | security |
| `.agents/sessions/` | Session context | memory |
| `.agents/skills/` | Skill files | skillbook |

---

## 6. Parallel Execution

### 6.1 Sectioning Pattern

When subtasks are independent, document parallel execution:

```markdown
## Parallel Analysis

### Section A: Architecture Impact
Agent: architect
Status: In Progress

### Section B: Security Impact
Agent: security
Status: In Progress

### Section C: QA Impact
Agent: qa
Status: In Progress
```

### 6.2 Voting Pattern

For critical decisions, use redundant execution:

```markdown
## Voting Session

### Vote 1: independent-thinker
Recommendation: [A]
Confidence: [%]

### Vote 2: architect
Recommendation: [A]
Confidence: [%]

### Vote 3: analyst
Recommendation: [B]
Confidence: [%]

### Result
Majority: [A] (2/3)
```

### 6.3 Aggregation Strategies

| Strategy | Use When | Process |
|----------|----------|---------|
| **merge** | Non-conflicting outputs | Combine all results |
| **vote** | Conflicting recommendations | Select majority |
| **escalate** | Critical conflicts | Route to high-level-advisor |

---

## 7. Steering System

### 7.1 Steering File Locations

Location: `.agents/steering/`

| File | Glob Pattern | Purpose |
|------|--------------|---------|
| `csharp-patterns.md` | `**/*.cs` | C# coding standards |
| `agent-prompts.md` | `src/claude/**/*.md` | Agent prompt patterns |
| `testing-approach.md` | `**/*.test.*` | Testing conventions |
| `security-practices.md` | `**/Auth/**` | Security requirements |

### 7.2 Injection Protocol

Orchestrator determines applicable steering:

1. Analyze task scope (files affected)
2. Match against steering glob patterns
3. Inject relevant steering into agent context
4. Respect token budget (prioritize most specific)

---

## 8. Quality Gates

### 8.1 Critic Validation

Critic MUST review before implementation when:

- New architectural patterns introduced
- More than 5 files affected
- Security-sensitive changes
- Breaking changes to APIs

**Checklist**:
- [ ] Scope matches requirements
- [ ] Dependencies identified
- [ ] Risks documented
- [ ] Acceptance criteria testable
- [ ] Estimates reasonable

**Outcomes**: APPROVED / REJECTED / NEEDS WORK

### 8.2 QA Verification

QA validates after ALL implementer work:

| Check | Threshold |
|-------|-----------|
| New code coverage | ≥80% |
| All tests passing | 100% |
| User scenarios verified | All |
| No regressions | Confirmed |

### 8.3 Traceability Validation

Before completion:

- [ ] All tasks reference source requirements
- [ ] Implementation matches plan
- [ ] Tests cover acceptance criteria
- [ ] Documentation updated

---

## 9. Conflict Resolution

### 9.1 Agent Disagreement

When agents produce conflicting recommendations:

1. **Document Conflict**: Record both positions with evidence
2. **Escalate**: Route to high-level-advisor
3. **Verdict**: Advisor provides clear decision
4. **Document Rationale**: Record why decision was made

### 9.2 Scope Creep

Orchestrator enforces boundaries:

1. Compare current work against original scope
2. Flag additions not in requirements
3. Either: reject, or route to planner for scope update
4. Document decision

### 9.3 Blocked Tasks

When work cannot proceed:

```markdown
## Blocker Report

**Task**: [TASK-NNN]
**Blocker**: [Description]
**Type**: External / Technical / Missing Info

**Alternatives Attempted**:
1. [Alternative 1]: [Result]
2. [Alternative 2]: [Result]

**Recommendation**:
- [ ] Wait for [dependency]
- [ ] Pivot to [alternative task]
- [ ] Escalate to [agent/user]
```

---

## 10. Quick Reference Tables

### Workflow Selection

| Scenario | Workflow | Key Agents |
|----------|----------|------------|
| New feature from scratch | Ideation + Standard | architect, planner, implementer |
| Implement defined task | Quick Fix | implementer, qa |
| Investigate issue | Analysis | analyst, architect |
| Quality improvement | Standard | critic, qa |
| Strategic decision | Strategic | independent-thinker, high-level-advisor |
| Security review | Specialized | security, architect |
| Documentation | Specialized | explainer, analyst |
| PR comment response | PR Flow | pr-comment-responder, orchestrator |

### Agent Model Assignment

| Agent | Model | Rationale |
|-------|-------|-----------|
| orchestrator | sonnet | Fast routing decisions |
| implementer | sonnet | Balanced code generation |
| analyst | sonnet | Research efficiency |
| architect | sonnet | Design analysis |
| planner | sonnet | Planning speed |
| critic | sonnet | Review efficiency |
| qa | sonnet | Test validation |
| explainer | sonnet | Documentation |
| task-generator | sonnet | Task decomposition |
| high-level-advisor | opus | Strategic depth |
| independent-thinker | opus | Deep analysis |
| memory | sonnet | Simple operations |
| retrospective | sonnet | Learning extraction |
| skillbook | sonnet | Skill management |
| devops | sonnet | Infrastructure |
| roadmap | opus | Strategic vision |
| security | opus | Thorough review |
| pr-comment-responder | sonnet | Comment handling |

---

## 11. Extension Points

### 11.1 Adding New Agents

1. **Create Agent Prompt**: `src/claude/[agent-name].md`

```markdown
---
name: [agent-name]
description: [One-line description]
model: [sonnet/opus/haiku]
argument-hint: [Usage hint for users]
---
# [Agent Name] Agent

## Core Identity
[Role description]

## Claude Code Tools
[Available tools]

## Core Mission
[Primary purpose]

## Key Responsibilities
[Numbered list]

## Memory Protocol
[How to use cloudmcp-manager]

## Output Location
[Where artifacts are saved]

## Handoff Protocol
[How to return results]

## Execution Mindset
[Guiding principles]
```

2. **Register in AGENT-SYSTEM.md**: Add to Agent Catalog

3. **Update Routing**: Add patterns to routing heuristics

4. **Create Output Directory**: `mkdir .agents/[agent-name]/`

### 11.2 Adding Steering Files

1. **Create Steering File**: `.agents/steering/[domain].md`

```markdown
# [Domain] Steering

## Scope
Glob pattern: `[pattern]`

## Guidelines
[Domain-specific guidance]

## Anti-Patterns
[What to avoid]

## Examples
[Good and bad examples]
```

2. **Register Pattern**: Add to Steering File Locations table

### 11.3 Adding Workflows

1. **Document Workflow**:

```markdown
### [Workflow Name] Flow

**Purpose**: [What this workflow accomplishes]

**Agents**: `agent1 → agent2 → agent3`

**Use When**: [Trigger conditions]

**Diagram**:
[ASCII or Mermaid diagram]
```

2. **Update Workflow Selection Table**

3. **Add Routing Rules**: Update orchestrator patterns if needed

---

## 12. Appendix

### A. Entity Naming Conventions

| Type | Pattern | Example |
|------|---------|---------|
| Feature | `Feature-[Name]` | `Feature-Authentication` |
| Module | `Module-[Name]` | `Module-Identity` |
| Decision | `ADR-[Number]` | `ADR-001` |
| Pattern | `Pattern-[Name]` | `Pattern-StrategyTax` |
| Problem | `Problem-[Name]` | `Problem-CachingRace` |
| Solution | `Solution-[Name]` | `Solution-LockingCache` |
| Skill | `Skill-[Category]-[Number]` | `Skill-Build-001` |
| Epic | `EPIC-[Number]-[name]` | `EPIC-001-authentication` |

### B. Relation Types

| Relation | Meaning |
|----------|---------|
| `implemented_in` | Feature in module |
| `depends_on` | Entity requires another |
| `replaces` | New replaces old |
| `supersedes` | Newer version |
| `related_to` | General association |
| `blocked_by` | Progress blocked |
| `solved_by` | Problem has solution |
| `derived_from` | Skill from learning |

### C. Skill Categories

| Category | Description |
|----------|-------------|
| Build | Compilation patterns |
| Test | Testing strategies |
| Debug | Debugging techniques |
| Design | Architecture patterns |
| Perf | Performance optimization |
| Process | Workflow improvements |
| Tool | Tool-specific knowledge |

### D. Priority Definitions

| Priority | Meaning | Action |
|----------|---------|--------|
| P0 | Critical | Do today |
| P1 | Important | Do this week |
| P2 | Nice to have | Do eventually |
| KILL | Waste | Stop doing |

---

*Last updated: 2025-12-17 | Version 2.0*
