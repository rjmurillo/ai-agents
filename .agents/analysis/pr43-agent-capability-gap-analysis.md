# PR #43 Agent Capability Gap Analysis

**Date**: 2025-12-15
**Source**: PR #43 CodeRabbit Review Retrospective
**Purpose**: Identify specific gaps in agent prompts that caused the 7 issues
**Output**: Actionable recommendations for agent prompt modifications

---

## Executive Summary

Analysis of the 9 agent files in `src/claude/` against the PR #43 retrospective findings reveals **15 specific capability gaps** across 9 agents. The gaps fall into 5 categories:

1. **Missing Output Validation** (4 gaps) - No enforcement of data completeness in outputs
2. **Missing Cross-Document Validation** (3 gaps) - No requirement to verify consistency with source documents
3. **Missing Path Normalization** (2 gaps) - No guidance on converting absolute to relative paths
4. **Missing Naming Conventions** (2 gaps) - No documented/enforced artifact naming patterns
5. **Missing Post-Implementation Checkpoints** (4 gaps) - No re-verification after implementation phase

---

## Agent-by-Agent Gap Analysis

### 1. Critic Agent (`critic.md`)

**Root Cause**: Escalation Prompt Missing Data (Issue 1)

#### Current Capability

The critic agent has:
- Review Checklist (lines 24-52) with completeness, feasibility, alignment, testability checks
- Impact Analysis Validation section (lines 53-62)
- Disagreement Detection & Escalation section (lines 63-93)
- Escalation Protocol (lines 77-85) with instructions to document conflicts and escalate

#### Missing Capability

The escalation protocol does NOT require:
- Including all verified facts with exact numeric values
- Preserving specific data points from analysis tables
- Structured prompt template with mandatory fields

#### Specific Text to Add

**Location**: After line 85 (Escalation Protocol section), add:

```markdown
### Escalation Prompt Completeness Requirements

When escalating to high-level-advisor, the prompt MUST include:

```markdown
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
| [Agent A] | [Position] | [Why] |
| [Agent B] | [Position] | [Why] |

### Decision Questions
1. [Specific question requiring resolution]
```

**Anti-Pattern**: Converting "99%+ overlap (VS Code/Copilot), 60-70% (Claude)" to "80-90% overlap" loses actionable detail.
```

#### Gap Category
- **Type**: Missing Output Validation
- **Severity**: Major
- **Prevention**: Structured escalation template with mandatory fields

---

### 2. Planner Agent (`planner.md`)

**Root Cause**: QA Conditions Not Tracked (Issue 2)

#### Current Capability

The planner agent has:
- Multi-Agent Impact Analysis Framework (lines 112-304)
- Aggregated Impact Summary template (lines 228-283)
- Issues Discovered section in template (lines 271-276)

#### Missing Capability

1. No requirement to merge specialist conditions INTO the Work Breakdown table
2. No cross-reference validation between conditions and task assignments
3. No traceability protocol for multi-source synthesis

#### Specific Text to Add

**Location**: After line 283 (after Planning Checkpoints), add:

```markdown
### Condition-to-Task Traceability

When aggregating specialist reviews, ENSURE:

1. **All conditions attached to tasks**: Each condition from specialist reviews must be linked to specific task IDs in the Work Breakdown section
2. **Conditions visible in task definitions**: Update the Work Breakdown table to include condition flags

**Work Breakdown Template with Conditions**:

| Task ID | Description | Effort | Conditions |
|---------|-------------|--------|------------|
| TASK-001 | [Task name] | [Est.] | None |
| TASK-006 | [Task name] | [Est.] | QA: Requires test spec file path |
| TASK-012 | [Task name] | [Est.] | QA: Effort revised to 1.5hrs |

**Validation Checklist**:
- [ ] Every specialist condition has a task assignment
- [ ] Work Breakdown table reflects all conditions
- [ ] No orphan conditions (conditions without task links)

**Anti-Pattern**: Putting conditions in a separate section without cross-references to tasks.
```

#### Gap Category
- **Type**: Missing Cross-Document Validation
- **Severity**: Major
- **Prevention**: Condition-to-task traceability checklist

---

### 3. Orchestrator Agent (`orchestrator.md`)

**Root Cause**: QA Conditions Not Tracked (Issue 2 - coordination gap)

#### Current Capability

The orchestrator agent has:
- Handoff Protocol (lines 678-696)
- Impact Analysis Orchestration (lines 277-358)
- Disagree and Commit Protocol (lines 312-358)

#### Missing Capability

1. No validation that planner merged all specialist conditions
2. No checkpoint to verify traceability before handing off to critic

#### Specific Text to Add

**Location**: After line 303 (after orchestration flow), add:

```markdown
**Pre-Critic Validation Checkpoint**:

Before routing planner output to critic, verify:
- [ ] All specialist consultations returned findings
- [ ] Each specialist condition has a task assignment in Work Breakdown
- [ ] Effort estimates reconciled (see Estimate Reconciliation below)
- [ ] No orphan conditions in aggregated summary

If validation fails, return to planner for completion before critic review.
```

#### Gap Category
- **Type**: Missing Cross-Document Validation
- **Severity**: Medium
- **Prevention**: Pre-critic validation checkpoint

---

### 4. Explainer Agent (`explainer.md`)

**Root Cause**: Absolute Windows Paths (Issue 3)

#### Current Capability

The explainer agent has:
- Output Options (lines 103-107) specifying file location and GitHub issues
- Process (lines 26-32) for generating PRDs
- Handoff (lines 109-113)

#### Missing Capability

1. No path normalization guidance
2. No constraint against absolute paths in documentation
3. No post-generation validation for environment-specific content

#### Specific Text to Add

**Location**: After line 100 (before Target Audience), add:

```markdown
## Path Normalization Requirements

**Constraint**: All file paths in documentation MUST be repository-relative.

**What to Do**:
1. When referencing files, convert absolute paths to relative:
   - **Wrong**: `D:\src\GitHub\user\repo\.agents\analysis\file.md`
   - **Right**: `.agents/analysis/file.md`

2. Use forward slashes for cross-platform compatibility:
   - **Wrong**: `.agents\analysis\file.md`
   - **Right**: `.agents/analysis/file.md`

3. Before finalizing any document with file references, verify no absolute paths remain.

**Validation Regex**: `[A-Z]:\\|\/Users\/|\/home\/` (should return 0 matches)

**Why**: Absolute paths expose environment details and break portability.
```

#### Gap Category
- **Type**: Missing Path Normalization
- **Severity**: Critical
- **Prevention**: Path normalization constraint and validation regex

---

### 5. Task-Generator Agent (`task-generator.md`)

**Root Cause**: Effort Estimate Discrepancy (Issue 4)

#### Current Capability

The task-generator agent has:
- Complexity Guidelines (lines 56-64)
- Output Format with Summary table (lines 68-101)
- Scope vs Planner section (lines 124-132)

#### Missing Capability

1. No requirement to compare derived estimates with epic/PRD source estimates
2. No protocol for reconciling discrepancies
3. No back-propagation trigger when estimates diverge

#### Specific Text to Add

**Location**: After line 101 (after Output Format), add:

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
   - **Update source**: If task analysis reveals more accurate estimate, note in output and recommend epic update
   - **Document rationale**: If difference is justified (e.g., scope refinement), explain in output
   - **Flag for review**: If uncertain, flag for critic/planner review

### Output Template Addition

Add to Summary section:

```markdown
## Estimate Reconciliation

**Source Document**: [Epic/PRD filename]
**Source Estimate**: [X-Y hours]
**Derived Estimate**: [A-B hours]
**Difference**: [±N%]
**Status**: [Aligned | Reconciled | Flagged for review]
**Rationale** (if divergent): [Why estimates differ]
```

**Anti-Pattern**: Producing derived estimates without comparing to source.
```

#### Gap Category
- **Type**: Missing Cross-Document Validation
- **Severity**: Major
- **Prevention**: Estimate reconciliation protocol with mandatory comparison

---

### 6. Roadmap Agent (`roadmap.md`)

**Root Cause**: Naming Convention Violation (Issue 5)

#### Current Capability

The roadmap agent has:
- Roadmap Document Format (lines 142-196)
- Epic Definition Format (lines 198-237)
- Output location specified as `.agents/roadmap/product-roadmap.md`

#### Missing Capability

1. No naming convention for epic files
2. No prefix pattern (PREFIX-NNN) specified
3. No consistency guidance across artifact types

#### Specific Text to Add

**Location**: After line 196 (after Roadmap Document Format), add:

```markdown
## Artifact Naming Conventions

### Epic Files

**Pattern**: `EPIC-NNN-[kebab-case-name].md`

**Examples**:
- `EPIC-001-user-authentication.md`
- `EPIC-002-api-versioning.md`
- `EPIC-003-agent-consolidation.md`

### Numbering

- Start at 001 for new projects
- Increment sequentially
- Never reuse numbers (even for deleted epics)
- Check existing files before assigning: `ls .agents/roadmap/EPIC-*.md`

### Cross-Reference Convention

When referencing epics in other documents:
- **Full reference**: `EPIC-001: User Authentication`
- **Short reference**: `EPIC-001`

### Why PREFIX-NNN

1. **Sortable**: Files sort chronologically by default
2. **Traceable**: Easy to find all references to an epic
3. **Consistent**: Matches critique (`001-*`) and other artifacts

**Anti-Pattern**: Using `epic-[name].md` without numeric prefix.
```

#### Gap Category
- **Type**: Missing Naming Conventions
- **Severity**: Major
- **Prevention**: Explicit naming pattern with examples

---

### 7. Memory Agent (`memory.md`)

**Root Cause**: Memory Estimate Inconsistency (Issue 6)

#### Current Capability

The memory agent has:
- Storage Protocol (lines 128-144)
- Conflict Resolution (lines 165-171)
- Entity Naming Conventions (lines 87-98)

#### Missing Capability

1. No guidance on when to refresh stored estimates
2. No protocol for updating snapshots when derived documents change
3. No validation against source documents before storage

#### Specific Text to Add

**Location**: After line 171 (after Conflict Resolution), add:

```markdown
## Estimate Freshness Protocol

### Problem

Memory snapshots capture point-in-time data. When downstream agents (task-generator, planner) refine estimates, stored values become stale.

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

### Relation for Superseded Data

When estimates are refined:
```json
{
  "relations": [{
    "from": "Feature-[Name]",
    "to": "Task-Breakdown-[Name]",
    "relationType": "estimate_refined_by"
  }]
}
```

**Anti-Pattern**: Storing epic estimate after task breakdown exists.
```

#### Gap Category
- **Type**: Missing Cross-Document Validation
- **Severity**: Major
- **Prevention**: Estimate freshness protocol with update triggers

---

### 8. Security Agent (`security.md`)

**Root Cause**: Security Analysis Incomplete (Issue 7)

#### Current Capability

The security agent has:
- Capability 6: Impact Analysis (lines 68-185) for planning phase
- Security Checklist (lines 202-224) for code review
- Handoff Options (lines 287-294)

#### Missing Capability

1. No post-implementation verification step
2. No guidance on when to re-review after implementer completes
3. No security-relevant change detection triggers

#### Specific Text to Add

**Location**: After line 294 (after Handoff Options), add:

```markdown
## Post-Implementation Security Verification

### Problem

Security review at design phase does not verify implementation correctness.

### Security-Relevant Change Triggers

Request post-implementation verification when implementer creates:
- [ ] New scripts with file system access
- [ ] CI/CD workflow changes
- [ ] Path manipulation logic
- [ ] Environment variable handling
- [ ] External command execution (Invoke-Expression, Start-Process)
- [ ] User input processing

### Verification Checklist (Post-Implementation)

```markdown
- [ ] Implemented controls match design-phase recommendations
- [ ] No hardcoded credentials or secrets
- [ ] Path validation implemented (Test-PathWithinRoot or equivalent)
- [ ] Error messages do not leak sensitive information
- [ ] Input validation present for all external inputs
- [ ] Audit logging for security-relevant operations
```

### Handoff Protocol Update

After implementer completes security-relevant code:
1. **QA agent** flags files matching security triggers
2. **Security agent** performs spot-check verification
3. **Only then** proceed to merge

### Output

Save post-implementation findings to: `.agents/security/PIV-NNN-[feature].md`

```markdown
# Post-Implementation Verification: [Feature]

**Design Review**: SR-NNN-[feature].md
**Implementation**: [PR/branch]
**Verdict**: [Verified | Issues Found]

## Controls Verified
| Control | Design Spec | Implementation | Status |
|---------|-------------|----------------|--------|
| [Control] | [What was specified] | [What was implemented] | [OK/Gap] |

## Issues Found
[List any gaps between design and implementation]
```

**Anti-Pattern**: Approving design without verifying implementation.
```

#### Gap Category
- **Type**: Missing Post-Implementation Checkpoint
- **Severity**: Critical
- **Prevention**: Post-implementation verification step with triggers

---

### 9. Implementer Agent (`implementer.md`)

**Root Cause**: Security Analysis Incomplete (Issue 7 - implementation side)

#### Current Capability

The implementer agent has:
- Impact Analysis Mode (lines 38-131) for planning phase
- Handoff Options (lines 325-333)
- Handoff Protocol (lines 335-341)

#### Missing Capability

1. No trigger to request security re-review after implementing security-relevant changes
2. No self-identification of security-relevant code

#### Specific Text to Add

**Location**: After line 333 (in Handoff Options table), add row:

```markdown
| **security** | Security-relevant code implemented | Post-implementation verification |
```

**Location**: After line 341 (after Handoff Protocol), add:

```markdown
## Security-Relevant Code Flagging

### Self-Assessment Triggers

After implementation, assess if code is security-relevant:

| Pattern | Security Relevance |
|---------|-------------------|
| File system operations (`Get-Item`, `Set-Content`, `Remove-Item`) | High |
| Path manipulation (string concatenation with paths) | High |
| Environment variables (`$env:`, `GetEnvironmentVariable`) | Medium |
| External command execution (`Invoke-Expression`, `Start-Process`) | Critical |
| User input handling (parameters, config files) | High |
| Network operations (HTTP, WebSocket) | High |
| Credential handling | Critical |

### Protocol

If any trigger applies:
1. Add to commit message: `[security-relevant]`
2. Note in handoff: "Security-relevant changes - recommend security verification"
3. Include in TODO: `- [ ] Request security post-implementation review`

### Handoff Update

When implementation is complete AND security-relevant:

1. Ensure all commits are made with conventional messages
2. Store implementation notes in memory
3. Announce: "Implementation complete. **Security-relevant changes detected.** Handing off to qa for verification, then security for post-implementation review"

**Anti-Pattern**: Implementing security-relevant code without flagging for re-review.
```

#### Gap Category
- **Type**: Missing Post-Implementation Checkpoint
- **Severity**: Critical
- **Prevention**: Security-relevant code flagging protocol

---

## Cross-Agent Workflow Gaps

### Gap 1: No Handoff Validation

**Current State**: Agents hand off to next agent without validating output completeness.

**Problem**: Information can be lost between agents because receiving agent trusts sender.

**Recommendation**: Add receiving-agent validation checklist.

**Affected Agents**: All agents with handoffs

**Proposed Addition** (to each agent's handoff section):

```markdown
### Receiving Agent Validation

When receiving handoff, verify:
- [ ] Required sections present
- [ ] Data completeness (no "[TBD]" or "[TODO]" placeholders)
- [ ] Cross-references valid (referenced files exist)
- [ ] Estimates provided where expected
- [ ] If validation fails, return to sender with specific gaps
```

---

### Gap 2: No Feedback Loop for Inconsistencies

**Current State**: Downstream agents (task-generator, memory) can produce data inconsistent with upstream sources (epic, PRD) without correction mechanism.

**Problem**: Inconsistencies propagate and are only caught by external review (CodeRabbit).

**Recommendation**: Implement consistency checkpoint in orchestrator.

**Proposed Addition** (to orchestrator.md, after agent delegation):

```markdown
### Consistency Checkpoint

After task-generator completes, before handing to critic:
- [ ] Compare task estimates with epic estimate
- [ ] Verify all PRD requirements have task mappings
- [ ] Check memory entities reflect current (not stale) data

If inconsistencies found:
1. Document discrepancy
2. Route to appropriate agent for reconciliation
3. Update memory with reconciled values
```

---

### Gap 3: Naming Conventions Not Documented Centrally

**Current State**: Different agents use different naming patterns:
- Critiques: `001-*-critique.md` (numbered)
- PRDs: `prd-*.md` (prefix)
- Tasks: `tasks-*.md` (prefix)
- Epics: `epic-*.md` (prefix, no number)

**Problem**: Inconsistent conventions make artifacts harder to find and reference.

**Recommendation**: Create `.agents/governance/naming-conventions.md` and reference from each agent.

**Proposed Document**:

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

## Type-Prefixed Artifacts (no number)

| Type | Pattern | Example | Location |
|------|---------|---------|----------|
| PRD | `prd-[name].md` | `prd-auth.md` | `.agents/planning/` |
| Tasks | `tasks-[name].md` | `tasks-auth.md` | `.agents/planning/` |
| Plan | `plan-[name].md` | `plan-auth.md` | `.agents/planning/` |
| Impact Analysis | `impact-analysis-[name]-[domain].md` | `impact-analysis-auth-security.md` | `.agents/planning/` |

## Naming Rules

1. Use kebab-case for names: `user-authentication` not `user_authentication`
2. Keep names concise: 2-4 words maximum
3. Use consistent names across related artifacts:
   - `EPIC-001-auth.md`, `prd-auth.md`, `tasks-auth.md`
```

---

## Summary Table

| Agent | Issue | Gap Type | Severity | Fix Effort |
|-------|-------|----------|----------|------------|
| critic | 1 | Missing Output Validation | Major | 1 hour |
| planner | 2 | Missing Cross-Document Validation | Major | 1.5 hours |
| orchestrator | 2 | Missing Cross-Document Validation | Medium | 0.5 hours |
| explainer | 3 | Missing Path Normalization | Critical | 0.5 hours |
| task-generator | 4 | Missing Cross-Document Validation | Major | 1 hour |
| roadmap | 5 | Missing Naming Conventions | Major | 0.5 hours |
| memory | 6 | Missing Cross-Document Validation | Major | 1 hour |
| security | 7 | Missing Post-Implementation Checkpoint | Critical | 1.5 hours |
| implementer | 7 | Missing Post-Implementation Checkpoint | Critical | 1 hour |

**Total Estimated Fix Effort**: 8.5 hours

---

## Implementation Priority

### P0 - Critical (implement immediately)

1. **Explainer path normalization** - Prevents environment leaks in docs
2. **Security post-implementation verification** - Closes security gap
3. **Implementer security flagging** - Enables security re-review

### P1 - High (implement before next feature)

4. **Critic escalation template** - Prevents information loss
5. **Task-generator estimate reconciliation** - Prevents inconsistencies
6. **Planner condition-to-task traceability** - Ensures specialist inputs tracked

### P2 - Medium (implement within 2 weeks)

7. **Roadmap naming conventions** - Improves consistency
8. **Memory estimate freshness** - Prevents stale data
9. **Orchestrator consistency checkpoint** - Catches issues earlier

### P3 - Low (document for future)

10. **Cross-agent naming convention document** - Governance improvement
11. **Handoff validation checklist** - Process improvement

---

## Next Steps

1. Create PRs for P0 fixes (security, explainer)
2. Update agent prompts in `src/claude/` per recommendations
3. Create `.agents/governance/naming-conventions.md`
4. Add CI validation for absolute paths in markdown
5. Consider tooling for cross-document consistency checking

---

**Analysis By**: Analyst Agent
**Date**: 2025-12-15
**Source**: PR #43 CodeRabbit Review + `pr43-coderabbit-root-cause-analysis.md`
