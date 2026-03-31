# Agent Consolidation A/B Test Specification

## Overview

**Hypothesis**: A 5-agent architecture with skill injection achieves equivalent or better task completion quality at lower operational complexity compared to the current 21+ agent architecture.

**Test Duration**: 4 weeks (2 weeks per condition)

**Date Created**: 2026-03-31

## Treatment Groups

### Control: Current Architecture (21 Agents)

| Tier | Agents | Model |
|------|--------|-------|
| Coordination | orchestrator | sonnet |
| Planning | milestone-planner, task-decomposer, roadmap | sonnet |
| Analysis | analyst, explainer, independent-thinker, high-level-advisor | sonnet |
| Architecture | architect | sonnet |
| Implementation | implementer | opus |
| Verification | critic, qa, security | opus (security), sonnet (critic, qa) |
| Support | memory, skillbook, context-retrieval | haiku |

**Total**: 21 agents, 3 model tiers

### Treatment: Proposed Architecture (5 Agents + Skills)

| Agent | Merged From | Reasoning Mode | Model |
|-------|-------------|----------------|-------|
| **Orchestrator** | orchestrator, milestone-planner, task-decomposer, roadmap | Coordination & routing | sonnet |
| **Analyst** | analyst, explainer, independent-thinker, high-level-advisor | Research & synthesis | sonnet |
| **Architect** | architect (unchanged) | System design | sonnet |
| **Builder** | implementer, debug | Code generation & fixing | opus |
| **Critic** | critic, qa, security | Adversarial verification | opus |

**Skill Packs** (injected at dispatch time):
- `security-scan`: CWE patterns, OWASP Top 10, secret detection
- `qa-checklist`: Test quality criteria, coverage validation
- `code-review`: Plan validation, completeness checks
- `spec-validation`: EARS requirements, traceability
- `planning-breakdown`: Task decomposition, milestone creation
- `strategic-advisory`: High-level guidance, trade-off analysis

**Total**: 5 agents, 2 model tiers, 6+ skill packs

## Evaluation Dimensions

### D1: Task Completion Quality

**Metric**: Task success rate (fully completed vs partial/failed)

| Measurement | Method | Target |
|-------------|--------|--------|
| Primary task completion | Binary: task objectives met | >= 95% |
| Rework rate | Count of retry/fix cycles | < 10% |
| Human intervention rate | Times user had to correct agent | < 5% |

**Data Collection**:
- Tag each task with outcome: `COMPLETE | PARTIAL | FAILED`
- Record retry count per task
- Log user correction events

### D2: Security Finding Quality

**Metric**: Vulnerability detection rate and false positive rate

| Measurement | Method | Target |
|-------------|--------|--------|
| True positive rate | Vulnerabilities found / total vulnerabilities | >= 90% |
| False positive rate | False alarms / total findings | < 15% |
| CWE coverage | Unique CWEs detected / CWEs in test corpus | >= 80% |

**Data Collection**:
- Use security test corpus with known vulnerabilities
- Run both architectures against same corpus
- Compare detection rates

### D3: Routing Accuracy

**Metric**: Correct agent selection on first attempt

| Measurement | Method | Target |
|-------------|--------|--------|
| First-attempt accuracy | Correct routing / total routings | >= 90% |
| Misrouting recovery time | Time to recover from wrong routing | < 30s |
| Cascading errors | Errors caused by misrouting | 0 |

**Data Collection**:
- Log routing decisions with rationale
- Track re-routing events
- Measure downstream impact

### D4: Execution Efficiency

**Metric**: Time and cost to complete tasks

| Measurement | Method | Target |
|-------------|--------|--------|
| Task completion time | Wall clock time per task | Treatment <= Control |
| Token consumption | Total tokens per task | Treatment < Control by 20% |
| Agent invocation count | Number of agent calls per task | Treatment < Control by 50% |
| API cost | $ per task | Treatment < Control by 30% |

**Data Collection**:
- Instrument all agent invocations
- Track token counts per call
- Calculate costs using published pricing

### D5: Context Coherence

**Metric**: Information loss during handoffs

| Measurement | Method | Target |
|-------------|--------|--------|
| Context retention | Key facts preserved across handoffs | >= 95% |
| Instruction following | Agent follows delegated instructions | >= 98% |
| Skill injection fidelity | Skill pack directives followed | >= 95% |

**Data Collection**:
- Sample handoff messages
- Check for required context elements
- Verify skill pack application

## Test Scenarios

### Scenario Set 1: Feature Implementation (Complexity: High)

| ID | Description | Expected Agents (Control) | Expected Agents (Treatment) |
|----|-------------|---------------------------|----------------------------|
| S1.1 | Add new API endpoint with auth | analyst, architect, implementer, security, qa | Analyst, Architect, Builder, Critic (security+qa skills) |
| S1.2 | Refactor module with breaking changes | analyst, architect, implementer, critic | Analyst, Architect, Builder, Critic |
| S1.3 | Add feature with cross-cutting concerns | orchestrator, analyst, architect, implementer, security, qa, devops | Orchestrator, Analyst, Architect, Builder, Critic |

### Scenario Set 2: Bug Fixes (Complexity: Medium)

| ID | Description | Expected Agents (Control) | Expected Agents (Treatment) |
|----|-------------|---------------------------|----------------------------|
| S2.1 | Fix security vulnerability | security, implementer | Critic (security skill), Builder |
| S2.2 | Fix failing tests | qa, implementer | Critic (qa skill), Builder |
| S2.3 | Fix performance regression | analyst, implementer | Analyst, Builder |

### Scenario Set 3: Documentation/Planning (Complexity: Low)

| ID | Description | Expected Agents (Control) | Expected Agents (Treatment) |
|----|-------------|---------------------------|----------------------------|
| S3.1 | Write ADR | architect, critic | Architect, Critic |
| S3.2 | Create milestone plan | milestone-planner, critic | Orchestrator (planning skill), Critic |
| S3.3 | Research external library | analyst | Analyst |

### Scenario Set 4: Security Review (Complexity: High, Critical)

| ID | Description | Expected Agents (Control) | Expected Agents (Treatment) |
|----|-------------|---------------------------|----------------------------|
| S4.1 | Review PR with auth changes | security | Critic (security skill) |
| S4.2 | Threat model new feature | security, architect | Critic (security skill), Architect |
| S4.3 | Secret scan + dependency audit | security | Critic (security skill) |

## Test Corpus

### Security Test Cases (Known Vulnerabilities)

| ID | Vulnerability | CWE | Detection Required |
|----|--------------|-----|-------------------|
| SEC-001 | SQL Injection | CWE-89 | Input validation missing |
| SEC-002 | Path Traversal | CWE-22 | GetFullPath not used |
| SEC-003 | Command Injection | CWE-78 | Unquoted variables in shell |
| SEC-004 | Hardcoded Secret | CWE-798 | API key in source |
| SEC-005 | XSS | CWE-79 | Unsanitized output |
| SEC-006 | SSRF | CWE-918 | Unvalidated URL |
| SEC-007 | Deserialization | CWE-502 | Untrusted data deserialized |
| SEC-008 | IDOR | CWE-639 | Missing authorization check |
| SEC-009 | Race Condition | CWE-362 | TOCTOU vulnerability |
| SEC-010 | Memory Poisoning | ASI06 | Agentic security pattern |

### Task Corpus (Complexity Distribution)

| Complexity | Count | Examples |
|------------|-------|----------|
| Low | 10 | Documentation, simple config changes |
| Medium | 15 | Bug fixes, test additions, refactors |
| High | 10 | New features, architecture changes |
| Critical | 5 | Security fixes, breaking changes |

**Total**: 40 tasks per condition (80 total)

## Success Criteria

### Primary Success (All Required)

| Criterion | Threshold | Rationale |
|-----------|-----------|-----------|
| Task success rate | Treatment >= Control | No quality regression |
| Security detection rate | Treatment >= 90% of Control | Critical capability preserved |
| API cost | Treatment < Control by 20% | Efficiency gain realized |
| Human intervention rate | Treatment <= Control | No usability regression |

### Secondary Success (Majority Required)

| Criterion | Threshold | Rationale |
|-----------|-----------|-----------|
| Token consumption | Treatment < Control by 15% | Context efficiency |
| Task completion time | Treatment <= Control * 1.1 | Acceptable latency |
| Agent invocation count | Treatment < Control by 40% | Routing simplicity |
| Context retention | Treatment >= 90% | Handoff quality |

### Failure Criteria (Any Triggers Halt)

| Criterion | Threshold | Action |
|-----------|-----------|--------|
| Security false negative | Any CWE missed that Control caught | Halt, analyze, adjust |
| Task failure rate | > 15% | Halt, root cause analysis |
| Human intervention spike | > 3x Control rate | Pause, investigate |

## Execution Protocol

### Week 1-2: Control Condition

1. Run Control architecture against Task Corpus (40 tasks)
2. Run Control against Security Test Corpus (10 cases)
3. Collect all metrics
4. Establish baseline

### Week 3-4: Treatment Condition

1. Implement 5-agent architecture with skill packs
2. Run Treatment against same Task Corpus (40 tasks)
3. Run Treatment against same Security Test Corpus
4. Collect all metrics

### Analysis Phase

1. Compare D1-D5 metrics between conditions
2. Statistical significance testing (paired t-test where applicable)
3. Qualitative analysis of failure cases
4. Generate recommendation

## Skill Pack Specifications

### security-scan (Critic skill)

```yaml
name: security-scan
triggers:
  - Auth changes
  - Secrets handling
  - External API calls
  - File operations
checklists:
  - CWE-699 categories (per current security agent)
  - OWASP Top 10:2021
  - OWASP Agentic Top 10:2026
  - Secret detection patterns
output: Security findings with severity, CWE, remediation
```

### qa-checklist (Critic skill)

```yaml
name: qa-checklist
triggers:
  - Implementation complete
  - Pre-PR validation
checklists:
  - Test quality criteria (per current qa agent)
  - Coverage thresholds
  - Fail-safe pattern verification
  - PR description validation
output: QA report with pass/fail verdict
```

### code-review (Critic skill)

```yaml
name: code-review
triggers:
  - Plan validation
  - Pre-implementation review
checklists:
  - Completeness check
  - Feasibility assessment
  - Alignment verification
  - Testability review
output: Critique with verdict (APPROVED/NEEDS REVISION)
```

## Risk Mitigations

### Risk: Skill-switching degrades quality

**Mitigation**: Clear skill activation headers in Critic prompt:
```
## Active Skill: security-scan
You are now operating in SECURITY mode. Apply the following checklist...
```

### Risk: Prompt size explosion

**Mitigation**: Progressive disclosure. Base Critic prompt contains:
- Core identity (50 tokens)
- Skill loading protocol
- Output format

Skill packs loaded on demand, not embedded in base prompt.

### Risk: Security requires Opus reasoning

**Mitigation**: Critic agent uses Opus model. Security skill pack benefits from Opus-level reasoning while sharing context window with other verification tasks.

### Risk: Parallel execution loss

**Mitigation**: If A/B test shows significant time regression, implement multi-pass Critic:
- Pass 1: security-scan skill
- Pass 2: qa-checklist skill (can run in parallel with Pass 1 in future optimization)

## Reporting

### Daily Metrics (During Test)

- Tasks attempted / completed / failed
- Agent invocations
- Token consumption
- Notable incidents

### Weekly Summary

- Dimension scores (D1-D5)
- Cumulative comparisons
- Emerging patterns

### Final Report

1. Executive summary with recommendation
2. Statistical analysis per dimension
3. Failure case studies
4. Recommended adjustments (if Treatment adopted)
5. Migration plan (if applicable)

## Appendix: Current Agent Distribution Reference

| Agent | Model (ADR-039) | Lines | Primary Function |
|-------|-----------------|-------|------------------|
| orchestrator | sonnet | 800+ | Coordination |
| analyst | sonnet | 400+ | Research |
| architect | sonnet | 600+ | Design |
| implementer | opus | 600+ | Code generation |
| critic | sonnet | 500+ | Plan validation |
| qa | sonnet | 800+ | Test strategy |
| security | opus | 800+ | Vulnerability assessment |
| devops | sonnet | 400+ | CI/CD |
| explainer | sonnet | 300+ | Documentation |
| memory | haiku | 200+ | Context retrieval |
| skillbook | haiku | 300+ | Pattern management |
| milestone-planner | sonnet | 400+ | Task breakdown |
| task-decomposer | sonnet | 300+ | Atomic tasks |
| roadmap | sonnet | 400+ | Strategic planning |
| high-level-advisor | sonnet | 400+ | Strategic guidance |
| independent-thinker | sonnet | 300+ | Contrarian analysis |
| spec-generator | sonnet | 400+ | Requirements |
| retrospective | sonnet | 300+ | Learning extraction |
| context-retrieval | haiku | 200+ | Memory search |
| backlog-generator | sonnet | 300+ | Task creation |
| adr-generator | sonnet | 300+ | ADR creation |

---

*Specification Version: 1.0*
*Author: Claude Agent*
*Review Status: Draft*
