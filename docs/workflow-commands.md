# Lifecycle Commands Reference

Slash commands for structured development phases. Each command invokes specialized agents and quality gates.

## Overview

The lifecycle command system provides six slash commands that guide development from requirements through shipping.

```text
/spec → /plan → /build → /test → /review → /ship
```

Each command chains to the next. Output from one phase feeds into the next automatically.

## Getting Started

### Standard Feature Workflow

```bash
/spec Add OAuth2 login flow with JWT tokens
/plan
/build
/test
/review
/ship
```

### Quick Fix Workflow

```bash
/build Fix null reference in UserService.GetById
/test
/ship
```

### Research-First Workflow

```bash
/spec Should we migrate from REST to gRPC for internal services?
/plan
```

## Command Reference

### /spec -- Define What to Build

Transforms a problem statement into testable requirements with acceptance criteria.

```bash
/spec <problem-statement-or-issue-number>
```

**What it does:**

1. Clarifies the problem (what, who, why, constraints)
2. Searches the codebase for existing solutions
3. Runs Commonality/Variability Analysis (CVA) to identify shared behavior and variation points
4. Writes requirements as testable acceptance criteria
5. Invokes analyst, decision-critic, and critic agents to find gaps and challenge assumptions

**Output:** Structured requirements with problem statement, acceptance criteria, out-of-scope exclusions, open questions, and CVA summary.

**When to use:** Starting a new feature or investigating whether something is worth building.

---

### /plan -- Plan How to Build It

Decomposes specs into milestones with dependencies and risk mitigations.

```bash
/plan <spec-output-or-issue-number>
```

**What it does:**

1. Reads the spec or issue
2. Maps sub-problems to existing code
3. Invokes milestone-planner to break work into independently shippable milestones
4. Invokes task-decomposer to create atomic tasks with done definitions (sized S/M/L)
5. Persists the plan as a versioned artifact via execution-plans skill
6. Runs analyst pre-mortem and critic validation

**Output:** Milestones with exit criteria, tasks per milestone, dependency graph, risk register, and deferred items.

**When to use:** After `/spec`, or when you have a clear problem and need an execution plan.

---

### /build -- Build Incrementally

Implements changes in thin vertical slices with TDD and atomic commits.

```bash
/build <plan-step-or-task-description>
```

**What it does:**

1. Reads the task and existing code patterns
2. Invokes the implementer agent as a senior engineer
3. For each slice: write failing test, write minimum code to pass, refactor toward quality
4. Commits atomically with conventional messages
5. Runs code-qualities-assessment to score the result

**Guardrails:** Atomic commits, no code without understanding existing patterns, favor delegation over inheritance, three similar lines beat a premature abstraction.

**When to use:** After `/plan`, or for direct implementation of a well-understood task.

---

### /test -- Prove It Works

Multi-dimensional quality validation across 6 gates: functional, non-functional, security, DevOps, DX, and observability.

```bash
/test <component-or-failure-description>
```

**What it does:**

1. Classifies the PR type (CODE, WORKFLOW, CONFIG, DOCS, MIXED)
2. Runs only the applicable gates based on PR type
3. Each gate dispatches a specialized agent (qa, analyst, security, devops, critic, architect)
4. Produces per-gate verdicts: PASS, WARN, or CRITICAL_FAIL

**Gates:**

| Gate | Agent | Focus |
|------|-------|-------|
| Functional | qa | Unit, integration, acceptance, edge cases, error paths |
| Non-Functional | analyst | Performance, scalability, reliability, complexity |
| Security | security | OWASP Top 10, CWE references, secrets, dependencies |
| DevOps | devops | Pipeline safety, Actions security, build reproducibility |
| DX | critic | API ergonomics, documentation, debuggability, onboarding |
| Observability | architect | Logging, metrics, alerting, tracing, health checks |

**Output:** Per-gate verdict table with findings, evidence, and overall PASS/WARN/CRITICAL_FAIL.

**When to use:** After `/build`, or to validate any branch before shipping.

---

### /review -- Review Before Merge

Five-axis code review across architecture, security, quality, tests, and standards.

```bash
/review <branch-or-pr-number>
```

**What it does:**

1. Reads the diff against the base branch
2. Runs five review axes sequentially, each dispatching a specialized agent or skill
3. Categorizes findings as Critical, Important, or Suggestion

**Axes:**

| Axis | Agent/Skill | Focus |
|------|-------------|-------|
| Architecture | architect | Patterns, boundaries, ADR conformance, coupling |
| Security | security + security-scan | CWE references, OWASP, least privilege |
| Quality | code-qualities-assessment | Cohesion, coupling, encapsulation, testability, DRY |
| Tests | qa | Coverage for every new code path, failure paths |
| Standards | golden-principles + taste-lints | Naming, style, consistency |

**Output:** Per-finding format with location (file:line), severity, and fix recommendation.

**When to use:** After `/test`, before shipping. Also useful for reviewing any diff or PR.

---

### /ship -- Ship It

Pre-flight validation, CI check, and PR creation.

```bash
/ship <target-branch>
```

Default target is `main` unless specified.

**What it does:**

1. Runs 5 pre-flight checks (pipeline, security, review, tests, standards)
2. If any check fails: reports what failed, why, and how to fix. Stops.
3. If all pass: validates PR description and creates the PR

**Pre-flight checks:**

| Check | What | Blocking |
|-------|------|----------|
| Pipeline | CI checks green, no suppressed failures | Yes |
| Security | No new CWE findings, no secrets in diff | Yes |
| Review | /review run, no unresolved Critical findings | Yes |
| Tests | All tests green, no unjustified skips | Yes |
| Standards | Golden principles and taste lints pass | Yes |

**Output:** Ship report with per-check PASS/FAIL, PR link if created, and follow-up items.

**When to use:** After `/review`, when you are ready to open a PR.

---

## Lifecycle vs. Old Workflow Commands

The lifecycle commands replace the numbered workflow commands that were removed in PR #1611:

| Old Command | Replacement | Notes |
|-------------|-------------|-------|
| `/0-init` | `/session-init` skill | Session initialization is now a skill, not a lifecycle phase |
| `/1-plan` | `/spec` + `/plan` | Requirements and planning are now separate phases |
| `/2-impl` | `/build` | TDD-first, atomic commits, quality scoring |
| `/3-qa` | `/test` | Expanded from 1 gate to 6 gates |
| `/4-security` | `/test` + `/review` | Security is now integrated into both test and review |

Key differences:

- **Stack-agnostic**: Commands discover the project's tech stack instead of assuming one.
- **Platform-agnostic**: Commands use `Bash(*)` instead of PowerShell-specific scripts.
- **Separated concerns**: Requirements (`/spec`) and planning (`/plan`) are distinct phases.
- **Deeper quality gates**: `/test` runs 6 specialized gates instead of a single QA pass.

## Related

- CLAUDE.md: [Lifecycle commands](../CLAUDE.md#lifecycle-commands) routing rules
- AGENTS.md: [Skill-First](../AGENTS.md#skill-first) lifecycle references
- Deprecated workflow skill: [`.claude/skills/workflow/SKILL.md`](../.claude/skills/workflow/SKILL.md)
