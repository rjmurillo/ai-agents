# Phase 2 Implementation Plan: CWE-78 Incident Remediation

## Overview

This plan coordinates the implementation of Phase 2 issues for GitHub Issue #4 (Agent System Enhancement - CWE-78 Incident Remediation). Phase 1 is complete (Issues #11, #12, #13), providing the foundation for Phase 2 work.

**Reference**: GitHub Issue #4 - Phase 2
**Estimated Duration**: 8-12 weeks
**Branch**: `enhancement/4-phase-2`
**Prerequisites**: Phase 1 complete (Issues #11, #12, #13 all CLOSED)

---

## Executive Summary

Phase 2 implements the operational capabilities built on Phase 1's foundation:

| Issue | Title | Effort | Key Deliverable |
|-------|-------|--------|-----------------|
| #6 | Agent Interview Protocol | 3-5 days | Capability discovery process |
| #5 | Orchestrator Routing Logic | 1-2 weeks | Task-to-agent routing algorithm |
| #10 | Security Agent Enhancement | 2-4 weeks | 5 security capabilities |
| #9 | Auto-trigger Security Agent | 1-2 weeks | Infrastructure detection |
| #8 | Governance Framework | 2-3 weeks | ADR templates, steering charter |
| #7 | Agent Invocation Metrics | 1-2 weeks | 8 key metrics + dashboard |

**Recommended Order**: #6 -> #5 -> (#10 || #8) -> #9 -> #7

---

## Dependency Analysis

```text
PHASE 1 (COMPLETE)
+----------------+     +----------------+     +----------------+
|   Issue #13    |     |   Issue #12    |     |   Issue #11    |
| Entry Criteria |     | Capabilities   |     | Threat Models  |
|    [DONE]      |     | Matrix [DONE]  |     |    [DONE]      |
+----------------+     +----------------+     +----------------+
        |                     |                     |
        +----------+----------+---------------------+
                   |
                   v
PHASE 2 DEPENDENCIES
+------------------------------------------------------------------+
|                                                                   |
|   #6 Interview Protocol  <-- Foundation for capability discovery  |
|          |                                                        |
|          v                                                        |
|   #5 Routing Logic  <-- Needs #13 + #12 + benefits from #6        |
|          |                                                        |
|          +---------------+---------------+                        |
|          |               |               |                        |
|          v               v               v                        |
|   #10 Security     #8 Governance    #7 Metrics                    |
|   Enhancement      Framework        (partial)                     |
|          |               |                                        |
|          v               |                                        |
|   #9 Auto-trigger  <-----+                                        |
|          |                                                        |
|          v                                                        |
|   #7 Metrics (completion - after #9 for infrastructure metrics)   |
+------------------------------------------------------------------+
```

**Critical Path**: #6 -> #5 -> #10 -> #9 -> #7 (completion)

---

## Optimal Implementation Order

### Rationale

1. **#6 First** - Interview Protocol creates the process for validating and updating agent capabilities, directly supporting all other Phase 2 work
2. **#5 Second** - Routing Logic depends on Entry Criteria (#13) and Capabilities Matrix (#12), both complete; also benefits from #6's structured capability format
3. **#10 Third** - Security Enhancement is a prerequisite for #9 (Auto-trigger)
4. **#8 Parallel with #10** - Governance Framework is independent of security work
5. **#9 Fourth** - Auto-trigger requires enhanced security agent (#10)
6. **#7 Last** - Metrics can be partially implemented early but require #9 for infrastructure review metrics

### Implementation Waves

```text
WAVE 1 (Week 1-2)
+------------------+
| #6 Interview     | <-- Start here (3-5 days)
| Protocol         |
+------------------+
         |
         v
+------------------+
| #5 Routing Logic | <-- Start after #6 (1-2 weeks)
+------------------+

WAVE 2 (Week 2-5) - Parallel
+------------------+     +------------------+
| #10 Security     |     | #8 Governance    |
| Enhancement      |     | Framework        |
| (2-4 weeks)      |     | (2-3 weeks)      |
+------------------+     +------------------+

WAVE 3 (Week 5-7)
+------------------+
| #9 Auto-trigger  | <-- Requires #10 complete
| (1-2 weeks)      |
+------------------+

WAVE 4 (Week 7-9)
+------------------+
| #7 Metrics       | <-- Requires #9 for full metrics
| (1-2 weeks)      |
+------------------+
```

---

## Issue #6: Agent Interview Protocol

**Duration**: 3-5 days
**Owner**: Analyst with planner support
**Priority**: P0 - Start first

### Requirements Summary

Create repeatable process for agent capability discovery with:
- 8 standardized interview questions
- Consistent response format feeding into capabilities matrix
- Interview cadence (new agents: pre-release; existing: annual or on-change)
- Quality assurance process

### Deliverables

| Artifact | Location | Agent |
|----------|----------|-------|
| Interview Protocol | `.agents/governance/agent-interview-protocol.md` | planner |
| Response Template | `.agents/governance/interview-response-template.md` | planner |
| Sample Interview (Security Agent) | `.agents/governance/interviews/security-interview.md` | analyst |
| Capabilities Matrix Link | Update `docs/agent-capabilities-matrix.md` to reference protocol | implementer |

### Directory Structure

```text
.agents/
  governance/                           # NEW directory
    agent-interview-protocol.md         # Issue #6 main deliverable
    interview-response-template.md      # Standardized format
    interviews/                         # Interview results
      security-interview.md             # Sample (validates format)
```

### Integration Points

- Links to Capabilities Matrix (#12)
- Supports Governance Framework (#8)
- Informs Orchestrator Routing (#5)

### Commit Strategy

1. `feat(governance): create agent interview protocol (#6)`
   - Create `.agents/governance/agent-interview-protocol.md`
   - Create `.agents/governance/interview-response-template.md`

2. `feat(governance): add security agent interview sample (#6)`
   - Create `.agents/governance/interviews/security-interview.md`

3. `docs: link interview protocol to capabilities matrix (#6)`
   - Update reference in capabilities documentation

### Acceptance Criteria

- [ ] 8 standardized questions documented
- [ ] Response template created and validated
- [ ] At least 1 sample interview completed (security agent)
- [ ] Protocol referenced from capabilities matrix

---

## Issue #5: Orchestrator Routing Logic

**Duration**: 1-2 weeks
**Owner**: Architect with analyst validation
**Priority**: P0 - Start after #6

### Requirements Summary

Create explicit routing algorithm for task-to-agent assignment:
- Task type classification (feature, bug, infrastructure, security, strategic)
- Complexity assessment (simple, multi-step, multi-domain)
- Risk level determination (low, medium, high, critical)
- Execution strategy (serial vs. parallel)
- Result synthesis

### Deliverables

| Artifact | Location | Agent |
|----------|----------|-------|
| Routing Algorithm | `docs/orchestrator-routing-algorithm.md` | architect |
| Task Classification Guide | `docs/task-classification-guide.md` | planner |
| Routing Flowchart | `docs/diagrams/routing-flowchart.md` | planner |
| Orchestrator Update | Update `claude/orchestrator.md` with routing reference | implementer |
| VS Code Agent Update | Update `vs-code-agents/orchestrator.agent.md` | implementer |

### Directory Structure

```text
docs/
  orchestrator-routing-algorithm.md     # Issue #5 main deliverable
  task-classification-guide.md          # Supporting guide
  diagrams/
    routing-flowchart.md                 # Visual representation
```

### Integration Points

- Consumes Entry Criteria from #13
- Consumes Capabilities Matrix from #12
- Uses Interview Protocol from #6 for capability lookup
- Referenced by Governance Framework #8

### Commit Strategy

1. `feat(routing): create task classification guide (#5)`
   - Create `docs/task-classification-guide.md`

2. `feat(routing): create orchestrator routing algorithm (#5)`
   - Create `docs/orchestrator-routing-algorithm.md`
   - Create `docs/diagrams/routing-flowchart.md`

3. `feat(routing): add execution strategy documentation (#5)`
   - Add serial vs. parallel rules
   - Add result synthesis guidance

4. `chore(agents): update orchestrator with routing reference (#5)`
   - Update `claude/orchestrator.md`
   - Update `vs-code-agents/orchestrator.agent.md`
   - Update `copilot-cli/orchestrator.agent.md`

### Acceptance Criteria

- [ ] Routing algorithm documented as flowchart/pseudocode
- [ ] Algorithm handles multi-domain tasks correctly
- [ ] CWE-78 incident validated against algorithm (would have routed correctly)
- [ ] 3-5 real scenarios documented with expected routing

---

## Issue #10: Security Agent Enhancement

**Duration**: 2-4 weeks
**Owner**: Security agent with architect validation
**Priority**: P1 - Start after #5, can parallel with #8

### Requirements Summary

Expand security agent from threat modeling to 5 comprehensive capabilities:
1. Static analysis & vulnerability scanning (CWE detection)
2. Secret detection & environment leak scanning
3. Code quality audit (security perspective)
4. Architecture & boundary security audit
5. Best practices enforcement

### Deliverables

| Artifact | Location | Agent |
|----------|----------|-------|
| Security Agent Update (Claude) | `claude/security.md` | implementer |
| Security Agent Update (VS Code) | `vs-code-agents/security.agent.md` | implementer |
| Security Agent Update (Copilot) | `copilot-cli/security.agent.md` | implementer |
| Static Analysis Checklist | `.agents/security/static-analysis-checklist.md` | security |
| Secret Detection Patterns | `.agents/security/secret-detection-patterns.md` | security |
| Code Quality Security Guide | `.agents/security/code-quality-security.md` | security |
| Architecture Security Template | `.agents/security/architecture-security-template.md` | security |
| Best Practices Enforcement | `.agents/security/security-best-practices.md` | security |

### Directory Structure

```text
.agents/
  security/                             # Existing directory
    static-analysis-checklist.md        # NEW - Capability 1
    secret-detection-patterns.md        # NEW - Capability 2
    code-quality-security.md            # NEW - Capability 3
    architecture-security-template.md   # NEW - Capability 4
    security-best-practices.md          # NEW - Capability 5
```

### Integration Points

- Consumes Threat Models from #11
- Consumed by Auto-trigger (#9)
- Referenced in Capabilities Matrix (#12)
- Subject to Governance Framework (#8)

### Commit Strategy

1. `feat(security): add static analysis checklist with CWE patterns (#10)`
   - Create `.agents/security/static-analysis-checklist.md`
   - Include CWE-78, CWE-79, CWE-89, CWE-200, CWE-287 patterns

2. `feat(security): add secret detection patterns (#10)`
   - Create `.agents/security/secret-detection-patterns.md`
   - Include API key, token, credential patterns

3. `feat(security): add code quality security guide (#10)`
   - Create `.agents/security/code-quality-security.md`
   - Include LOC thresholds, complexity metrics

4. `feat(security): add architecture security audit template (#10)`
   - Create `.agents/security/architecture-security-template.md`
   - Include privilege boundary analysis, trust boundaries

5. `feat(security): add best practices enforcement guide (#10)`
   - Create `.agents/security/security-best-practices.md`
   - Include input validation, error handling, logging

6. `feat(agents): expand security agent capabilities (#10)`
   - Update `claude/security.md` with 5 capabilities
   - Update `vs-code-agents/security.agent.md`
   - Update `copilot-cli/security.agent.md`

### Acceptance Criteria

- [ ] Security agent includes 5 documented capabilities
- [ ] CWE-78 shell injection pattern included in static analysis
- [ ] All 3 platforms updated with consistent capabilities
- [ ] Interview protocol (#6) completed for updated security agent

---

## Issue #8: Governance Framework

**Duration**: 2-3 weeks
**Owner**: Architect with analyst support
**Priority**: P1 - Can parallel with #10

### Requirements Summary

Establish governance framework for agent system evolution:
- ADR template for agent decisions
- Steering committee charter
- Agent design principles
- Consolidation process for overlapping agents

### Deliverables

| Artifact | Location | Agent |
|----------|----------|-------|
| ADR Template | `.agents/architecture/ADR-TEMPLATE.md` | architect |
| Steering Committee Charter | `.agents/governance/steering-committee-charter.md` | architect |
| Agent Design Principles | `.agents/governance/agent-design-principles.md` | architect |
| Consolidation Process | `.agents/governance/agent-consolidation-process.md` | planner |
| Governance Overview | `docs/agent-governance.md` | planner |

### Directory Structure

```text
.agents/
  architecture/
    ADR-TEMPLATE.md                     # NEW - Agent decision template
  governance/                           # Directory from #6
    steering-committee-charter.md       # NEW
    agent-design-principles.md          # NEW
    agent-consolidation-process.md      # NEW

docs/
  agent-governance.md                   # NEW - Public overview
```

### Integration Points

- References Interview Protocol (#6)
- References Capabilities Matrix (#12)
- Informs all future agent additions/changes
- Supports Metrics interpretation (#7)

### Commit Strategy

1. `feat(governance): create ADR template for agent decisions (#8)`
   - Create `.agents/architecture/ADR-TEMPLATE.md`

2. `feat(governance): create steering committee charter (#8)`
   - Create `.agents/governance/steering-committee-charter.md`

3. `feat(governance): document agent design principles (#8)`
   - Create `.agents/governance/agent-design-principles.md`
   - Include: non-overlapping, clear entry criteria, explicit limitations

4. `feat(governance): document agent consolidation process (#8)`
   - Create `.agents/governance/agent-consolidation-process.md`
   - Include: 20% overlap threshold, migration paths

5. `docs: create agent governance overview (#8)`
   - Create `docs/agent-governance.md`
   - Link all governance artifacts

### Acceptance Criteria

- [ ] ADR template created and validated
- [ ] Steering committee charter defined with cadence
- [ ] Design principles documented (6 principles from issue)
- [ ] Consolidation process documented with triggers

---

## Issue #9: Auto-trigger Security Agent

**Duration**: 1-2 weeks
**Owner**: DevOps with security validation
**Priority**: P2 - Requires #10 complete

### Requirements Summary

Automatically detect and recommend security review for infrastructure changes:
- File pattern detection for high-risk files
- Pre-commit hook integration (warning only)
- PR template integration with checkbox

### Deliverables

| Artifact | Location | Agent |
|----------|----------|-------|
| File Pattern Configuration | `.agents/security/infrastructure-file-patterns.md` | security |
| Pre-commit Hook Update | `.githooks/pre-commit` | devops |
| Security Detection Script | `.agents/utilities/security-detection/detect-infrastructure.ps1` | devops |
| Security Detection Script (Python) | `.agents/utilities/security-detection/detect_infrastructure.py` | devops |
| PR Template Update | `.github/PULL_REQUEST_TEMPLATE.md` | implementer |

### Directory Structure

```text
.agents/
  security/
    infrastructure-file-patterns.md     # NEW - Pattern definitions
  utilities/
    security-detection/                 # NEW directory
      detect-infrastructure.ps1         # PowerShell detector
      detect_infrastructure.py          # Python detector
      SKILL.md                          # Documentation

.github/
  PULL_REQUEST_TEMPLATE.md              # CREATE or UPDATE

.githooks/
  pre-commit                            # UPDATE with detection
```

### File Patterns to Detect

Based on Issue #9 requirements:

```text
.github/workflows/*          # CI/CD pipelines
.githooks/*                  # Pre-commit/post-commit hooks
src/**/Controllers/*         # API endpoints
src/**/Auth/**               # Authentication code
src/**/Security/**           # Security utilities
build/scripts/*              # Build scripts
Dockerfile                   # Container security
docker-compose.yml           # Container orchestration
appsettings*.json            # Configuration files
*.env*                       # Environment files
```

### Integration Points

- Requires Security Agent Enhancement (#10)
- Uses patterns from Threat Models (#11)
- Supports Metrics (#7) - infrastructure review rate

### Commit Strategy

1. `feat(security): define infrastructure file patterns (#9)`
   - Create `.agents/security/infrastructure-file-patterns.md`

2. `feat(tools): add infrastructure detection utility (#9)`
   - Create `.agents/utilities/security-detection/detect-infrastructure.ps1`
   - Create `.agents/utilities/security-detection/detect_infrastructure.py`
   - Create `.agents/utilities/security-detection/SKILL.md`

3. `feat(hooks): add security warning to pre-commit hook (#9)`
   - Update `.githooks/pre-commit` with detection call
   - Non-blocking warning only

4. `feat(templates): add security review checkbox to PR template (#9)`
   - Create/update `.github/PULL_REQUEST_TEMPLATE.md`
   - Add infrastructure security review checkbox

### Acceptance Criteria

- [ ] File patterns documented and validated
- [ ] Pre-commit hook warns on infrastructure changes
- [ ] PR template includes security review checkbox
- [ ] Warning is non-blocking (does not prevent commit)

---

## Issue #7: Agent Invocation Metrics

**Duration**: 1-2 weeks
**Owner**: DevOps with analyst support
**Priority**: P2 - Complete after #9 for full metrics

### Requirements Summary

Implement 8 key metrics for agent system observability:
1. Invocation rate by agent
2. Agent coverage (% commits with agent review)
3. Shift-left effectiveness
4. Infrastructure code review rate
5. Usage distribution by agent
6. Agent review turnaround time
7. Vulnerability discovery timeline
8. Compliance with agent policies

### Deliverables

| Artifact | Location | Agent |
|----------|----------|-------|
| Metrics Definition | `docs/agent-metrics.md` | analyst |
| Metrics Collection Script | `.agents/utilities/metrics/collect-metrics.ps1` | devops |
| Metrics Collection Script (Python) | `.agents/utilities/metrics/collect_metrics.py` | devops |
| CI Workflow | `.github/workflows/agent-metrics.yml` | devops |
| Dashboard Template | `.agents/metrics/dashboard-template.md` | planner |
| Baseline Report | `.agents/metrics/baseline-report.md` | analyst |

### Directory Structure

```text
.agents/
  metrics/                              # NEW directory
    dashboard-template.md               # Metric visualization template
    baseline-report.md                  # Initial baseline
  utilities/
    metrics/                            # NEW directory
      collect-metrics.ps1               # PowerShell collector
      collect_metrics.py                # Python collector
      SKILL.md                          # Documentation

.github/
  workflows/
    agent-metrics.yml                   # CI job for metrics

docs/
  agent-metrics.md                      # Public metric definitions
```

### Integration Points

- Requires Infrastructure Detection (#9) for review rate metric
- Consumes Capabilities Matrix (#12) for agent identification
- Informs Governance Framework (#8) decisions

### Commit Strategy

1. `feat(metrics): define 8 key agent metrics (#7)`
   - Create `docs/agent-metrics.md`

2. `feat(tools): add metrics collection utility (#7)`
   - Create `.agents/utilities/metrics/collect-metrics.ps1`
   - Create `.agents/utilities/metrics/collect_metrics.py`
   - Create `.agents/utilities/metrics/SKILL.md`

3. `feat(metrics): create dashboard template (#7)`
   - Create `.agents/metrics/dashboard-template.md`

4. `feat(ci): add agent metrics workflow (#7)`
   - Create `.github/workflows/agent-metrics.yml`

5. `docs(metrics): establish baseline measurements (#7)`
   - Create `.agents/metrics/baseline-report.md`
   - Document current state as baseline

### Acceptance Criteria

- [ ] 8 metrics defined with measurement methods
- [ ] CI job implemented for automated collection
- [ ] Dashboard template created
- [ ] Baseline established for trend tracking

---

## Execution Timeline

### Week 1-2: Foundation

```text
Day 1-3:    Issue #6 - Interview protocol drafting
Day 3-5:    Issue #6 - Response template and sample interview
Day 4-10:   Issue #5 - Routing algorithm development
```

### Week 2-5: Core Implementation (Parallel Tracks)

```text
Track A: Security
  Day 8-20:   Issue #10 - Security agent 5 capabilities

Track B: Governance
  Day 8-18:   Issue #8 - Governance framework
```

### Week 5-7: Auto-Detection

```text
Day 21-28:  Issue #9 - Auto-trigger implementation
```

### Week 7-9: Observability

```text
Day 29-38:  Issue #7 - Metrics implementation
```

### Week 9-10: Integration and Validation

```text
Day 39-45:  Cross-issue validation
Day 45:     Phase 2 completion
```

---

## Agent Routing Plan

### Issue #6 Workflow

```text
analyst -> planner -> critic -> implementer
```

| Step | Agent | Task |
|------|-------|------|
| 1 | analyst | Research interview best practices |
| 2 | planner | Create protocol structure and template |
| 3 | critic | Validate completeness of questions |
| 4 | implementer | Create sample interview, link to matrix |

### Issue #5 Workflow

```text
analyst -> architect -> planner -> critic -> implementer
```

| Step | Agent | Task |
|------|-------|------|
| 1 | analyst | Analyze task patterns and routing needs |
| 2 | architect | Design routing algorithm |
| 3 | planner | Create task classification guide |
| 4 | critic | Validate algorithm against CWE-78 incident |
| 5 | implementer | Update orchestrator agents |

### Issue #10 Workflow

```text
security -> analyst -> architect -> critic -> implementer
```

| Step | Agent | Task |
|------|-------|------|
| 1 | security | Define 5 capability specifications |
| 2 | analyst | Research CWE patterns and detection methods |
| 3 | architect | Validate capabilities align with architecture |
| 4 | critic | Review for completeness and overlap |
| 5 | implementer | Update security agent on all platforms |

### Issue #8 Workflow

```text
architect -> analyst -> planner -> critic -> implementer
```

| Step | Agent | Task |
|------|-------|------|
| 1 | architect | Design ADR template and principles |
| 2 | analyst | Research governance best practices |
| 3 | planner | Structure consolidation process |
| 4 | critic | Validate governance is actionable |
| 5 | implementer | Create all governance artifacts |

### Issue #9 Workflow

```text
security -> devops -> critic -> implementer -> qa
```

| Step | Agent | Task |
|------|-------|------|
| 1 | security | Define file patterns and detection rules |
| 2 | devops | Implement detection scripts and hooks |
| 3 | critic | Validate detection completeness |
| 4 | implementer | Update PR template |
| 5 | qa | Test detection against known patterns |

### Issue #7 Workflow

```text
analyst -> devops -> architect -> critic -> implementer -> qa
```

| Step | Agent | Task |
|------|-------|------|
| 1 | analyst | Define metrics and measurement methods |
| 2 | devops | Implement collection scripts and CI |
| 3 | architect | Review metrics align with governance goals |
| 4 | critic | Validate metrics are measurable |
| 5 | implementer | Create dashboard template |
| 6 | qa | Verify baseline establishment |

---

## Success Metrics

### Quantitative Metrics

| Metric | Target | Measurement Method |
|--------|--------|-------------------|
| Interview protocol coverage | 100% of agents | Audit interview completion |
| Routing algorithm accuracy | 100% for CWE-78 scenario | Scenario validation |
| Security capabilities | 5 documented | Artifact count |
| Infrastructure detection | 100% of patterns | Test against known files |
| Metrics collection | 8 metrics baselined | CI job output |

### Qualitative Metrics

| Metric | Target | Measurement Method |
|--------|--------|-------------------|
| Developer routing confidence | Improved | Post-implementation survey |
| Security review clarity | Clear process exists | Documentation review |
| Governance adoption | Used for next agent change | First ADR created |

---

## Risk Mitigation

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Security enhancement scope creep | Medium | High | Strict 5-capability scope |
| Pre-commit hook breaks workflow | Medium | High | Non-blocking warning only |
| Metrics collection performance | Low | Medium | Async CI job, no blocking |
| Governance too bureaucratic | Medium | Medium | Lightweight templates |
| Cross-platform agent sync issues | Low | Medium | Single commit per platform update |

---

## Rollback Strategy

### Branch Strategy

- All work on `enhancement/4-phase-2` branch
- Feature branches for each issue: `enhancement/4-issue-N`
- PRs require approval before merge to main

### Revert Procedures

| Issue | Rollback Action |
|-------|-----------------|
| #6 Interview Protocol | Remove `.agents/governance/` directory |
| #5 Routing Logic | Remove routing docs, revert orchestrator |
| #10 Security Agent | Revert agent files to previous version |
| #9 Auto-trigger | Remove detection scripts, revert hook |
| #8 Governance | Remove governance docs |
| #7 Metrics | Disable CI workflow, remove scripts |

---

## Validation Checkpoints

### Checkpoint 1: Foundation Complete (Week 2)

- [ ] Issue #6 Interview Protocol complete
- [ ] Issue #5 Routing Algorithm complete
- [ ] CWE-78 scenario validated against routing

### Checkpoint 2: Security Enhanced (Week 5)

- [ ] Issue #10 Security Agent has 5 capabilities
- [ ] Issue #8 Governance Framework complete
- [ ] Security agent interview completed

### Checkpoint 3: Auto-Detection Working (Week 7)

- [ ] Issue #9 Auto-trigger implemented
- [ ] Pre-commit hook tested
- [ ] PR template updated

### Checkpoint 4: Phase 2 Complete (Week 9)

- [ ] Issue #7 Metrics baselined
- [ ] All acceptance criteria met
- [ ] Cross-issue validation complete

---

## File Structure After Phase 2

```text
.agents/
  architecture/
    ADR-001-markdown-linting.md         # Existing
    ADR-TEMPLATE.md                     # Issue #8
  governance/                           # NEW from #6
    agent-interview-protocol.md         # Issue #6
    interview-response-template.md      # Issue #6
    interviews/
      security-interview.md             # Issue #6
    steering-committee-charter.md       # Issue #8
    agent-design-principles.md          # Issue #8
    agent-consolidation-process.md      # Issue #8
  metrics/                              # NEW from #7
    dashboard-template.md               # Issue #7
    baseline-report.md                  # Issue #7
  security/
    static-analysis-checklist.md        # Issue #10
    secret-detection-patterns.md        # Issue #10
    code-quality-security.md            # Issue #10
    architecture-security-template.md   # Issue #10
    security-best-practices.md          # Issue #10
    infrastructure-file-patterns.md     # Issue #9
  utilities/
    fix-markdown-fences/                # Existing
    security-detection/                 # NEW from #9
      detect-infrastructure.ps1         # Issue #9
      detect_infrastructure.py          # Issue #9
      SKILL.md                          # Issue #9
    metrics/                            # NEW from #7
      collect-metrics.ps1               # Issue #7
      collect_metrics.py                # Issue #7
      SKILL.md                          # Issue #7

.github/
  workflows/
    agent-metrics.yml                   # Issue #7
  PULL_REQUEST_TEMPLATE.md              # Issue #9

docs/
  orchestrator-routing-algorithm.md     # Issue #5
  task-classification-guide.md          # Issue #5
  agent-governance.md                   # Issue #8
  agent-metrics.md                      # Issue #7
  diagrams/
    routing-flowchart.md                # Issue #5

claude/
  security.md                           # Updated by #10
  orchestrator.md                       # Updated by #5

vs-code-agents/
  security.agent.md                     # Updated by #10
  orchestrator.agent.md                 # Updated by #5

copilot-cli/
  security.agent.md                     # Updated by #10
  orchestrator.agent.md                 # Updated by #5
```

---

## Handoff to Phase 3

Upon Phase 2 completion:

1. **Retrospective**: Document learnings in `.agents/retrospective/phase-2-retrospective.md`
2. **Memory Update**: Store patterns in cloudmcp-manager
3. **Metrics Analysis**: Review baseline and set improvement targets
4. **Success Validation**: Verify CWE-78 incident would now be caught pre-implementation

---

## Appendix A: Commit Message Reference

All commits should reference the GitHub issue number:

```text
# Feature commits
feat(governance): create agent interview protocol (#6)
feat(routing): create orchestrator routing algorithm (#5)
feat(security): expand security agent capabilities (#10)
feat(hooks): add security warning to pre-commit hook (#9)
feat(governance): create steering committee charter (#8)
feat(metrics): define 8 key agent metrics (#7)

# Documentation commits
docs: link interview protocol to capabilities matrix (#6)
docs: create agent governance overview (#8)
docs(metrics): establish baseline measurements (#7)

# Chore commits
chore(agents): update orchestrator with routing reference (#5)
chore(templates): add security review checkbox to PR template (#9)
```

---

## Appendix B: Agent Selection Quick Reference

| Task Type | Primary Agent | Support Agents |
|-----------|---------------|----------------|
| Interview protocol creation | planner | analyst |
| Routing algorithm design | architect | analyst, planner |
| Security capability expansion | security | analyst, architect |
| Governance framework | architect | planner, analyst |
| Infrastructure detection | devops | security |
| Metrics implementation | devops | analyst |
| Documentation updates | implementer | - |
| Validation | qa | critic |

---

## Appendix C: Issue Cross-Reference

| Issue | Depends On | Enables |
|-------|------------|---------|
| #6 | #12 (done) | #5, #8, all future agents |
| #5 | #12, #13 (done), benefits from #6 | Automated routing |
| #10 | #12 (done) | #9 |
| #8 | #12 (done), #6 | All future governance |
| #9 | #10 | #7 (infrastructure metric) |
| #7 | #12 (done), #9 | Governance decisions |

---

*Plan created: 2025-12-13*
*Plan version: 1.0*
*Status: READY FOR REVIEW*
