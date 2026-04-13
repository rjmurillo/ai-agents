# Handoff Terms Specification

**Purpose**: Define consistent terminology for agent handoffs, verdicts, and status indicators across all workflows.

**Scope**: This document is the single source of truth for handoff vocabulary between agents, GitHub workflows, and orchestration systems.

## Quick Reference

| Category | Terms | Used By |
|----------|-------|---------|
| General Status | PASS, FAIL, WARNING, COMPLETE, BLOCKED, PENDING | All agents |
| QA Verdicts | PASS, FAIL, NEEDS WORK | QA agent |
| Security Verdicts | APPROVED, CONDITIONAL, REJECTED | Security agent |
| Critic Verdicts | APPROVED, NEEDS REVISION, REJECTED | Critic agent |
| Plan Status | PENDING, IN PROGRESS, COMPLETE, BLOCKED | Planner agent |
| Orchestrator Determinations | N/A (not triggered) | Orchestrator only |

## General Status Indicators

All agents use these text status indicators in their output:

| Term | Meaning | When to Use |
|------|---------|-------------|
| **[PASS]** | Check succeeded | Validation passed, test passed, requirement met |
| **[FAIL]** | Check failed | Validation failed, test failed, requirement not met |
| **[WARNING]** | Non-blocking concern | Issue identified but not blocking progress |
| **[COMPLETE]** | Work finished | Task or phase finished successfully |
| **[BLOCKED]** | Cannot proceed | Dependencies missing or blocking issues exist |
| **[PENDING]** | Not yet started | Work item queued but not begun |
| **[IN PROGRESS]** | Currently active | Work item being executed |
| **[SKIP]** | Intentionally omitted | Test or step deliberately not run |
| **[FLAKY]** | Intermittent result | Test has inconsistent pass/fail behavior |

## Agent-Specific Verdicts

### QA Agent Verdicts

The QA agent returns these verdicts for quality validation:

| Verdict | Meaning | Orchestrator Action |
|---------|---------|---------------------|
| **PASS** | All quality checks pass | Proceed to next phase |
| **FAIL** | Critical quality issues | Route to implementer with failure list |
| **NEEDS WORK** | Non-critical issues found | Route to implementer with issue list |

**Usage in handoff message:**

```text
QA COMPLETE: All tests passing. [PASS]
QA FAILED: Tests failed. Recommend orchestrator routes to implementer with failures: [list]
```

### Security Agent Verdicts

The security agent returns these verdicts for Post-Implementation Verification (PIV):

| Verdict | Meaning | Orchestrator Action |
|---------|---------|---------------------|
| **APPROVED** | No security concerns | Proceed to PR creation |
| **CONDITIONAL** | Minor, non-blocking concerns documented | Proceed to PR; include security notes in description |
| **REJECTED** | Critical security issues | Route to implementer; do NOT create PR |

**CONDITIONAL vs REJECTED:**

- **CONDITIONAL**: Approved with documented concerns. Does not block PR creation. Reviewers should be aware of noted items for future follow-up.
- **REJECTED**: Blocking issues that must be fixed before PR creation.

**Usage in handoff message:**

```text
Security PIV APPROVED: Implementation meets security requirements.
Security PIV CONDITIONAL: Approved with minor considerations documented. Include notes in PR description.
Security PIV REJECTED: Critical issues found. Route to implementer with: [list]
```

### Critic Agent Verdicts

The critic agent returns these verdicts for plan validation:

| Verdict | Meaning | Orchestrator Action |
|---------|---------|---------------------|
| **APPROVED** | Plan ready for implementation | Route to implementer |
| **NEEDS REVISION** | Plan has gaps or issues | Route to planner with issue list |
| **REJECTED** | Fundamental problems | Route to analyst for research |

**Usage in handoff message:**

```text
Plan approved. Recommend orchestrator routes to implementer for execution.
Plan needs revision. Recommend orchestrator routes to planner with these issues: [list]
Plan rejected. Recommend orchestrator routes to analyst for research on: [questions]
```

## Orchestrator-Only Determinations

These are NOT agent verdicts. They are orchestrator decisions:

| Term | Meaning | Context |
|------|---------|---------|
| **N/A** | Validation not triggered | Orchestrator determined the change is not relevant to a particular validation type (e.g., not security-relevant) |

**Important**: Agents do NOT return N/A. The orchestrator uses N/A when it decides not to route to a particular agent.

## Handoff Message Format

### Standard Handoff Structure

All agents use this format when returning control to orchestrator:

```text
[Phase] [STATUS]: [Summary]. Recommend orchestrator routes to [agent] for [next step].
```

**Examples:**

```text
Analysis COMPLETE: Root cause identified. Recommend orchestrator routes to planner for work breakdown.
Implementation COMPLETE: All changes made and tested. Recommend orchestrator routes to qa for verification.
QA COMPLETE: All tests passing. Ready for security review or PR creation.
Security PIV APPROVED: No concerns. Proceed to PR creation.
```

### Blocking Handoff Structure

When work cannot proceed:

```text
[Phase] [BLOCKED/FAILED]: [Issue summary]. Recommend orchestrator routes to [agent] with: [specific items]
```

**Examples:**

```text
QA FAILED: 3 tests failing. Recommend orchestrator routes to implementer with failures:
1. TestUserLogin: Expected 200, got 401
2. TestDataValidation: Null reference exception
3. TestCacheExpiry: Timeout after 30s
```

## Cross-Agent Terminology Alignment

### Pre-PR Validation Flow

| Step | Agent | Input | Output Verdict |
|------|-------|-------|----------------|
| 1 | QA | Implementation | PASS / FAIL / NEEDS WORK |
| 2 | Orchestrator | QA verdict | Continue / Route to implementer |
| 3 | Security (if triggered) | Implementation | APPROVED / CONDITIONAL / REJECTED |
| 4 | Orchestrator | All verdicts | APPROVED (create PR) / BLOCKED (fix first) |

### Plan Validation Flow

| Step | Agent | Input | Output Verdict |
|------|-------|-------|----------------|
| 1 | Planner | Epic/Requirements | Plan document |
| 2 | Critic | Plan document | APPROVED / NEEDS REVISION / REJECTED |
| 3 | Orchestrator | Critic verdict | Route to implementer / planner / analyst |

## GitHub Workflow Integration

When GitHub workflows interact with agent verdicts:

| Workflow Event | Agent Verdict | Workflow Action |
|----------------|---------------|-----------------|
| CI tests pass | QA: PASS | Continue pipeline |
| CI tests fail | QA: FAIL | Block merge, notify |
| Security scan clean | Security: APPROVED | Continue pipeline |
| Security scan warnings | Security: CONDITIONAL | Continue with notes |
| Security scan critical | Security: REJECTED | Block merge, notify |

## Anti-Patterns

### Do NOT Use

| Incorrect | Correct | Reason |
|-----------|---------|--------|
| APPROVED for QA | PASS | QA uses PASS/FAIL/NEEDS WORK |
| BLOCKED for security | REJECTED | Security uses APPROVED/CONDITIONAL/REJECTED |
| N/A as agent output | (orchestrator only) | N/A is orchestrator determination |
| Emoji status ✅❌ | Text [PASS][FAIL] | Accessibility and parsing |

### Consistent Vocabulary

Always use the exact terms from this specification. Do not use synonyms:

| Incorrect | Correct |
|-----------|---------|
| SUCCESS | PASS |
| FAILURE | FAIL |
| PASSED | PASS |
| FAILED | FAIL |
| OK | PASS |
| ERROR | FAIL |
| GOOD | APPROVED |
| BAD | REJECTED |

