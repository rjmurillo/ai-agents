# Agent Catalog

This document describes all 21 specialized agents in the AI Agents system. Each agent has a defined role, specific outputs, and recommended use cases.

## Agent Overview

| Agent | Category | Platform availability |
|-------|----------|----------------------|
| [orchestrator](#orchestrator) | Coordination | Claude, Copilot CLI, VS Code |
| [analyst](#analyst) | Planning | Claude, Copilot CLI, VS Code |
| [architect](#architect) | Planning | Claude, Copilot CLI, VS Code |
| [milestone-planner](#milestone-planner) | Planning | Claude, Copilot CLI, VS Code |
| [implementer](#implementer) | Implementation | Claude, Copilot CLI, VS Code |
| [critic](#critic) | Quality | Claude, Copilot CLI, VS Code |
| [qa](#qa) | Quality | Claude, Copilot CLI, VS Code |
| [security](#security) | Quality | Claude, Copilot CLI, VS Code |
| [devops](#devops) | Operations | Claude, Copilot CLI, VS Code |
| [roadmap](#roadmap) | Strategy | Claude, Copilot CLI, VS Code |
| [high-level-advisor](#high-level-advisor) | Strategy | Claude, Copilot CLI, VS Code |
| [independent-thinker](#independent-thinker) | Strategy | Claude, Copilot CLI, VS Code |
| [explainer](#explainer) | Documentation | Claude, Copilot CLI, VS Code |
| [spec-generator](#spec-generator) | Documentation | Claude only |
| [task-decomposer](#task-decomposer) | Planning | Claude, Copilot CLI, VS Code |
| [backlog-generator](#backlog-generator) | Planning | Claude, Copilot CLI, VS Code |
| [debug](#debug) | Implementation | Claude, Copilot CLI, VS Code |
| [janitor](#janitor) | Implementation | Claude, Copilot CLI, VS Code |
| [memory](#memory) | Knowledge | Claude, Copilot CLI, VS Code |
| [retrospective](#retrospective) | Knowledge | Claude, Copilot CLI, VS Code |
| [skillbook](#skillbook) | Knowledge | Claude, Copilot CLI, VS Code |
| [pr-comment-responder](#pr-comment-responder) | Collaboration | Claude, Copilot CLI, VS Code |

## Coordination

### orchestrator

Enterprise task orchestrator who autonomously coordinates specialized agents end-to-end. Routes work, manages handoffs, and synthesizes results. Classifies complexity, triages delegation, and sequences workflows.

**Use when:** You have a multi-step task requiring coordination, integration, or complete end-to-end resolution.

**Output:** Delegated results from specialists, synthesized into a cohesive response.

**Example:**

```text
orchestrator: build the webhook retry system. Start with analyst to verify requirements,
then milestone-planner for work packages, critic to stress-test, implementer to code,
qa to verify, and security to scan. Open a PR when all checks pass.
```

## Planning

### analyst

Research and investigation specialist. Digs deep into root causes, surfaces unknowns, and gathers evidence before implementation. Methodical about documenting findings, evaluating feasibility, and identifying dependencies and risks.

**Use when:** You need clarity on patterns, impact assessment, requirements discovery, or hypothesis validation.

**Output:** Quantitative findings with evidence, feasibility assessments, dependency maps.

**Example:**

```text
analyst: the /api/users endpoint returns 500 when the email contains a plus sign.
Trace the request through the handler, identify the root cause, and propose a fix.
```

### architect

Technical authority on system design. Guards architectural coherence, enforces patterns, and maintains boundaries. Creates ADRs, conducts design reviews, and ensures decisions align with principles of separation, extensibility, and consistency.

**Use when:** You need governance, trade-off analysis, or blueprints that protect long-term system health.

**Output:** Rated assessments (Strong/Adequate/Needs-Work), ADRs, design blueprints.

**Example:**

```text
architect: review the proposed microservice split for the auth module.
Evaluate coupling, data ownership, and API surface area.
```

### milestone-planner

High-rigor planning assistant. Translates roadmap epics into implementation-ready work packages with clear milestones, dependencies, and acceptance criteria. Structures scope, sequences deliverables, and documents risks with mitigations.

**Use when:** You need structured breakdown, impact analysis, or verification approaches.

**Output:** Implementation plans with acceptance criteria, dependency graphs, risk matrices.

**Example:**

```text
milestone-planner: break down "add webhook retry with exponential backoff" into milestones.
Include acceptance criteria, estimated complexity, dependencies, and implementation order.
```

### task-decomposer

Task decomposition specialist. Breaks PRDs and epics into atomic, estimable work items with clear acceptance criteria and done definitions. Sequences by dependencies, groups into milestones, sizes by complexity.

**Use when:** Tasks need to be discrete enough that someone can pick them up and know exactly what to do.

**Output:** Sized work items with acceptance criteria and done definitions.

### backlog-generator

Autonomous backlog generator. Analyzes project state (open issues, PRs, code health) when agent slots are idle and creates 3-5 sized, actionable tasks. Unlike task-decomposer (which decomposes existing PRDs), backlog-generator proactively identifies what needs doing next.

**Use when:** You need to discover what work should happen next based on current project state.

**Output:** 3-5 sized, actionable tasks with context from project analysis.

## Implementation

### implementer

Execution-focused engineering expert. Implements approved plans with production-quality code. Enforces testability, encapsulation, and intentional coupling. Uses Commonality/Variability Analysis (CVA) for design. Writes tests alongside code, commits atomically with conventional messages.

**Use when:** You need to ship code.

**Output:** Production code, tests, atomic commits with conventional messages.

**Example:**

```text
implementer: implement the webhook retry handler per the approved design in ADR-045.
Write tests first, then implementation. Commit atomically.
```

### debug

Systematic debugger. Follows structured phases: assessment, investigation, resolution, and quality assurance. Performs root cause analysis rather than symptom treatment.

**Use when:** You need to find and fix a bug through systematic investigation.

**Output:** Diagnostic findings with resolution steps, root cause identification.

**Example:**

```text
debug: the payment webhook handler drops events when Redis is unavailable.
Find the root cause and propose a fix.
```

### janitor

Code and documentation cleanup specialist. Performs janitorial tasks including cleanup, simplification, and tech debt remediation.

**Use when:** You need to clean up code, reduce complexity, or address tech debt.

**Output:** Refactoring suggestions, cleanup changes.

## Quality

### critic

Constructive reviewer. Stress-tests plans before implementation. Validates completeness, identifies gaps, catches ambiguity. Challenges assumptions, checks alignment, and blocks approval when risks are not mitigated.

**Use when:** You need a clear verdict on whether a plan is ready or needs revision.

**Output:** Verdict: APPROVE, APPROVE WITH CONDITIONS, or REJECT with specific findings.

**Example:**

```text
critic: review the authentication design in docs/auth-design.md for coupling,
error handling gaps, and test coverage. Deliver an APPROVE or REJECT verdict.
```

### qa

Quality assurance specialist. Verifies implementations work correctly for real users, not just passing tests. Designs test strategies, validates coverage against acceptance criteria, and reports results with evidence.

**Use when:** You need confidence through verification, regression testing, edge-case coverage, or user-scenario validation.

**Output:** Test reports, coverage analysis, pass/fail results with evidence.

**Example:**

```text
qa: write pytest tests for scripts/validate_session_json.py.
Cover happy path, malformed input, missing required fields, and boundary conditions.
Target 95% line coverage.
```

### security

Security specialist with defense-first mindset. Fluent in threat modeling, vulnerability assessment, and OWASP Top 10. Scans for CWE patterns, detects secrets, audits dependencies, and maps attack surfaces.

**Use when:** You need hardening, penetration analysis, compliance review, or mitigation recommendations before shipping.

**Output:** Threat matrices with CWE/CVSS ratings, vulnerability reports, remediation steps.

**Example:**

```text
security: scan src/api/ for OWASP Top 10 vulnerabilities. Focus on injection,
broken auth, and data exposure. Output a threat matrix with CWE identifiers.
```

## Strategy

### roadmap

Strategic product owner. Defines what to build and why with outcome-focused vision. Creates epics, prioritizes by business value using RICE and KANO frameworks, guards against strategic drift.

**Use when:** You need direction, outcomes over outputs, sequencing by dependencies, or user-value validation.

**Output:** Priority stacks, cost-benefit analysis, epic definitions.

### high-level-advisor

Brutally honest strategic advisor. Cuts through comfort and delivers unfiltered truth. Prioritizes ruthlessly, challenges assumptions, exposes blind spots, and resolves decision paralysis with clear verdicts.

**Use when:** You need P0 priorities, not options. Clarity and action, not validation.

**Output:** Verdict: GO, CONDITIONAL GO, or NO-GO with conditions.

### independent-thinker

Contrarian analyst. Challenges assumptions with evidence, presents alternative viewpoints, and declares uncertainty rather than guessing. Intellectually rigorous, respectfully skeptical, cites sources.

**Use when:** You need opposing critique, trade-off analysis, or verification rather than validation. Use as devil's advocate.

**Output:** Counter-arguments with alternatives and evidence.

## Documentation

### explainer

Documentation specialist. Writes PRDs, explainers, and technical specifications that junior developers understand without questions. Uses explicit language, INVEST criteria for user stories, and unambiguous acceptance criteria.

**Use when:** You need clarity, accessible documentation, templates, or requirements that define scope and boundaries.

**Output:** Specs, user guides, PRDs with clear acceptance criteria.

### spec-generator

Requirement specifications specialist. Transforms feature descriptions into structured 3-tier specifications using EARS requirements format. Guides users through clarifying questions, then produces requirements.md, design.md, and tasks.md with full traceability.

**Use when:** A feature idea needs to become an implementable specification.

**Output:** requirements.md, design.md, and tasks.md with EARS-format requirements.

> **Note:** Available in Claude Code only.

## Operations

### devops

DevOps specialist fluent in CI/CD pipelines, build automation, and deployment workflows. Thinks in reliability, security, and developer experience. Designs GitHub Actions, configures build systems, and manages secrets.

**Use when:** You need pipeline configuration, infrastructure automation, or anything involving environments, artifacts, caching, or runners.

**Output:** Infrastructure configs, pipeline definitions, maintenance estimates.

## Knowledge

### memory

Memory management specialist. Ensures cross-session continuity by retrieving relevant context before reasoning and storing progress at milestones. Maintains institutional knowledge, tracks entity relations, and keeps observations fresh with source attribution.

**Use when:** You need context retrieval, knowledge persistence, or understanding why past decisions were made.

**Output:** Retrieved knowledge, stored observations with citations.

### retrospective

Reflective analyst. Extracts learnings through structured retrospective frameworks. Diagnoses agent performance, identifies error patterns, and documents success strategies. Uses Five Whys, timeline analysis, and learning matrices.

**Use when:** You need root-cause analysis, atomicity scoring, or to transform experience into institutional knowledge.

**Output:** Actionable insights, skill updates, learning extractions.

### skillbook

Skill manager. Transforms reflections into high-quality atomic skillbook updates. Guards strategy quality, prevents duplicates, and maintains learned patterns. Scores atomicity, runs deduplication checks, and rejects vague learnings.

**Use when:** You need skill persistence, validation, or keeping institutional knowledge clean and actionable.

**Output:** Atomic strategy updates, deduplication reports.

## Collaboration

### pr-comment-responder

PR review coordinator. Gathers comment context, acknowledges every piece of feedback, and ensures all reviewer comments are addressed systematically. Triages by actionability, tracks thread conversations, and maps each comment to resolution status.

**Use when:** You are handling PR feedback, review threads, or bot comments.

**Output:** Triaged responses, resolution tracking, comment status mapping.

## Workflow Patterns

Agents work together through common patterns. The orchestrator manages these automatically, but you can also compose them manually.

| Workflow | Agent sequence |
|----------|----------------|
| Feature (standard) | orchestrator > analyst > architect > milestone-planner > critic > implementer > qa |
| Quick fix | implementer > qa |
| Strategic decision | independent-thinker > high-level-advisor > task-decomposer |
| Ideation pipeline | analyst > high-level-advisor > independent-thinker > critic > roadmap > explainer > task-decomposer |
