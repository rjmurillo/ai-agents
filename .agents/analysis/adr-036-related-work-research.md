# ADR-036 Related Work Research

**Date**: 2026-01-01
**ADR Under Review**: ADR-036-two-source-agent-template-architecture.md
**Analyst**: analyst agent

## Related Issues

| # | Title | Status | Relevance |
|---|-------|--------|-----------|
| [#124](https://github.com/rjmurillo/ai-agents/issues/124) | arch: Strategic decision needed on dual template system | OPEN (P1) | **CRITICAL OVERLAP**: This open issue requests an ADR to evaluate the exact same problem ADR-036 addresses. Created 2025-12-20, remains unresolved with needs-info label. |
| [#72](https://github.com/rjmurillo/ai-agents/issues/72) | fix: Validate Generated Agents workflow failing - templates out of sync | CLOSED | Documents original template sync failure that led to 2-variant consolidation |
| [#606](https://github.com/rjmurillo/ai-agents/issues/606) | fix(ci): 'Validate Generated Files' required check blocks PRs when path filters don't match | CLOSED | CI validation issues for generated agents |
| [#159](https://github.com/rjmurillo/ai-agents/issues/159) | Define test location standards for repository | OPEN (P2) | Related to file organization standards, not directly template-related |
| [#265](https://github.com/rjmurillo/ai-agents/issues/265) | [EPIC] Pre-PR Validation System | OPEN (P0) | Includes validation for agent templates and generation |
| [#674](https://github.com/rjmurillo/ai-agents/issues/674) | feat(governance): Require ADR for SESSION-PROTOCOL.md changes | OPEN (P1) | Establishes pattern for ADR requirements on protocol changes |
| [#324](https://github.com/rjmurillo/ai-agents/issues/324) | [EPIC] 10x Velocity Improvement | OPEN (P0) | Includes agent template validation in shift-left approach |

## Related PRs

| # | Title | Branch | Status |
|---|-------|--------|--------|
| [#43](https://github.com/rjmurillo/ai-agents/pull/43) | feat: add shared template system for multi-platform agent generation | feat/templates | MERGED |
| [#715](https://github.com/rjmurillo/ai-agents/pull/715) | feat(traceability): implement Phase 2 spec layer traceability validation | feat/phase-2-traceability | OPEN (current branch) |
| [#558](https://github.com/rjmurillo/ai-agents/pull/558) | refactor(tests): consolidate redundant multi-file diff test cases | refactor/525-consolidate-copilot-tests | MERGED |

## Related ADRs

| ADR | Title | Relationship |
|-----|-------|--------------|
| ADR-005 | PowerShell-Only Scripting | Generate-Agents.ps1 must follow PowerShell standards |
| ADR-006 | Thin Workflows, Testable Modules | Build script patterns for agent generation |
| ADR-030 | Skills Pattern Superiority | Impacts how agent templates reference skills |
| ADR-033 | Routing-Level Enforcement Gates | May affect orchestrator routing with template changes |

## Related Documentation

| Document | Location | Key Findings |
|----------|----------|--------------|
| Retrospective: 2-Variant Consolidation Failure | `.agents/retrospective/2025-12-15-accountability-analysis.md` | **CRITICAL**: Documents 2.4-12.8% similarity between Claude agents and templates, calls it "catastrophic divergence" and a "collective failure" |
| Drift Analysis | `.agents/analysis/drift-analysis-claude-vs-templates.md` | Details section-by-section drift across 6 high-drift agents |
| Architecture Review | `.agents/architecture/2-variant-consolidation-review.md` | Architect approved 2-variant approach as "architecturally sound" despite drift data |
| Drift Detection Disaster | `.agents/retrospective/2025-12-15-drift-detection-disaster.md` | Post-mortem on drift detection failures |
| PRD: Dual Template Strategy Decision | Issue #124 comment (AI-generated) | Comprehensive PRD evaluating Options A/B/C for template strategy |

## Current State Evidence

### Templates Directory Structure (Confirmed)

```text
templates/
├── agents/           (18 *.shared.md files)
├── platforms/        (vscode.yaml, copilot-cli.yaml)
├── AGENTS.md
└── README.md
```

### Build Infrastructure (Confirmed)

- `build/Generate-Agents.ps1` - Generation script (exists)
- `build/scripts/Detect-AgentDrift.ps1` - Drift detection (16KB file, exists)
- `.github/workflows/validate-agents.yml` - CI validation workflow

### Claude Agents (Source of Truth)

- Location: `src/claude/*.md` (18 agents)
- Status: Manually maintained, independent evolution
- Drift: 2.4-12.8% similarity to templates per retrospective

## Key Timeline

| Date | Event |
|------|-------|
| 2025-12-15 | PR #43 merged: 2-variant consolidation (VS Code + Copilot CLI) |
| 2025-12-15 | Drift analysis published: 2.4-12.8% Claude/template similarity |
| 2025-12-15 | Retrospective published: "collective failure" assessment |
| 2025-12-20 | Issue #124 opened: Strategic decision needed on dual template system |
| 2025-12-31 | Clarification requested on Issue #124 (11+ days without resolution) |
| 2026-01-01 | ADR-036 created (this research conducted) |

## Implications for ADR-036 Review

### 1. Duplicate Effort Risk

**Finding**: Issue #124 explicitly requests an ADR to evaluate template strategy options.

**Evidence**: Issue body states:
> "An ADR documenting:
> 1. Evaluation of each option
> 2. Recommendation with rationale
> 3. Migration plan if changing approach"

**ADR-036 Status**: ADR-036 addresses template architecture but does NOT evaluate the three options requested in #124 (Template-First, Claude-First, Independent Platforms).

**Verdict**: ADR-036 and Issue #124 have PARTIAL OVERLAP but different scopes:
- ADR-036: Documents two-source architecture pattern (templates + Claude manual)
- Issue #124: Requests decision on whether to consolidate to single source

### 2. Unresolved Strategic Decision

**Finding**: Issue #124 remains open with needs-info label for 11+ days.

**Evidence**:
- Last comment (2025-12-31): "Clarification Needed" from rjmurillo-bot
- AI-generated PRD proposes three options but awaits stakeholder decision
- Priority: P1, Milestone: v1.1

**Impact on ADR-036**:
- If Issue #124 concludes with "Claude-First" or "Template-First" option, ADR-036's two-source pattern becomes obsolete
- If Issue #124 concludes with "Independent Platforms," ADR-036 becomes UNNECESSARY (no template system)
- ADR-036 assumes continuation of current dual approach without addressing strategic questions

**Recommendation**: ADR-036 should REFERENCE Issue #124 and either:
1. Explicitly state it assumes dual approach continues (dependencies section)
2. Defer until Issue #124 resolves
3. Expand scope to answer Issue #124's strategic questions

### 3. Existing Drift Data Contradicts Template Effectiveness

**Finding**: Retrospective documents 88-98% divergence between Claude and templates.

**Evidence**: `.agents/retrospective/2025-12-15-accountability-analysis.md` states:
> "2.4% similarity means 97.6% DIFFERENT. This is not 'drift' - this is COMPLETE DIVERGENCE."

**Impact on ADR-036**:
- ADR-036 proposes template system as source of truth
- Existing data shows templates have failed to maintain Claude parity
- No evidence templates have improved since retrospective (11 Dec → 1 Jan = 17 days)

**Recommendation**: ADR-036 must address why template approach will succeed when historical data shows failure.

### 4. PR #43 CodeRabbit Findings Ignored

**Finding**: External tool (CodeRabbit) identified 7 issues across planning artifacts that agent system missed.

**Evidence**: Retrospective states:
> "CodeRabbit identified 7 issues across planning, critique, and implementation artifacts. Analysis reveals 3 systemic root causes affecting multiple agents."

**Impact on ADR-036**:
- If agent system failed to catch planning issues, can it maintain template quality?
- ADR-036 does NOT propose validation improvements beyond existing CI

**Recommendation**: ADR-036 should include quality gates for template changes.

### 5. Current Infrastructure Already Exists

**Finding**: All infrastructure ADR-036 proposes ALREADY EXISTS.

**Evidence**:
- `templates/agents/*.shared.md` - 18 files
- `build/Generate-Agents.ps1` - generation script
- `build/scripts/Detect-AgentDrift.ps1` - drift detection
- Platform configs: `templates/platforms/*.yaml`

**Impact on ADR-036**:
- ADR-036 is documenting EXISTING architecture, not proposing NEW architecture
- This should be classified as "Documentation ADR" not "Decision ADR"
- Status should be "Accepted" (documenting fait accompli) not "Proposed"

**Recommendation**: Reclassify ADR-036 or expand scope to propose improvements.

## Gaps Identified

### Gap 1: No Three-Option Evaluation

Issue #124 requests evaluation of:
- Option A: Template-First (current + enhanced)
- Option B: Claude-First (invert source of truth)
- Option C: Independent Platforms (no templates)

ADR-036 does NOT evaluate these options.

### Gap 2: No Migration Plan

Issue #124 acceptance criteria include "Migration plan if changing approach."

ADR-036 does NOT include migration plan from current state to proposed state (because proposed = current).

### Gap 3: No Drift Remediation Strategy

Retrospective documented catastrophic drift. ADR-036 does NOT propose how to prevent recurrence.

### Gap 4: No Stakeholder Decision Record

Issue #124 awaits stakeholder input on preferred direction. ADR-036 does NOT document stakeholder decision.

## Issues to Link

| Issue | Reason |
|-------|--------|
| #124 | MUST LINK: Duplicate/overlapping scope |
| #72 | Should link: Original template sync failure |
| #265 | Should link: Pre-PR validation includes agent templates |
| #324 | Should link: Velocity improvements include template validation |

## PRs Already Implementing This

**Finding**: No PRs currently implementing ADR-036 changes because infrastructure already exists.

**Status**: PR #43 (merged 2025-12-15) implemented the 2-variant template system ADR-036 documents.

## Blocking Questions for ADR-036

### Question 1: What is ADR-036's relationship to Issue #124?

**Context**: Both address template architecture strategy.

**Options**:
1. ADR-036 supersedes Issue #124 (close #124 as resolved)
2. ADR-036 defers to Issue #124 (mark ADR-036 as dependent)
3. ADR-036 documents current state; Issue #124 decides future state (complementary)

**Recommended Answer**: Option 3 (complementary), but ADR-036 must reference Issue #124 in Consequences section.

### Question 2: Is ADR-036 documenting or proposing?

**Context**: Infrastructure already exists.

**Options**:
1. Documentation ADR (Status: Accepted, records past decision)
2. Proposal ADR (Status: Proposed, requires approval)

**Evidence**: All proposed components exist in codebase.

**Recommended Answer**: Documentation ADR with Status: Accepted, Date: 2025-12-15 (PR #43 merge date).

### Question 3: How does ADR-036 address historical drift failure?

**Context**: Retrospective documented 88-98% divergence.

**Missing**: ADR-036 proposes no improvements to prevent recurrence.

**Recommended Addition**: Add "Quality Gates" section with:
- Mandatory drift detection before merge
- Section-level diff validation
- Claude parity verification

## Recommendations for Architect

### Recommendation 1: Reference Issue #124

Add to ADR-036 Consequences section:

```markdown
## Relationship to Issue #124

Issue #124 requests a strategic decision on the dual template system. This ADR
documents the CURRENT architecture (two-source pattern) but does NOT resolve
the strategic question of whether to consolidate sources.

**Dependency**: If Issue #124 concludes with single-source approach (Claude-First
or Template-First), this ADR's two-source pattern will be superseded.
```

### Recommendation 2: Reclassify as Documentation ADR

Change ADR-036 metadata:

```yaml
Status: Accepted
Date: 2025-12-15 (PR #43 implementation date)
Type: Documentation (records existing architecture)
```

### Recommendation 3: Add Drift Remediation Section

Propose improvements to prevent recurrence of 2.4-12.8% drift:

```markdown
## Quality Gates (Preventing Drift Recurrence)

1. **Section-Level Validation**: Drift detection compares individual sections
   (Core Identity, Core Mission, etc.) not just overall similarity
2. **Claude Parity Threshold**: Generated files must maintain >85% similarity
   to Claude source (current: 2.4-12.8%)
3. **Pre-Merge Verification**: CI fails if regeneration produces different output
```

### Recommendation 4: Link Related Issues

Add to ADR-036:

```markdown
## Related Issues

- #124: Strategic decision on dual template system (OVERLAPPING SCOPE)
- #72: Original template sync failure
- #265: Pre-PR validation includes agent templates
- #324: Velocity improvements include template validation
```

### Recommendation 5: Document Known Limitations

Add to ADR-036 Consequences section:

```markdown
## Known Limitations

1. **Historical Drift**: As of 2025-12-15, Claude agents and templates showed
   2.4-12.8% similarity (88-98% divergence). Template system has not yet
   demonstrated ability to maintain Claude parity.
2. **Manual Claude Maintenance**: Claude agents remain manually maintained,
   introducing asymmetry in maintenance model.
3. **Unresolved Strategic Direction**: Issue #124 questions whether dual-source
   approach should continue.
```

## Data Transparency

### Found

- Issue #124 with comprehensive AI-generated PRD
- Retrospective documenting drift failure (2.4-12.8% similarity)
- Drift analysis with section-by-section comparison
- Architecture review approving 2-variant approach
- Existing infrastructure (templates, scripts, CI)
- PR #43 merge implementing current system

### Not Found

- Evidence templates have improved Claude parity since 2025-12-15
- Stakeholder decision on Issue #124 options
- Validation that drift detection has prevented new drift
- Migration plan from dual-source to single-source (if desired)
- Quality gate improvements since retrospective

## Conclusion

ADR-036 documents existing architecture implemented in PR #43 (merged 2025-12-15). Issue #124 (opened 2025-12-20, still open P1) requests strategic decision on whether this architecture should continue. The two efforts have overlapping scope but different purposes:

- **ADR-036**: Documents two-source pattern (as-is architecture)
- **Issue #124**: Questions whether two-source pattern should continue (strategic decision)

**Verdict**: ADR-036 and Issue #124 are COMPLEMENTARY but DEPENDENT. ADR-036 should:
1. Reference Issue #124 as unresolved strategic dependency
2. Reclassify as Documentation ADR (Status: Accepted, recording PR #43)
3. Add drift remediation quality gates
4. Document known limitations from retrospective data

**User Impact**: If Issue #124 concludes with single-source approach, users will experience simpler maintenance model. If dual-source continues, users face ongoing drift risk documented in retrospective.

**Handoff**: Route to architect for ADR-036 revision incorporating these findings.

---

**Analysis Complete**: 2026-01-01
**Analyst**: analyst agent
**Confidence**: High (all claims sourced from repository documents and GitHub API)
