# Ideation Workflow

## Overview

The Ideation Workflow transforms vague feature ideas into actionable implementation plans. It handles the full lifecycle from "shower thought" to approved work breakdown structure.

## When to Use

The orchestrator triggers this workflow when it detects:

- **Package/library URLs**: NuGet, npm, PyPI links
- **Vague scope language**: "we need to add", "we should consider", "what if we"
- **Incomplete GitHub issues**: Issues lacking clear specifications
- **Exploratory requests**: "would it make sense to", "I was thinking about"
- **Early-stage ideas**: Features described without acceptance criteria

### Example Triggers

```text
"We need to integrate https://www.nuget.org/packages/DotNet.ReproducibleBuilds/"

"What if we added support for OpenTelemetry?"

"I was thinking about improving our logging infrastructure"

GitHub Issue #42: "Add caching" (no further details)
```

## Workflow Phases

```text
[Vague Idea]
     │
     ▼
┌─────────────────────────────────────────┐
│  PHASE 1: Research & Discovery          │
│  Agent: analyst                         │
│  Output: Research findings              │
│  Location: .agents/analysis/            │
└─────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────┐
│  PHASE 2: Validation & Consensus        │
│  Agents: high-level-advisor →           │
│          independent-thinker →          │
│          critic → roadmap               │
│  Output: Proceed / Defer / Reject       │
│  Location: .agents/analysis/            │
└─────────────────────────────────────────┘
     │
     ▼ (if Proceed)
┌─────────────────────────────────────────┐
│  PHASE 3: Epic & PRD Creation           │
│  Agents: roadmap → explainer →          │
│          task-generator                 │
│  Output: Epic, PRD, Work Breakdown      │
│  Location: .agents/roadmap/             │
│            .agents/planning/            │
└─────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────┐
│  PHASE 4: Implementation Plan Review    │
│  Agents: architect, devops,             │
│          security, qa (parallel)        │
│  Output: Approved implementation plan   │
│  Location: .agents/planning/            │
└─────────────────────────────────────────┘
     │
     ▼
[Ready for Implementation]
```

## Phase Details

### Phase 1: Research & Discovery

**Primary Agent**: analyst

**Purpose**: Gather evidence to inform the validation decision.

**Research Areas**:

| Area | Questions to Answer |
|------|---------------------|
| Package Overview | What does it do? What problem does it solve? |
| Community Signal | Is it actively maintained? How popular? |
| Technical Fit | Does it work with our stack? Any conflicts? |
| Integration Complexity | How much work to integrate? |
| Alternatives | What else could solve this problem? |
| Risks | Security, licensing, maintenance concerns? |

**Tools Used**:

- Microsoft Docs Search - Official Microsoft documentation
- Context7 - Library documentation
- DeepWiki - Repository documentation
- Perplexity - Deep research and web search
- WebSearch/WebFetch - General web research
- GitHub CLI - Issue and PR research

**Output**: `.agents/analysis/ideation-[topic].md`

**Success Criteria**: Research document with clear recommendation (Proceed/Defer/Reject) and supporting evidence.

### Phase 2: Validation & Consensus

**Agents** (sequential):

| Agent | Role | Key Question |
|-------|------|--------------|
| high-level-advisor | Strategic fit | Does this align with where we're going? |
| independent-thinker | Challenge assumptions | What are we missing? What could go wrong? |
| critic | Validate research | Is the analysis complete and accurate? |
| roadmap | Priority decision | Where does this fit in our roadmap? |

**Decision Options**:

| Decision | Meaning | Next Step |
|----------|---------|-----------|
| **Proceed** | Good idea, worth pursuing | Move to Phase 3 |
| **Defer** | Good idea, but not now | Pause workflow, create backlog entry at `.agents/roadmap/backlog.md` with conditions and resume trigger |
| **Reject** | Not aligned with goals | Report rejection to user, persist rationale in validation doc |

**Output**: `.agents/analysis/ideation-[topic]-validation.md`

**Success Criteria**: Unanimous or majority consensus with documented rationale.

### Phase 3: Epic & PRD Creation

**Agents** (sequential):

| Agent | Output | Location |
|-------|--------|----------|
| roadmap | Epic with vision and outcomes | `.agents/roadmap/epic-[topic].md` |
| explainer | Full PRD with specifications | `.agents/planning/prd-[topic].md` |
| task-generator | Work breakdown structure | `.agents/planning/tasks-[topic].md` |

**Epic Contents**:

- Vision statement
- Measurable outcomes (not outputs)
- Success metrics
- Scope boundaries (in/out)
- Dependencies

**PRD Contents**:

- User stories
- Acceptance criteria
- Technical requirements
- Non-functional requirements
- Edge cases

**WBS Contents**:

- Atomic tasks sized for individual agents
- Task dependencies
- Priority ordering
- Effort estimates

**Success Criteria**: Complete documentation chain from Epic to actionable tasks.

### Phase 4: Implementation Plan Review

**Agents** (can run in parallel):

| Agent | Review Focus |
|-------|--------------|
| architect | Design patterns, architectural fit, technical debt |
| devops | CI/CD impact, infrastructure needs, deployment |
| security | Threat assessment, secure coding, compliance |
| qa | Test strategy, coverage requirements, quality gates |

**Review Questions**:

- **Architect**: Does this fit our architecture? Any patterns to follow/avoid?
- **DevOps**: What CI/CD changes needed? Any infrastructure requirements?
- **Security**: Any security implications? What mitigations needed?
- **QA**: How do we test this? What coverage is required?

**Output**: `.agents/planning/implementation-plan-[topic].md`

**Success Criteria**: All agents approve (or concerns addressed) before implementation begins.

## Agent Sequence

Full sequence for reference:

```text
analyst -> high-level-advisor -> independent-thinker -> critic ->
roadmap -> explainer -> task-generator -> architect -> devops -> security -> qa
```

Note: In Phase 4, architect/devops/security/qa can run in parallel for efficiency.

## Artifacts Summary

| Phase | Artifact | Location |
|-------|----------|----------|
| 1 | Research findings | `.agents/analysis/ideation-[topic].md` |
| 2 | Validation decision | `.agents/analysis/ideation-[topic]-validation.md` |
| 3 | Epic | `.agents/roadmap/epic-[topic].md` |
| 3 | PRD | `.agents/planning/prd-[topic].md` |
| 3 | Tasks (WBS) | `.agents/planning/tasks-[topic].md` |
| 4 | Implementation plan | `.agents/planning/implementation-plan-[topic].md` |

## Exit Points

The workflow can exit early at several points:

| Exit Point | Condition | Action |
|------------|-----------|--------|
| Phase 1 | Analyst recommends Reject | Document, notify user, close |
| Phase 2 | Consensus is Reject | Document reasoning, close |
| Phase 2 | Consensus is Defer | Add to backlog with conditions |
| Phase 4 | Security finds critical issue | Block until resolved |

## Example: DotNet.ReproducibleBuilds

**Trigger**: "We need to integrate <https://www.nuget.org/packages/DotNet.ReproducibleBuilds/>"

**Phase 1 (analyst)**:

- Researches package on NuGet
- Checks GitHub repo, maintenance status
- Evaluates .NET version compatibility
- Identifies integration approach
- Recommends: Proceed (active package, simple integration, clear benefit)

**Phase 2 (validation)**:

- high-level-advisor: Aligned with build reliability goals
- independent-thinker: Flags potential CI time impact
- critic: Research is complete
- roadmap: Priority P2, next wave

**Phase 3 (planning)**:

- Epic: "Reproducible Builds for Supply Chain Security"
- PRD: Detailed requirements for integration
- Tasks: 5 atomic tasks for implementer

**Phase 4 (review)**:

- architect: Approved, fits existing build patterns
- devops: Approved, minor pipeline updates needed
- security: Approved, improves supply chain security
- qa: Approved, verification strategy defined

**Result**: Ready for implementation with full documentation.

## Related Documents

- [Task Classification Guide](./task-classification-guide.md)
- [Orchestrator Agent](../src/claude/orchestrator.md)
- [Analyst Agent](../src/claude/analyst.md)

---

*Document Version: 1.0*
*Created: 2025-12-14*
