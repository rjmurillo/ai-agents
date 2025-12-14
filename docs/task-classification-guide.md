# Task Classification Guide

## Purpose

This guide provides a systematic approach to classifying tasks for optimal agent routing. Accurate classification ensures tasks are routed to agents with the right capabilities.

## Classification Dimensions

Every task is classified across three dimensions:

1. **Task Type**: What kind of work is this?
2. **Complexity Level**: How many steps/domains are involved?
3. **Risk Level**: What's the potential impact of errors?

---

## Dimension 1: Task Type

### Feature Development

**Indicators**:

- New functionality requested
- User-facing changes
- New API endpoints or UI components
- "Add", "Create", "Implement" in request

**Agent Sequence**: `analyst -> architect -> planner -> critic -> implementer -> qa`

### Bug Fix

**Indicators**:

- Something is broken or not working correctly
- Error messages or stack traces mentioned
- "Fix", "Broken", "Not working" in request
- Regression from previous behavior

**Agent Sequence**: `analyst -> implementer -> qa`

### Infrastructure

**Indicators**:

- CI/CD pipeline changes
- Build script modifications
- Git hooks or workflow files
- Docker/container configuration
- Deployment automation

**Agent Sequence**: `devops -> security -> critic -> qa`

### Security

**Indicators**:

- Authentication/authorization changes
- Credential handling
- Vulnerability remediation
- Security audit request
- Files in `**/Auth/**`, `**/Security/**`

**Agent Sequence**: `security -> architect -> implementer -> qa`

### Strategic/Planning

**Indicators**:

- Architecture decisions
- Technology choices
- Long-term direction
- Epic or milestone planning

**Agent Sequence**: `roadmap -> architect -> planner -> critic`

### Research/Investigation

**Indicators**:

- "Why does X happen?"
- Root cause analysis
- Technology evaluation
- "How does X work?"

**Agent Sequence**: `analyst` (often standalone)

### Documentation

**Indicators**:

- README updates
- API documentation
- User guides
- Architecture diagrams

**Agent Sequence**: `explainer -> critic`

### Refactoring

**Indicators**:

- Code cleanup without functional changes
- Performance optimization
- Technical debt reduction
- "Refactor", "Clean up", "Improve" in request

**Agent Sequence**: `analyst -> architect -> implementer -> qa`

---

## Dimension 2: Complexity Level

### Simple

**Definition**: Single agent can complete the task independently.

**Indicators**:

- Single file change
- Well-defined scope
- No cross-cutting concerns
- Clear success criteria
- No research required

**Routing**: Direct to single agent, no orchestration needed.

**Examples**:

- Fix typo in documentation
- Add single unit test
- Update configuration value
- Rename a variable

### Multi-Step

**Definition**: Sequential agents required, each building on previous output.

**Indicators**:

- Multiple files affected
- Requires planning before implementation
- Some research needed
- Clear handoff points between agents

**Routing**: Orchestrator coordinates agent sequence.

**Examples**:

- Implement new API endpoint with tests
- Add feature with documentation
- Fix bug that spans multiple components

### Multi-Domain

**Definition**: Multiple specialized agents working on parallel concerns.

**Indicators**:

- Cross-cutting concerns (security + architecture)
- Multiple stakeholders affected
- Parallel workstreams possible
- Complex tradeoffs required

**Routing**: Orchestrator REQUIRED. Multiple agent tracks.

**Examples**:

- New authentication system (security + architecture + implementation)
- CI/CD pipeline overhaul (devops + security + qa)
- Major refactoring with security implications

---

## Dimension 3: Risk Level

### Low Risk

**Definition**: Errors have minimal impact and are easily reversible.

**Indicators**:

- Documentation-only changes
- Test file modifications
- Non-production code
- Easy to revert

**Routing**: Minimal validation required.

### Medium Risk

**Definition**: Errors could cause regressions but are detectable.

**Indicators**:

- Production code changes with test coverage
- Feature flag protected changes
- Internal tooling modifications

**Routing**: QA validation required.

### High Risk

**Definition**: Errors could cause significant issues.

**Indicators**:

- Authentication/authorization changes
- Payment processing code
- Data migration scripts
- Infrastructure changes

**Routing**: Security + Critic + QA validation required.

### Critical Risk

**Definition**: Errors could cause security breaches or data loss.

**Indicators**:

- Credential handling
- Encryption/decryption code
- User data processing
- Infrastructure security
- Shell script execution

**Routing**: Full validation chain required. Security agent MANDATORY.

---

## Quick Classification Matrix

| If the task involves... | Task Type | Likely Complexity | Minimum Risk |
|------------------------|-----------|-------------------|--------------|
| New user feature | Feature | Multi-Step | Medium |
| Something broken | Bug Fix | Simple/Multi-Step | Medium |
| `.github/workflows/*` | Infrastructure | Multi-Domain | High |
| `**/Auth/**` | Security | Multi-Domain | Critical |
| "Why does X..." | Research | Simple | Low |
| README/docs | Documentation | Simple | Low |
| "Clean up X" | Refactoring | Multi-Step | Medium |
| Epic planning | Strategic | Multi-Domain | Low |
| `.githooks/*` | Infrastructure | Multi-Step | Critical |
| Shell scripts | Infrastructure | Multi-Step | Critical |

---

## Classification Examples

### Example 1: CWE-78 Shell Injection Fix

**Request**: "Fix shell injection vulnerability in pre-commit hook"

**Classification**:

- Task Type: **Security** (vulnerability fix)
- Complexity: **Multi-Domain** (security + devops + qa)
- Risk: **Critical** (shell injection, infrastructure)

**Routing**: `security -> devops -> critic -> qa`

### Example 2: Add Logout Button

**Request**: "Add logout button to user menu"

**Classification**:

- Task Type: **Feature** (new functionality)
- Complexity: **Multi-Step** (design + implement + test)
- Risk: **High** (authentication related)

**Routing**: `analyst -> security -> architect -> implementer -> qa`

### Example 3: Fix Typo in README

**Request**: "Fix typo in README.md"

**Classification**:

- Task Type: **Documentation**
- Complexity: **Simple**
- Risk: **Low**

**Routing**: Direct fix, no orchestration.

### Example 4: New OAuth Integration

**Request**: "Implement OAuth2 integration for third-party login"

**Classification**:

- Task Type: **Feature** + **Security**
- Complexity: **Multi-Domain** (security + architecture + auth + testing)
- Risk: **Critical** (authentication)

**Routing**: `analyst -> security -> architect -> planner -> critic -> implementer -> qa`

### Example 5: CI Pipeline Optimization

**Request**: "Speed up CI pipeline by 50%"

**Classification**:

- Task Type: **Infrastructure**
- Complexity: **Multi-Step** (analysis + implementation)
- Risk: **High** (could break builds)

**Routing**: `analyst -> devops -> critic -> qa`

---

## Decision Flowchart

```text
START
  |
  v
[Is the task security-related?]
  |
  +--YES--> Security agent ALWAYS involved
  |           Risk = High or Critical
  |
  +--NO---> Continue
            |
            v
[Does task involve infrastructure?]
  |
  +--YES--> DevOps agent primary
  |           Security agent validation
  |           Risk = High minimum
  |
  +--NO---> Continue
            |
            v
[Is this research/investigation only?]
  |
  +--YES--> Analyst agent standalone
  |           No implementation
  |
  +--NO---> Continue
            |
            v
[Does task span multiple domains?]
  |
  +--YES--> Orchestrator REQUIRED
  |           Multi-agent sequence
  |
  +--NO---> Single agent may suffice
            |
            v
[Does task require implementation?]
  |
  +--YES--> Plan before implement
  |           QA validation after
  |
  +--NO---> Documentation/planning only
            |
            v
CLASSIFY and ROUTE
```

---

## Related Documents

- [Orchestrator Routing Algorithm](./orchestrator-routing-algorithm.md)
- [Routing Flowchart](./diagrams/routing-flowchart.md)
- [Agent Interview Protocol](../.agents/governance/agent-interview-protocol.md)

---

*Document Version: 1.0*
*Created: 2025-12-13*
*GitHub Issue: #5*
