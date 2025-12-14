# Phase 1 Implementation Plan: CWE-78 Incident Remediation

## Overview

This plan coordinates the foundational work for Issue #25 (Agent System Enhancement - CWE-78 Incident Remediation), consisting of three parallelizable issues that establish governance, documentation, and security controls for the agent system.

**Reference**: GitHub Issue #25 - Phase 1
**Estimated Duration**: 4-5 weeks
**Branch**: `enhancement/25-phase-1`

---

## Executive Summary

The CWE-78 shell injection vulnerability in `.githooks/pre-commit` (documented in SR-001-pre-commit-hook.md) exposed a systemic gap: multi-domain tasks (CI + security + architecture) bypassed orchestrator coordination. Phase 1 addresses root causes through:

1. **Issue #16**: Entry criteria to trigger orchestrator invocation
2. **Issue #17**: Agent capabilities matrix for informed selection
3. **Issue #18**: Threat models for infrastructure code

---

## Dependency Analysis

```text
+----------------+     +----------------+     +----------------+
|   Issue #16    |     |   Issue #17    |     |   Issue #18    |
| Orchestrator   |     | Capabilities   |     | Threat Model   |
| Entry Criteria |     | Matrix         |     | Documentation  |
+----------------+     +----------------+     +----------------+
        |                     |                     |
        |   NO DEPENDENCIES   |   NO DEPENDENCIES   |
        |   BETWEEN ISSUES    |   BETWEEN ISSUES    |
        v                     v                     v
+---------------------------------------------------------------+
|               Phase 2: Integration & Validation                |
+---------------------------------------------------------------+
```

**Key Finding**: All three issues are independent and can execute in parallel. They share no blocking dependencies, only a common goal of preventing future CWE-78-class incidents.

---

## Issue Breakdown

### Issue #16: Orchestrator Entry Criteria

**Duration**: 2-3 days
**Owner**: Documentation with analyst validation

#### Requirements

| Requirement | Description |
|-------------|-------------|
| Entry Criteria | Objective triggers requiring orchestrator |
| Decision Tree | Single-page flowchart, max 3 questions |
| Integration Points | Pre-commit hooks, CI, PR templates |
| Examples | 5+ scenarios demonstrating application |

#### Prerequisites

| Prerequisite | Description | Agent |
|--------------|-------------|-------|
| GitHub Actions Structure | Create `.github/workflows/` directory if not exists | devops |
| PR Template Foundation | Create `.github/PULL_REQUEST_TEMPLATE.md` if not exists | implementer |

#### Deliverables

| Artifact | Location | Agent |
|----------|----------|-------|
| Entry Criteria Doc | `docs/orchestrator-entry-criteria.md` | planner |
| Decision Flowchart | `docs/diagrams/orchestrator-decision-tree.md` | planner |
| PR Template (Create) | `.github/PULL_REQUEST_TEMPLATE.md` with routing checklist | implementer |
| CI Workflow Check | `.github/workflows/routing-check.yml` | devops |

#### Acceptance Criteria

- [ ] Retrospective validation of 10+ PRs confirms appropriate orchestrator usage patterns
- [ ] Developer answers "Should I invoke orchestrator?" within 30 seconds (validated via developer survey, n=3+)
- [ ] Zero critical-severity issues in PR reviews for tasks meeting orchestrator criteria (audited post-implementation)

---

### Issue #17: Agent Capabilities Matrix

**Duration**: 1-2 weeks
**Owner**: Analyst with architect validation

#### Agent Inventory

Agent definitions exist across three platforms with consistent naming:

| Platform | Directory | File Pattern | Example |
|----------|-----------|--------------|---------|
| Claude Code | `claude/` | `{agent}.md` | `claude/orchestrator.md` |
| VS Code Agents | `vs-code-agents/` | `{agent}.agent.md` | `vs-code-agents/orchestrator.agent.md` |
| Copilot CLI | `copilot-cli/` | `{agent}.agent.md` | `copilot-cli/orchestrator.agent.md` |

**All 18 Agents** (available on all platforms):

| Agent | Claude Code | VS Code | Copilot CLI |
|-------|-------------|---------|-------------|
| orchestrator | `claude/orchestrator.md` | `vs-code-agents/orchestrator.agent.md` | `copilot-cli/orchestrator.agent.md` |
| analyst | `claude/analyst.md` | `vs-code-agents/analyst.agent.md` | `copilot-cli/analyst.agent.md` |
| architect | `claude/architect.md` | `vs-code-agents/architect.agent.md` | `copilot-cli/architect.agent.md` |
| planner | `claude/planner.md` | `vs-code-agents/planner.agent.md` | `copilot-cli/planner.agent.md` |
| critic | `claude/critic.md` | `vs-code-agents/critic.agent.md` | `copilot-cli/critic.agent.md` |
| implementer | `claude/implementer.md` | `vs-code-agents/implementer.agent.md` | `copilot-cli/implementer.agent.md` |
| qa | `claude/qa.md` | `vs-code-agents/qa.agent.md` | `copilot-cli/qa.agent.md` |
| security | `claude/security.md` | `vs-code-agents/security.agent.md` | `copilot-cli/security.agent.md` |
| devops | `claude/devops.md` | `vs-code-agents/devops.agent.md` | `copilot-cli/devops.agent.md` |
| memory | `claude/memory.md` | `vs-code-agents/memory.agent.md` | `copilot-cli/memory.agent.md` |
| skillbook | `claude/skillbook.md` | `vs-code-agents/skillbook.agent.md` | `copilot-cli/skillbook.agent.md` |
| retrospective | `claude/retrospective.md` | `vs-code-agents/retrospective.agent.md` | `copilot-cli/retrospective.agent.md` |
| roadmap | `claude/roadmap.md` | `vs-code-agents/roadmap.agent.md` | `copilot-cli/roadmap.agent.md` |
| explainer | `claude/explainer.md` | `vs-code-agents/explainer.agent.md` | `copilot-cli/explainer.agent.md` |
| task-generator | `claude/task-generator.md` | `vs-code-agents/task-generator.agent.md` | `copilot-cli/task-generator.agent.md` |
| high-level-advisor | `claude/high-level-advisor.md` | `vs-code-agents/high-level-advisor.agent.md` | `copilot-cli/high-level-advisor.agent.md` |
| independent-thinker | `claude/independent-thinker.md` | `vs-code-agents/independent-thinker.agent.md` | `copilot-cli/independent-thinker.agent.md` |
| pr-comment-responder | `claude/pr-comment-responder.md` | `vs-code-agents/pr-comment-responder.agent.md` | `copilot-cli/pr-comment-responder.agent.md` |

#### Requirements Per Agent

- One-sentence core specialty description
- 5-10 specific capabilities
- Critical limitations
- Input/output format specifications
- Compatible agent partnerships
- Invocation guidelines (when/when not to use)
- Real-world positive and negative use cases

#### Tier Classification

| Tier | Criteria | Agents |
|------|----------|--------|
| TIER 1 | Core always-available | orchestrator, analyst, architect, planner, implementer |
| TIER 2 | Commonly utilized | critic, qa, security, devops, memory |
| TIER 3 | Specialized/infrequent | skillbook, retrospective, roadmap, explainer, task-generator, high-level-advisor, independent-thinker, pr-comment-responder |

#### Deliverables

| Artifact | Location | Agent |
|----------|----------|-------|
| Capabilities Matrix | `docs/agent-capabilities-matrix.md` | analyst |
| Agent Overlap Analysis | `.agents/analysis/agent-overlap-analysis.md` | analyst |
| Quick Reference Card | `docs/agent-quick-reference.md` | planner |
| CLAUDE.md Updates | `CLAUDE.md` | implementer |
| USING-AGENTS.md (Create) | `USING-AGENTS.md` | implementer |

#### Acceptance Criteria

- [ ] All 18 agents documented with required fields
- [ ] Tier classification assigned and justified
- [ ] Overlapping capabilities identified with disambiguation rules
- [ ] 5+ implementation examples per tier

---

### Issue #18: Threat Model Documentation

**Duration**: 1-2 weeks
**Owner**: Security agent with architect validation

#### Infrastructure Components

| Component | Privilege Level | Primary CWEs |
|-----------|----------------|--------------|
| Pre-Commit Hooks | Developer machine (full filesystem/network) | CWE-78, CWE-426 |
| CI/CD Workflows | Repo secrets, deployment credentials | CWE-798, CWE-200, CWE-276 |
| Build Scripts | Developer machine + supply chain | CWE-78, CWE-1104 |
| Configuration Files | Varies | CWE-798, CWE-200 |

#### Threat Model Template

Each threat model must include:

```markdown
## [Component] Threat Model

### Privilege Context
- Where it runs
- What access it has

### Threat Actors
- Who might attack
- Capability level

### STRIDE Analysis
| Category | Threat | Applicable | Analysis |
|----------|--------|------------|----------|
| Spoofing | [Identity-based threats] | Yes/No | [How component is/isn't vulnerable] |
| Tampering | [Data integrity threats] | Yes/No | [How component is/isn't vulnerable] |
| Repudiation | [Audit/logging gaps] | Yes/No | [How component is/isn't vulnerable] |
| Information Disclosure | [Data exposure risks] | Yes/No | [How component is/isn't vulnerable] |
| Denial of Service | [Availability threats] | Yes/No | [How component is/isn't vulnerable] |
| Elevation of Privilege | [Authorization bypass] | Yes/No | [How component is/isn't vulnerable] |

### Attack Vectors (CWE-based)
| CWE | Threat | Likelihood | Impact | Mitigation |
|-----|--------|------------|--------|------------|
| [CWE-XXX](https://cwe.mitre.org/data/definitions/XXX.html) | [Description] | Low/Med/High | Low/Med/High | [Mitigation] |

### Untrusted Inputs
- What data cannot be trusted
- Source of untrusted data

### Security Controls
- Required mitigations
- Implementation patterns
```

#### Deliverables

| Artifact | Location | Agent |
|----------|----------|-------|
| Pre-Commit Hook TM | `.agents/security/TM-001-pre-commit-hooks.md` | security |
| CI/CD Workflow TM | `.agents/security/TM-002-cicd-workflows.md` | security |
| Build Scripts TM | `.agents/security/TM-003-build-scripts.md` | security |
| Configuration Files TM | `.agents/security/TM-004-configuration-files.md` | security |
| Secure Coding Guide | `docs/secure-infrastructure-guide.md` | security |
| Security Checklist | `.github/SECURITY_CHECKLIST.md` | security |

**Security Checklist Integration**: The security checklist will be included inline in the PR template (not as a separate linked file) to ensure visibility. The `.github/SECURITY_CHECKLIST.md` file serves as the canonical source for updates, with relevant sections copied into the PR template during implementation.

#### Acceptance Criteria

- [ ] Four threat models created (pre-commit, CI/CD, build, config)
- [ ] Each model includes STRIDE analysis (using template above)
- [ ] CWE references linked to MITRE database (format: `[CWE-XXX](https://cwe.mitre.org/data/definitions/XXX.html)`)
- [ ] Secure coding patterns documented with code examples
- [ ] Security checklist inline in PR template with link to full checklist

---

## Execution Timeline

### Week 1-2: Parallel Initiation

```text
Day 1-2:    Issue #16 - Entry criteria drafting
Day 1-5:    Issue #17 - Agent capability inventory
Day 1-5:    Issue #18 - Pre-commit and CI/CD threat models
```

### Week 2-3: Primary Deliverables

```text
Day 3:      Issue #16 - Decision tree and examples
Day 6-10:   Issue #17 - Tier classification and overlap analysis
Day 6-10:   Issue #18 - Build scripts and config threat models
```

### Week 3-4: Integration and Review

```text
Day 11-12:  Issue #16 - Integration points (PR template, CI)
Day 11-14:  Issue #17 - Documentation updates (CLAUDE.md, USING-AGENTS.md)
Day 11-14:  Issue #18 - Secure coding guide compilation
```

### Week 4-5: Validation and Closure

```text
Day 15-20:  Cross-issue validation
Day 15-20:  Acceptance criteria verification
Day 20:     Phase 1 completion
```

---

## Agent Routing Plan

### Issue #16 Workflow

```text
analyst -> planner -> critic -> implementer -> devops -> qa
```

| Step | Agent | Task |
|------|-------|------|
| 1 | analyst | Research orchestrator usage patterns, identify failure modes |
| 2 | planner | Create entry criteria structure and decision tree |
| 3 | critic | Validate completeness and clarity |
| 4 | implementer | Update PR template with routing checklist |
| 5 | devops | Create CI workflow for routing validation |
| 6 | qa | Verify acceptance criteria met |

### Issue #17 Workflow

```text
analyst -> architect -> planner -> critic -> implementer -> qa
```

| Step | Agent | Task |
|------|-------|------|
| 1 | analyst | Inventory all agents, extract capabilities from definitions |
| 2 | architect | Validate tier classification, resolve overlaps |
| 3 | planner | Structure matrix format and quick reference |
| 4 | critic | Review completeness and consistency |
| 5 | implementer | Update CLAUDE.md and USING-AGENTS.md |
| 6 | qa | Verify all agents documented, examples work |

### Issue #18 Workflow

```text
security -> analyst -> architect -> critic -> implementer -> qa
```

| Step | Agent | Task |
|------|-------|------|
| 1 | security | Create threat models using STRIDE analysis |
| 2 | analyst | Research CWE references and real-world examples |
| 3 | architect | Validate security controls align with architecture |
| 4 | critic | Review threat model completeness |
| 5 | implementer | Update security checklist in PR template |
| 6 | qa | Verify threat models cover all CWEs in issue |

---

## Success Metrics

### Quantitative Metrics

| Metric | Target | Measurement Method |
|--------|--------|-------------------|
| Orchestrator usage patterns | Appropriate for 10+ PRs | Retrospective validation of PR history |
| Decision time | <30 seconds | Developer survey (n=3+) |
| Critical PR review findings | 0 for orchestrator-worthy tasks | PR review audit post-implementation |
| Agent documentation coverage | 100% (18/18 agents) | Doc validation |
| Threat model coverage | 4 component types | Artifact count |

### Qualitative Metrics

| Metric | Target | Measurement Method |
|--------|--------|-------------------|
| Developer confidence in agent selection | Improved | Post-implementation survey of 3+ developers with Likert scale (1-5) comparison to baseline |
| Security awareness for infrastructure | Documented patterns exist | Verify secure coding guide published and referenced in 2+ PRs |
| Orchestrator utilization | Intentional, not accidental | Retrospective interview with 3+ developers confirming decision criteria are clear |

---

## Validation Checkpoints

### Checkpoint 1: Issue #16 Complete (Day 4)

- [ ] Entry criteria document reviewed and approved
- [ ] Decision tree validated by 2+ developers
- [ ] Examples cover all required scenarios

*Note: 1-day buffer built in to account for agent handoff delays*

### Checkpoint 2: Issue #17 Midpoint (Day 7)

- [ ] All 18 agents inventoried
- [ ] Tier classification draft complete
- [ ] Overlap analysis in progress

### Checkpoint 3: Issue #18 Midpoint (Day 7)

- [ ] Pre-commit and CI/CD threat models complete
- [ ] CWE references validated
- [ ] Security controls documented

### Checkpoint 4: Integration Ready (Day 14)

- [ ] All primary deliverables complete
- [ ] Cross-references validated
- [ ] No blocking issues

### Checkpoint 5: Phase 1 Complete (Day 20)

- [ ] All acceptance criteria met
- [ ] Documentation merged to main
- [ ] Retrospective scheduled for Phase 2

---

## Risk Mitigation

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Agent definitions inconsistent across platforms | Medium | Medium | Create single-source-of-truth in matrix |
| Threat models too abstract | Medium | High | Include concrete code examples |
| Entry criteria too complex | Low | High | Limit decision tree to 3 questions |
| Parallel work creates merge conflicts | Low | Low | Separate file paths per issue |
| Security agent unavailable | Low | High | Analyst can draft, security validates |
| CI workflow breaks builds | Low | Medium | Iterative rollout; start with PR-only triggers |
| No baseline data for metrics | High | Medium | Accept qualitative validation for Phase 1; establish baseline for Phase 2 |

---

## Rollback Strategy

If Phase 1 deliverables cause issues:

### Branch Strategy
- All work on `enhancement/25-phase-1` branch
- No direct commits to `main`
- PRs require approval before merge

### Revert Procedures

| Issue | Rollback Action |
|-------|-----------------|
| CI workflow breaks | Disable workflow via GitHub UI or revert commit |
| PR template causes confusion | Revert to previous template or remove routing checklist |
| Documentation errors | Direct edit and push fix within 24 hours |

### Recovery Checklist
- [ ] Identify failing component
- [ ] Communicate issue to team
- [ ] Execute revert if needed
- [ ] Document root cause
- [ ] Plan remediation before re-deployment

---

## Commit Strategy

### Issue #16 Commits

1. `docs(orchestrator): add entry criteria documentation`
2. `docs(orchestrator): add decision tree flowchart`
3. `feat(ci): add orchestrator routing check workflow`
4. `chore(templates): update PR template with routing checklist`

### Issue #17 Commits

1. `docs(agents): add capabilities matrix structure`
2. `docs(agents): complete tier 1 agent documentation`
3. `docs(agents): complete tier 2 agent documentation`
4. `docs(agents): complete tier 3 agent documentation`
5. `docs(agents): add overlap analysis and disambiguation`
6. `docs: update CLAUDE.md and USING-AGENTS.md with matrix reference`

### Issue #18 Commits

1. `docs(security): add pre-commit hook threat model TM-001`
2. `docs(security): add CI/CD workflow threat model TM-002`
3. `docs(security): add build scripts threat model TM-003`
4. `docs(security): add configuration files threat model TM-004`
5. `docs(security): add secure infrastructure guide`
6. `chore(templates): add security checklist to PR template`

---

## Handoff to Phase 2

Upon Phase 1 completion:

1. **Retrospective**: Document learnings in `.agents/retrospective/`
2. **Memory Update**: Store patterns in cloudmcp-manager
3. **Phase 2 Planning**: Begin auto-routing and tooling implementation
4. **Metrics Baseline**: Establish measurement for Phase 2 comparison

---

## Appendix A: File Structure After Phase 1

```text
.agents/
  analysis/
    agent-overlap-analysis.md          # Issue #17
  architecture/
    (no new ADRs for Phase 1)
  planning/
    phase1-implementation-plan.md      # This document
  security/
    SR-001-pre-commit-hook.md          # Existing
    TM-001-pre-commit-hooks.md         # Issue #18
    TM-002-cicd-workflows.md           # Issue #18
    TM-003-build-scripts.md            # Issue #18
    TM-004-configuration-files.md      # Issue #18

docs/
  orchestrator-entry-criteria.md       # Issue #16
  diagrams/
    orchestrator-decision-tree.md      # Issue #16
  agent-capabilities-matrix.md         # Issue #17
  agent-quick-reference.md             # Issue #17
  secure-infrastructure-guide.md       # Issue #18

.github/
  PULL_REQUEST_TEMPLATE.md             # Created: #16, #18 (with routing + security checklist)
  SECURITY_CHECKLIST.md                # Issue #18 (canonical source)
  workflows/
    routing-check.yml                  # Issue #16 (created with directory)
```

---

## Appendix B: Agent Selection Quick Reference

| Task Type | Primary Agent | Support Agents |
|-----------|---------------|----------------|
| Entry criteria drafting | planner | analyst |
| Decision tree creation | planner | architect |
| Agent inventory | analyst | - |
| Tier classification | architect | analyst |
| Threat modeling | security | analyst, architect |
| Documentation updates | implementer | - |
| CI workflow creation | devops | security |
| Validation | qa | critic |

---

## Appendix C: CWE Reference

| CWE ID | Name | Applies To |
|--------|------|------------|
| CWE-78 | OS Command Injection | Pre-commit, Build |
| CWE-426 | Untrusted Search Path | Pre-commit |
| CWE-798 | Hardcoded Credentials | CI/CD, Config |
| CWE-200 | Exposure of Sensitive Info | CI/CD, Config |
| CWE-276 | Incorrect Default Permissions | CI/CD |
| CWE-1104 | Use of Unmaintained Third Party Components | Build |

---

*Plan created: 2025-12-13*
*Plan revised: 2025-12-13*
*Plan version: 1.1*
*Status: REVISED - READY FOR RE-REVIEW*

---

## Revision History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2025-12-13 | Initial plan |
| 1.1 | 2025-12-13 | Addressed critic findings from `.agents/critique/phase1-plan-review.md` |

### Changes in Version 1.1

**Critical Issues Resolved:**
- C1: Added explicit STRIDE analysis section to threat model template (lines 171-179)
- C2: Revised Issue #16 acceptance criteria to use retrospective validation instead of unmeasurable 80% metric

**Important Issues Resolved:**
- I1: Changed USING-AGENTS.md from "Updates" to "(Create)"
- I2: Added Prerequisites section for GitHub Actions structure and PR template foundation
- I3: Updated Agent Inventory table to reflect actual file locations across all three platforms (claude/, vs-code-agents/, copilot-cli/)
- I4: Changed PR Template from "Updates" to "(Create)" with routing checklist
- I5: Added specific measurement methods for all qualitative metrics

**Minor Issues Addressed:**
- M1: Built 1-day buffer into Checkpoint 1 (Day 3 -> Day 4)
- M2: Added Rollback Strategy section with branch strategy and revert procedures
- M3: Specified MITRE hyperlink format in threat model template
- M4: Clarified security checklist integration method (inline in PR template)
