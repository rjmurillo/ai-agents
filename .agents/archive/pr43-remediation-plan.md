# PR #43 Remediation Plan: CodeRabbit Review Findings

**Date**: 2025-12-15
**Source PR**: #43 (feat/templates)
**Source Documents**:
- `.agents/retrospective/pr43-coderabbit-root-cause-analysis.md`
- `.agents/analysis/pr43-agent-capability-gap-analysis.md`

---

## Executive Summary

CodeRabbit identified **7 issues** in PR #43, stemming from **5 systemic patterns** and **15 agent capability gaps** across 9 agents. This plan organizes remediation into **4 workstreams** with **23 actionable items**.

### Issue Summary

| ID | Issue | Severity | Pattern |
|----|-------|----------|---------|
| I1 | Escalation prompt missing critical data | Major | Information Loss |
| I2 | QA conditions not tracked in work breakdown | Major | Cross-Document Consistency |
| I3 | Absolute Windows paths in references | Critical | Environment Contamination |
| I4 | Effort estimate discrepancy (12-16 vs 8-14 hrs) | Major | Cross-Document Consistency |
| I5 | Naming convention violation (no PREFIX-NNN) | Major | Naming Drift |
| I6 | Memory estimate inconsistency | Major | Cross-Document Consistency |
| I7 | Security analysis incomplete (post-impl) | Critical | Single-Phase Security |

### Systemic Patterns

1. **Cross-Document Consistency** (Issues 2, 4, 6) - No automated validation
2. **Information Loss During Synthesis** (Issues 1, 2) - Data summarized away
3. **Environment Contamination** (Issue 3) - Absolute paths in docs
4. **Naming Convention Drift** (Issue 5) - Inconsistent artifact naming
5. **Single-Phase Security Review** (Issue 7) - No post-implementation verification

---

## Priority Matrix

### P0 - Critical (Security, Path Contamination)

| Item | Issue | Agent | Workstream | Effort |
|------|-------|-------|------------|--------|
| P0-1 | I3 | explainer | WS1 | 0.5h |
| P0-2 | I7 | security | WS1 | 1.5h |
| P0-3 | I7 | implementer | WS1 | 1h |
| P0-4 | I3 | (tooling) | WS2 | 2h |

### P1 - High (Consistency, Information Loss)

| Item | Issue | Agent | Workstream | Effort |
|------|-------|-------|------------|--------|
| P1-1 | I1 | critic | WS1 | 1h |
| P1-2 | I4 | task-generator | WS1 | 1h |
| P1-3 | I2 | planner | WS1 | 1.5h |
| P1-4 | I2, I4, I6 | (tooling) | WS2 | 3h |

### P2 - Medium (Naming, Templates, Process)

| Item | Issue | Agent | Workstream | Effort |
|------|-------|-------|------------|--------|
| P2-1 | I5 | roadmap | WS1 | 0.5h |
| P2-2 | I6 | memory | WS1 | 1h |
| P2-3 | I2 | orchestrator | WS1 | 0.5h |
| P2-4 | I5 | (docs) | WS3 | 1h |
| P2-5 | - | (process) | WS4 | 1h |

### P3 - Low (Nice-to-Haves)

| Item | Issue | Agent | Workstream | Effort |
|------|-------|-------|------------|--------|
| P3-1 | - | (all) | WS1 | 2h |
| P3-2 | - | (docs) | WS3 | 0.5h |

**Total Effort**: ~17.5 hours

---

## Workstream 1: Agent Prompt Updates

### P0-1: Explainer Path Normalization

**Issue Reference**: I3 (CodeRabbit: absolute Windows paths)
**Affected Agent**: explainer
**Root Cause**: No constraint against absolute paths in documentation

**Remediation Action**:
Add path normalization requirements to `src/claude/explainer.md`:

```markdown
## Path Normalization Requirements

**Constraint**: All file paths in documentation MUST be repository-relative.

**What to Do**:
1. When referencing files, convert absolute paths to relative:
   - Wrong: `D:\src\GitHub\user\repo\.agents\analysis\file.md`
   - Right: `.agents/analysis/file.md`

2. Use forward slashes for cross-platform compatibility:
   - Wrong: `.agents\analysis\file.md`
   - Right: `.agents/analysis/file.md`

3. Before finalizing any document with file references, verify no absolute paths remain.

**Validation Regex**: `[A-Z]:\\|\/Users\/|\/home\/` (should return 0 matches)
```

**Acceptance Criteria**:
- [ ] Path normalization section added to explainer.md
- [ ] Validation regex documented
- [ ] Anti-pattern example included

**Effort**: 0.5 hours
**Dependencies**: None

---

### P0-2: Security Post-Implementation Verification

**Issue Reference**: I7 (CodeRabbit: security analysis incomplete)
**Affected Agent**: security
**Root Cause**: Security review at design phase only, no post-implementation step

**Remediation Action**:
Add post-implementation verification section to `src/claude/security.md`:

```markdown
## Post-Implementation Security Verification

### Security-Relevant Change Triggers

Request post-implementation verification when implementer creates:
- [ ] New scripts with file system access
- [ ] CI/CD workflow changes
- [ ] Path manipulation logic
- [ ] Environment variable handling
- [ ] External command execution (Invoke-Expression, Start-Process)
- [ ] User input processing

### Verification Checklist (Post-Implementation)

- [ ] Implemented controls match design-phase recommendations
- [ ] No hardcoded credentials or secrets
- [ ] Path validation implemented (Test-PathWithinRoot or equivalent)
- [ ] Error messages do not leak sensitive information
- [ ] Input validation present for all external inputs

### Output

Save post-implementation findings to: `.agents/security/PIV-NNN-[feature].md`
```

**Acceptance Criteria**:
- [ ] Post-implementation verification section added
- [ ] Security-relevant change triggers documented
- [ ] Verification checklist included
- [ ] PIV output template specified

**Effort**: 1.5 hours
**Dependencies**: None

---

### P0-3: Implementer Security Flagging

**Issue Reference**: I7 (CodeRabbit: security analysis incomplete)
**Affected Agent**: implementer
**Root Cause**: No self-identification of security-relevant code

**Remediation Action**:
Add security flagging protocol to `src/claude/implementer.md`:

```markdown
## Security-Relevant Code Flagging

### Self-Assessment Triggers

| Pattern | Security Relevance |
|---------|-------------------|
| File system operations | High |
| Path manipulation | High |
| Environment variables | Medium |
| External command execution | Critical |
| User input handling | High |
| Network operations | High |
| Credential handling | Critical |

### Protocol

If any trigger applies:
1. Add to commit message: `[security-relevant]`
2. Note in handoff: "Security-relevant changes - recommend security verification"
3. Include in TODO: `- [ ] Request security post-implementation review`
```

**Acceptance Criteria**:
- [ ] Security-relevant triggers table added
- [ ] Flagging protocol documented
- [ ] Handoff section updated with security handoff option

**Effort**: 1 hour
**Dependencies**: P0-2 (security agent must have verification capability)

---

### P1-1: Critic Escalation Template

**Issue Reference**: I1 (CodeRabbit: escalation prompt missing data)
**Affected Agent**: critic
**Root Cause**: No structured template requiring all verified facts

**Remediation Action**:
Add escalation completeness requirements to `src/claude/critic.md`:

```markdown
### Escalation Prompt Completeness Requirements

When escalating to high-level-advisor, the prompt MUST include:

## Mandatory Escalation Data

### Verified Facts (exact values, not summaries)
| Fact | Value | Source |
|------|-------|--------|
| [Data point] | [Exact value] | [Where verified] |

### Numeric Data
- [All percentages, hours, counts from analysis]

### Conflicting Positions
| Agent | Position | Rationale |
|-------|----------|-----------|

### Decision Questions
1. [Specific question requiring resolution]

**Anti-Pattern**: Converting "99%+ overlap (VS Code/Copilot), 60-70% (Claude)" to "80-90% overlap" loses actionable detail.
```

**Acceptance Criteria**:
- [ ] Escalation template with mandatory fields added
- [ ] Anti-pattern example documented
- [ ] Numeric data preservation requirement explicit

**Effort**: 1 hour
**Dependencies**: None

---

### P1-2: Task-Generator Estimate Reconciliation

**Issue Reference**: I4 (CodeRabbit: effort estimate discrepancy)
**Affected Agent**: task-generator
**Root Cause**: No comparison of derived estimates with source

**Remediation Action**:
Add estimate reconciliation protocol to `src/claude/task-generator.md`:

```markdown
## Estimate Reconciliation Protocol

**Requirement**: Derived estimates MUST be compared with source document estimates.

### Process

1. **Extract source estimate** from epic/PRD before generating tasks
2. **Sum task estimates** after task breakdown complete
3. **Compare**: If derived estimate differs from source by >10%:

| Source | Derived | Difference | Action Required |
|--------|---------|------------|-----------------|
| [Epic hours] | [Task total] | [%] | [See below] |

4. **Reconciliation Actions** (choose one):
   - Update source: Note in output and recommend epic update
   - Document rationale: Explain difference in output
   - Flag for review: If uncertain, flag for critic/planner review

### Output Template Addition

## Estimate Reconciliation

**Source Document**: [Epic/PRD filename]
**Source Estimate**: [X-Y hours]
**Derived Estimate**: [A-B hours]
**Difference**: [+/-N%]
**Status**: [Aligned | Reconciled | Flagged for review]
**Rationale** (if divergent): [Why estimates differ]
```

**Acceptance Criteria**:
- [ ] Estimate reconciliation protocol added
- [ ] 10% threshold documented
- [ ] Output template section included
- [ ] Reconciliation actions specified

**Effort**: 1 hour
**Dependencies**: None

---

### P1-3: Planner Condition-to-Task Traceability

**Issue Reference**: I2 (CodeRabbit: QA conditions not tracked)
**Affected Agent**: planner
**Root Cause**: Multi-source synthesis loses traceability

**Remediation Action**:
Add condition traceability section to `src/claude/planner.md`:

```markdown
### Condition-to-Task Traceability

When aggregating specialist reviews, ENSURE:

1. **All conditions attached to tasks**: Each condition from specialist reviews must be linked to specific task IDs
2. **Conditions visible in task definitions**: Update Work Breakdown table to include condition flags

**Work Breakdown Template with Conditions**:

| Task ID | Description | Effort | Conditions |
|---------|-------------|--------|------------|
| TASK-001 | [Task name] | [Est.] | None |
| TASK-006 | [Task name] | [Est.] | QA: Requires test spec file path |

**Validation Checklist**:
- [ ] Every specialist condition has a task assignment
- [ ] Work Breakdown table reflects all conditions
- [ ] No orphan conditions (conditions without task links)

**Anti-Pattern**: Putting conditions in a separate section without cross-references to tasks.
```

**Acceptance Criteria**:
- [ ] Condition traceability section added
- [ ] Work Breakdown template with Conditions column
- [ ] Validation checklist included
- [ ] Anti-pattern documented

**Effort**: 1.5 hours
**Dependencies**: None

---

### P2-1: Roadmap Naming Conventions

**Issue Reference**: I5 (CodeRabbit: naming convention violation)
**Affected Agent**: roadmap
**Root Cause**: No naming convention for epic files

**Remediation Action**:
Add naming conventions to `src/claude/roadmap.md`:

```markdown
## Artifact Naming Conventions

### Epic Files

**Pattern**: `EPIC-NNN-[kebab-case-name].md`

**Examples**:
- `EPIC-001-user-authentication.md`
- `EPIC-002-api-versioning.md`

### Numbering

- Start at 001 for new projects
- Increment sequentially
- Never reuse numbers
- Check existing files before assigning: `ls .agents/roadmap/EPIC-*.md`

**Anti-Pattern**: Using `epic-[name].md` without numeric prefix.
```

**Acceptance Criteria**:
- [ ] EPIC-NNN pattern documented
- [ ] Numbering rules specified
- [ ] Check command for existing files included

**Effort**: 0.5 hours
**Dependencies**: P2-4 (central naming conventions doc)

---

### P2-2: Memory Estimate Freshness

**Issue Reference**: I6 (CodeRabbit: memory estimate inconsistency)
**Affected Agent**: memory
**Root Cause**: Point-in-time snapshots without refresh triggers

**Remediation Action**:
Add estimate freshness protocol to `src/claude/memory.md`:

```markdown
## Estimate Freshness Protocol

### Problem

Memory snapshots capture point-in-time data. When downstream agents refine estimates, stored values become stale.

### Protocol

1. **Before storing estimates**, verify they are current:
   - Check if task breakdown exists for the epic
   - If yes, use task-derived estimate (more accurate)
   - If no, use epic estimate (preliminary)

2. **When storing**, include source and freshness indicator:
   ```json
   {
     "observations": [
       "Effort: 12-16 hours total (from tasks-*.md, 2025-12-15)",
       "Original epic estimate: 8-14 hours (superseded)"
     ]
   }
   ```

3. **Update triggers** - Refresh memory when:
   - Task breakdown is completed for an epic
   - Estimate reconciliation occurs
   - Critic flags estimate discrepancy

**Anti-Pattern**: Storing epic estimate after task breakdown exists.
```

**Acceptance Criteria**:
- [ ] Freshness protocol added
- [ ] Update triggers documented
- [ ] Source tracking in observations shown
- [ ] Anti-pattern documented

**Effort**: 1 hour
**Dependencies**: None

---

### P2-3: Orchestrator Consistency Checkpoint

**Issue Reference**: I2 (coordination gap)
**Affected Agent**: orchestrator
**Root Cause**: No validation before critic handoff

**Remediation Action**:
Add pre-critic validation to `src/claude/orchestrator.md`:

```markdown
**Pre-Critic Validation Checkpoint**:

Before routing planner output to critic, verify:
- [ ] All specialist consultations returned findings
- [ ] Each specialist condition has a task assignment in Work Breakdown
- [ ] Effort estimates reconciled (derived vs source)
- [ ] No orphan conditions in aggregated summary

If validation fails, return to planner for completion before critic review.
```

**Acceptance Criteria**:
- [ ] Pre-critic checkpoint added
- [ ] Validation checklist included
- [ ] Failure action specified (return to planner)

**Effort**: 0.5 hours
**Dependencies**: P1-3 (planner traceability)

---

### P3-1: Cross-Agent Handoff Validation

**Issue Reference**: General process improvement
**Affected Agents**: All agents with handoffs
**Root Cause**: No receiving-agent validation

**Remediation Action**:
Add to each agent's handoff section:

```markdown
### Receiving Agent Validation

When receiving handoff, verify:
- [ ] Required sections present
- [ ] Data completeness (no "[TBD]" or "[TODO]" placeholders)
- [ ] Cross-references valid (referenced files exist)
- [ ] Estimates provided where expected
- [ ] If validation fails, return to sender with specific gaps
```

**Acceptance Criteria**:
- [ ] Validation checklist added to critic.md
- [ ] Validation checklist added to implementer.md
- [ ] Validation checklist added to qa.md
- [ ] Validation checklist added to task-generator.md

**Effort**: 2 hours (across all agents)
**Dependencies**: All P0/P1 items

---

## Workstream 2: CI/Tooling Infrastructure

### P0-4: Path Normalization CI Check

**Issue Reference**: I3 (absolute Windows paths)
**Affected Components**: CI workflow, markdown files
**Root Cause**: No automated detection of environment-specific paths

**Remediation Action**:
Create CI validation script and workflow:

**Script**: `build/Validate-PathNormalization.ps1`

```powershell
# Scan markdown files for absolute paths
# Fail if patterns found: [A-Z]:\, /Users/, /home/
param(
    [string]$Path = ".agents",
    [switch]$Fix
)

$patterns = @(
    '[A-Z]:\\',           # Windows absolute
    '/Users/[^/]+/',      # macOS absolute
    '/home/[^/]+/'        # Linux absolute
)

# Implementation details...
```

**Workflow**: `.github/workflows/validate-paths.yml`

```yaml
name: Validate Path Normalization
on:
  pull_request:
    paths:
      - '.agents/**/*.md'
      - 'docs/**/*.md'
jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Check for absolute paths
        run: pwsh build/Validate-PathNormalization.ps1
```

**Acceptance Criteria**:
- [ ] PowerShell script created and tested
- [ ] CI workflow created
- [ ] Workflow triggers on .agents/ and docs/ changes
- [ ] Clear error messages with file:line references

**Effort**: 2 hours
**Dependencies**: None

---

### P1-4: Cross-Document Consistency Validation

**Issue Reference**: I2, I4, I6 (estimate discrepancies, conditions not tracked)
**Affected Components**: CI workflow, planning artifacts
**Root Cause**: No automated consistency checking

**Remediation Action**:
Create consistency validation script and workflow:

**Script**: `build/Validate-PlanningArtifacts.ps1`

```powershell
# Validates consistency across planning artifacts
# Checks:
# 1. Effort estimates (epic vs tasks vs memory) - flag >20% divergence
# 2. Task coverage (PRD requirements vs task assignments)
# 3. Condition traceability (specialist conditions vs work breakdown)

param(
    [string]$FeatureName,
    [switch]$CI
)

# Implementation details...
```

**Workflow**: Add to `.github/workflows/validate-generated-agents.yml`

```yaml
- name: Validate planning artifact consistency
  run: |
    $features = Get-ChildItem .agents/roadmap/EPIC-*.md | ForEach-Object { $_.BaseName -replace 'EPIC-\d+-', '' }
    foreach ($feature in $features) {
      pwsh build/Validate-PlanningArtifacts.ps1 -FeatureName $feature -CI
    }
```

**Acceptance Criteria**:
- [ ] Script validates estimate consistency (20% threshold)
- [ ] Script validates condition-to-task traceability
- [ ] CI integration added
- [ ] Detailed report output with specific discrepancies

**Effort**: 3 hours
**Dependencies**: P1-2, P1-3 (agents must produce reconciled outputs)

---

## Workstream 3: Documentation

### P2-4: Central Naming Conventions Document

**Issue Reference**: I5 (naming drift)
**Affected Components**: All agents, governance docs
**Root Cause**: No centralized naming standard

**Remediation Action**:
Create `.agents/governance/naming-conventions.md`:

```markdown
# Agent Artifact Naming Conventions

## Sequenced Artifacts (use PREFIX-NNN)

| Type | Pattern | Example | Location |
|------|---------|---------|----------|
| Epic | `EPIC-NNN-[name].md` | `EPIC-001-auth.md` | `.agents/roadmap/` |
| Critique | `NNN-[name]-critique.md` | `001-auth-critique.md` | `.agents/critique/` |
| Threat Model | `TM-NNN-[name].md` | `TM-001-auth.md` | `.agents/security/` |
| Security Report | `SR-NNN-[name].md` | `SR-001-auth.md` | `.agents/security/` |
| ADR | `ADR-NNN-[name].md` | `ADR-001-auth.md` | `.agents/architecture/` |
| PIV | `PIV-NNN-[name].md` | `PIV-001-auth.md` | `.agents/security/` |

## Type-Prefixed Artifacts (no number)

| Type | Pattern | Example | Location |
|------|---------|---------|----------|
| PRD | `prd-[name].md` | `prd-auth.md` | `.agents/planning/` |
| Tasks | `tasks-[name].md` | `tasks-auth.md` | `.agents/planning/` |
| Plan | `implementation-plan-[name].md` | `implementation-plan-auth.md` | `.agents/planning/` |
| Impact Analysis | `impact-analysis-[name]-[domain].md` | `impact-analysis-auth-security.md` | `.agents/planning/` |
| Handoff | `handoff-[name].md` | `handoff-auth.md` | `.agents/planning/` |

## Session and Analysis Artifacts

| Type | Pattern | Example | Location |
|------|---------|---------|----------|
| Ideation | `ideation-[topic].md` | `ideation-agent-templating.md` | `.agents/analysis/` |
| Root Cause | `[source]-root-cause-analysis.md` | `pr43-coderabbit-root-cause-analysis.md` | `.agents/retrospective/` |
| Gap Analysis | `[source]-[type]-gap-analysis.md` | `pr43-agent-capability-gap-analysis.md` | `.agents/analysis/` |
| Remediation | `[source]-remediation-plan.md` | `pr43-remediation-plan.md` | `.agents/planning/` |

## Naming Rules

1. **Use kebab-case**: `user-authentication` not `user_authentication`
2. **Keep names concise**: 2-4 words maximum
3. **Consistent names across related artifacts**: `EPIC-001-auth.md`, `prd-auth.md`, `tasks-auth.md`
4. **Never reuse sequence numbers**: Even for deleted artifacts
5. **Check existing files before numbering**: Use `ls .agents/[type]/` to find next number
```

**Acceptance Criteria**:
- [ ] Naming conventions document created
- [ ] All artifact types documented
- [ ] Naming rules specified
- [ ] Agent prompts reference this document

**Effort**: 1 hour
**Dependencies**: None

---

### P3-2: Update CLAUDE.md with Naming Reference

**Issue Reference**: I5 (naming drift)
**Affected Components**: CLAUDE.md
**Root Cause**: No single source of truth reference

**Remediation Action**:
Add to CLAUDE.md Output Directories section:

```markdown
## Artifact Naming

See `.agents/governance/naming-conventions.md` for:
- Sequenced artifact patterns (EPIC-NNN, ADR-NNN, etc.)
- Type-prefixed artifact patterns (prd-*, tasks-*, etc.)
- Naming rules and examples
```

**Acceptance Criteria**:
- [ ] Reference added to CLAUDE.md
- [ ] Consistent with governance document

**Effort**: 0.5 hours
**Dependencies**: P2-4

---

## Workstream 4: Process Changes

### P2-5: Feedback Loop for Inconsistencies

**Issue Reference**: General process gap
**Affected Components**: Orchestration workflow
**Root Cause**: Inconsistencies only caught by external review

**Remediation Action**:
Document feedback loop process in `.agents/governance/consistency-protocol.md`:

```markdown
# Consistency Protocol

## Checkpoints

### After Task-Generator

Before handing to critic:
1. Compare task estimates with epic estimate
2. Verify all PRD requirements have task mappings
3. Check memory entities reflect current data

### After Implementation

Before handing to QA:
1. Verify all task acceptance criteria addressed
2. Check security-relevant code flagged
3. Confirm no absolute paths in documentation

## Inconsistency Response

When inconsistency found:
1. Document the discrepancy (what, where, magnitude)
2. Route to appropriate agent for reconciliation
3. Update memory with reconciled values
4. Continue workflow only after resolution
```

**Acceptance Criteria**:
- [ ] Consistency protocol documented
- [ ] Checkpoint locations specified
- [ ] Response procedure defined

**Effort**: 1 hour
**Dependencies**: WS1 agent updates

---

## Skills to Extract (Skillbook)

Based on this analysis, extract the following skills:

### Skill-Review-001: Escalation Prompt Completeness

**Statement**: Include all verified facts with exact values in escalation prompts, not summaries.
**Atomicity**: 92%
**Evidence**: Issue 1 - lost 99%/60-70% breakdown in favor of "80-90%"
**Tag**: helpful (when applied), harmful (when omitted)

### Skill-Doc-002: Repository-Relative Paths Only

**Statement**: Convert absolute paths to relative before committing documentation.
**Atomicity**: 95%
**Evidence**: Issue 3 - Windows paths in References section
**Tag**: harmful (when violated)

### Skill-Plan-003: Estimate Reconciliation Required

**Statement**: Derived estimates differing >10% from source require explicit reconciliation.
**Atomicity**: 88%
**Evidence**: Issues 4, 6 - 12-16 hrs vs 8-14 hrs (43% difference)
**Tag**: harmful (when omitted)

### Skill-Security-001: Post-Implementation Security Spot-Check

**Statement**: Security-relevant implementations require verification after coding, not just design review.
**Atomicity**: 90%
**Evidence**: Issue 7 - script implemented but not re-reviewed by security
**Tag**: helpful (when applied)

---

## Success Metrics

| Metric | Current | Target | Measurement |
|--------|---------|--------|-------------|
| Absolute paths in committed docs | >0 | 0 | CI check pass rate |
| Estimate reconciliation rate | 0% | 100% | Tasks with reconciliation section |
| Security post-impl reviews | 0% | 100% for flagged items | PIV documents created |
| Naming convention compliance | ~60% | 100% | CI validation |
| Orphan conditions in plans | >0 | 0 | Validation script |

---

## Risk Register

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Agent prompt changes break existing behavior | Medium | Low | Test prompts on sample tasks before merge |
| CI checks too strict, false positives | Low | Medium | Start with warnings, graduate to failures |
| Estimate reconciliation adds overhead | Low | Medium | Document when to skip (trivial tasks) |
| Naming migration breaks existing references | Medium | Low | Update references in same PR |

---

## Rollout Phases

### Phase 1: Critical Fixes (P0)

**Timeline**: Immediate (this PR)
**Items**: P0-1, P0-2, P0-3, P0-4

**Deliverables**:
- [ ] explainer.md updated with path normalization
- [ ] security.md updated with post-implementation verification
- [ ] implementer.md updated with security flagging
- [ ] Path normalization CI script and workflow

### Phase 2: Consistency Fixes (P1)

**Timeline**: Next PR
**Items**: P1-1, P1-2, P1-3, P1-4

**Deliverables**:
- [ ] critic.md updated with escalation template
- [ ] task-generator.md updated with estimate reconciliation
- [ ] planner.md updated with condition traceability
- [ ] Cross-document validation CI script

### Phase 3: Process Improvements (P2)

**Timeline**: Within 2 weeks
**Items**: P2-1, P2-2, P2-3, P2-4, P2-5

**Deliverables**:
- [ ] roadmap.md updated with naming conventions
- [ ] memory.md updated with freshness protocol
- [ ] orchestrator.md updated with consistency checkpoint
- [ ] Central naming conventions document
- [ ] Consistency protocol document

### Phase 4: Polish (P3)

**Timeline**: As capacity allows
**Items**: P3-1, P3-2

**Deliverables**:
- [ ] Handoff validation added to all agents
- [ ] CLAUDE.md updated with naming reference

---

## GitHub Issue Format

```markdown
## PR #43 Remediation: CodeRabbit Review Findings

### Summary

CodeRabbit identified 7 issues in PR #43 stemming from 5 systemic patterns. This issue tracks remediation across 4 workstreams.

### Labels

- `enhancement`
- `agents`
- `documentation`
- `ci`

### Milestone

v1.1 - Agent Quality Improvements

---

### Phase 1: Critical Fixes (P0)

- [ ] #P0-1 Update explainer.md with path normalization requirements
- [ ] #P0-2 Update security.md with post-implementation verification
- [ ] #P0-3 Update implementer.md with security flagging protocol
- [ ] #P0-4 Create path normalization CI script and workflow

### Phase 2: Consistency Fixes (P1)

- [ ] #P1-1 Update critic.md with escalation template
- [ ] #P1-2 Update task-generator.md with estimate reconciliation
- [ ] #P1-3 Update planner.md with condition traceability
- [ ] #P1-4 Create cross-document validation CI script

### Phase 3: Process Improvements (P2)

- [ ] #P2-1 Update roadmap.md with naming conventions
- [ ] #P2-2 Update memory.md with freshness protocol
- [ ] #P2-3 Update orchestrator.md with consistency checkpoint
- [ ] #P2-4 Create `.agents/governance/naming-conventions.md`
- [ ] #P2-5 Create `.agents/governance/consistency-protocol.md`

### Phase 4: Polish (P3)

- [ ] #P3-1 Add handoff validation to all agents
- [ ] #P3-2 Update CLAUDE.md with naming reference

---

### Related

- PR #43 (source of CodeRabbit findings)
- `.agents/retrospective/pr43-coderabbit-root-cause-analysis.md`
- `.agents/analysis/pr43-agent-capability-gap-analysis.md`
- `.agents/planning/pr43-remediation-plan.md`

---

### Skills to Extract

After remediation complete, extract to skillbook:
- Skill-Review-001: Escalation Prompt Completeness
- Skill-Doc-002: Repository-Relative Paths Only
- Skill-Plan-003: Estimate Reconciliation Required
- Skill-Security-001: Post-Implementation Security Spot-Check
```

---

## Appendix A: Agent Files to Modify

| File | Priority Items | Total Changes |
|------|----------------|---------------|
| `src/claude/explainer.md` | P0-1 | 1 section |
| `src/claude/security.md` | P0-2 | 1 section |
| `src/claude/implementer.md` | P0-3 | 2 sections |
| `src/claude/critic.md` | P1-1, P3-1 | 2 sections |
| `src/claude/task-generator.md` | P1-2, P3-1 | 2 sections |
| `src/claude/planner.md` | P1-3 | 1 section |
| `src/claude/roadmap.md` | P2-1 | 1 section |
| `src/claude/memory.md` | P2-2 | 1 section |
| `src/claude/orchestrator.md` | P2-3 | 1 section |
| `src/claude/qa.md` | P3-1 | 1 section |

---

## Appendix B: New Files to Create

| File | Priority | Description |
|------|----------|-------------|
| `build/Validate-PathNormalization.ps1` | P0-4 | Absolute path detection |
| `.github/workflows/validate-paths.yml` | P0-4 | Path validation workflow |
| `build/Validate-PlanningArtifacts.ps1` | P1-4 | Consistency validation |
| `.agents/governance/naming-conventions.md` | P2-4 | Central naming standard |
| `.agents/governance/consistency-protocol.md` | P2-5 | Consistency checkpoints |

---

**Plan Created By**: Orchestrator Agent
**Date**: 2025-12-15
**Source PR**: #43 (feat/templates)
