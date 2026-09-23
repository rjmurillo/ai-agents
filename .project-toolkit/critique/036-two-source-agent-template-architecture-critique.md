# Plan Critique: ADR-036 Two-Source Agent Template Architecture

**Date**: 2026-01-01
**Critic**: critic agent
**ADR Under Review**: ADR-036-two-source-agent-template-architecture.md

## Verdict

**NEEDS REVISION**

## Summary

ADR-036 documents the existing two-source architecture (Claude agents + shared templates) implemented in PR #43 (merged 2025-12-16). The ADR accurately describes the current state but has critical gaps:

1. Does not address relationship to unresolved Issue #124 (P1, open 11+ days)
2. Does not reconcile with historical drift data (2.4-12.8% similarity documented in retrospective)
3. Missing quality gates to prevent drift recurrence
4. Unclear whether this is documenting existing infrastructure or proposing new architecture

The ADR is architecturally sound in describing the two-source pattern, but incomplete as a decision record.

## Strengths

- **Clear structure**: Decision, rationale, consequences well-organized
- **Accurate description**: Infrastructure details match actual implementation (verified)
- **Good synchronization guidance**: Synchronization procedure clearly documented with anti-pattern warnings
- **Comprehensive references**: 17 related documents linked with clear purpose statements
- **Trade-off transparency**: Acknowledges "toil" of manual sync as accepted trade-off

## Issues Found

### Critical (Must Fix)

- [ ] **Missing Issue #124 relationship** (Lines 1-207, entire ADR)
  - **Evidence**: Issue #124 (opened 2025-12-20, P1, still open) requests ADR to evaluate template strategy options
  - **Problem**: ADR-036 documents two-source pattern but does not reference overlapping Issue #124
  - **Impact**: If Issue #124 concludes with single-source approach, ADR-036 becomes obsolete
  - **Required fix**: Add "Relationship to Issue #124" section in Consequences documenting dependency

- [ ] **No drift remediation strategy** (Lines 84-102, Consequences section)
  - **Evidence**: Retrospective documented 88-98% divergence between Claude and templates (2.4-12.8% similarity)
  - **Problem**: ADR proposes no quality gates to prevent recurrence of catastrophic drift
  - **Impact**: Historical failure pattern likely to repeat without preventive measures
  - **Required fix**: Add quality gates section with drift prevention thresholds and validation requirements

- [ ] **Ambiguous status classification** (Lines 3-9, Status section)
  - **Evidence**: All infrastructure exists (verified: `templates/agents/`, `build/Generate-Agents.ps1`, `.githooks/pre-commit` lines 597-649)
  - **Problem**: Status is "Accepted" but date is 2026-01-01 (ADR creation), not 2025-12-16 (PR #43 merge when decision was implemented)
  - **Impact**: Unclear whether this documents past decision or proposes future change
  - **Required fix**: Clarify ADR type (Documentation vs. Proposal) and align date with actual implementation

### Important (Should Fix)

- [ ] **Pre-commit hook line reference needs verification** (Line 146)
  - **Evidence**: ADR states "lines 597-649" but actual agent generation logic not found in those lines (lines 597-656 show skill generation and security detection)
  - **Problem**: Reference may be incorrect, making ADR misleading
  - **Recommendation**: Search pre-commit hook for actual agent generation section and update line numbers

- [ ] **Known limitations not documented** (Lines 84-102, Consequences section)
  - **Evidence**: Research document shows 2.4-12.8% Claude/template similarity as "collective failure"
  - **Problem**: ADR does not acknowledge known weaknesses of current approach
  - **Recommendation**: Add "Known Limitations" subsection documenting historical drift and unresolved strategic questions

- [ ] **No automated detection of content desync** (Line 96)
  - **Evidence**: Consequence states "No automated detection of content desync between sources"
  - **Problem**: This is listed as negative consequence but no mitigation proposed
  - **Recommendation**: Propose drift detection enhancement or accept as permanent limitation

### Minor (Consider)

- [ ] **Serena memories not verified** (Lines 191-197)
  - **Problem**: ADR lists 6 Serena memories but does not indicate whether they were confirmed to exist
  - **Recommendation**: Add "(verified)" or "(expected)" annotations to each memory reference

- [ ] **Related ADRs missing from reference list** (Lines 167-169)
  - **Evidence**: ADR mentions ADR-029 and ADR-004 but not ADR-005 (PowerShell-only) or ADR-006 (testable modules) which govern `Generate-Agents.ps1`
  - **Recommendation**: Add ADR-005 and ADR-006 to Related Decisions section

## Questions for Architect

### Question 1: Relationship to Issue #124 (BLOCKING)

**Context**: Issue #124 (opened 2025-12-20, P1) requests ADR to evaluate three template strategy options:

- Option A: Template-First (current + enhanced)
- Option B: Claude-First (invert source of truth)
- Option C: Independent Platforms (no templates)

ADR-036 documents the current two-source pattern but does not evaluate these options or reference Issue #124.

**Question**: What is the intended relationship between ADR-036 and Issue #124?

**Options**:

1. ADR-036 supersedes Issue #124 (close #124 as resolved by ADR-036)
2. ADR-036 depends on Issue #124 (mark ADR-036 as contingent on #124 resolution)
3. ADR-036 documents current state; Issue #124 decides future state (complementary)

**Impact**: Affects whether ADR-036 requires revision to evaluate options or can proceed as-is with dependency note.

### Question 2: ADR Type and Date (BLOCKING)

**Context**: All infrastructure described in ADR-036 already exists (verified):

- `templates/agents/*.shared.md` (18 files)
- `build/Generate-Agents.ps1` (generation script)
- Platform configs: `templates/platforms/*.yaml`

PR #43 merged 2025-12-16. ADR-036 created 2026-01-01 (17 days later).

**Question**: Is ADR-036 documenting a past decision or proposing a future decision?

**Proposed classification**:

- **Documentation ADR**: Status "Accepted", Date "2025-12-16" (PR #43 merge date), records decision already made
- **Proposal ADR**: Status "Proposed", Date "2026-01-01", seeks approval for existing infrastructure

**Impact**: Affects status field and whether approval is required.

### Question 3: Drift Prevention Approach (IMPORTANT)

**Context**: Retrospective documented catastrophic drift:

| Agent | Similarity | Divergence |
|-------|-----------|------------|
| independent-thinker | 2.4% | 97.6% different |
| high-level-advisor | 3.8% | 96.2% different |
| critic | 9.7% | 90.3% different |

ADR-036 Consequences (line 96) acknowledges "No automated detection of content desync between sources" but proposes no mitigation.

**Question**: Should ADR-036 include quality gates to prevent drift recurrence?

**Proposed additions**:

1. Section-level drift detection (compare Core Identity, Core Mission, etc. independently)
2. Similarity threshold enforcement (fail if Claude vs. template <85% similar)
3. Pre-merge validation (CI fails if regeneration produces different output)

**Impact**: Affects ADR completeness and likelihood of preventing historical failure recurrence.

## Recommendations

### Recommendation 1: Add Issue #124 Dependency Section

Add to ADR-036 after "Consequences" section:

```markdown
## Relationship to Issue #124

Issue #124 (opened 2025-12-20, P1) requests a strategic decision on the dual template
system, evaluating three options: Template-First, Claude-First, and Independent Platforms.

**Relationship**: This ADR documents the CURRENT two-source architecture (implemented
in PR #43, merged 2025-12-16) but does NOT resolve the strategic question raised in
Issue #124 regarding whether this approach should continue.

**Dependency**: If Issue #124 concludes with a single-source approach (Claude-First
or Template-First), this ADR's two-source pattern will be superseded by the new
decision. This ADR should be amended or deprecated based on Issue #124 resolution.

**Status**: Issue #124 remains open as of 2026-01-01 with `needs-info` label awaiting
stakeholder decision on preferred direction.
```

### Recommendation 2: Reclassify as Documentation ADR

Change ADR-036 metadata (lines 3-9):

```markdown
## Status

Accepted (Documentation)

## Type

Documentation ADR - Records existing architecture implemented in PR #43

## Date

2025-12-16 (Implementation date)

## Documented

2026-01-01 (ADR creation date)
```

**Rationale**: All proposed infrastructure exists. ADR is recording a past decision, not proposing a future one.

### Recommendation 3: Add Drift Remediation Section

Add after "Consequences" section:

```markdown
## Quality Gates (Preventing Drift Recurrence)

**Context**: Retrospective analysis (2025-12-15) documented 2.4-12.8% similarity between
Claude agents and templates, representing 88-98% divergence. The current ADR proposes
no improvements to prevent recurrence.

**Required Improvements**:

### 1. Section-Level Drift Detection

- **Current**: `Detect-AgentDrift.ps1` compares overall file similarity
- **Required**: Compare individual sections (Core Identity, Core Mission, Key Responsibilities)
- **Threshold**: Fail if any section <60% similar (catches localized drift)

### 2. Claude Parity Validation

- **Threshold**: Generated files must maintain >85% overall similarity to Claude source
- **Frequency**: Pre-merge validation in CI
- **Action**: PR blocked if similarity below threshold

### 3. Pre-Merge Regeneration Check

- **Process**: CI regenerates all agents from templates
- **Validation**: Fail if regenerated output differs from committed files
- **Purpose**: Prevents manual edits to generated files (enforces "Do Not Edit" header)

**Implementation**: These quality gates are RECOMMENDED but not currently implemented.
Issue #124 resolution may supersede the need for these improvements.
```

### Recommendation 4: Add Known Limitations Section

Add to "Consequences" section:

```markdown
### Known Limitations

1. **Historical Drift**: As of 2025-12-15, Claude agents and templates showed 2.4-12.8%
   similarity (88-98% divergence per retrospective). Template system has not yet
   demonstrated ability to maintain Claude parity over time.

2. **Manual Claude Maintenance**: Claude agents in `src/claude/` remain manually
   maintained, introducing asymmetry in maintenance model. Changes to shared content
   must be applied twice (Claude + templates).

3. **Unresolved Strategic Direction**: Issue #124 (P1, open) questions whether
   dual-source approach should continue. This ADR may be superseded by future decision.

4. **No Automated Sync Detection**: System does not detect when shared content exists
   in templates but is missing from Claude agents (or vice versa). Synchronization
   relies on human diligence.
```

### Recommendation 5: Link Related Issues

Add after "Related Decisions" section:

```markdown
## Related Issues

- **#124** (OPEN, P1): Strategic decision on dual template system - OVERLAPPING SCOPE
- **#72** (CLOSED): Original template sync failure that motivated 2-variant consolidation
- **#265** (OPEN, P0): Pre-PR validation includes agent template validation
- **#324** (OPEN, P0): Velocity improvements include template validation in shift-left approach
```

## Approval Conditions

Before approval, ADR-036 MUST address:

1. **Issue #124 relationship** (Critical): Add dependency section or close #124 as superseded
2. **Drift remediation** (Critical): Add quality gates section or explicitly accept no improvements
3. **Status/date clarification** (Critical): Reclassify as Documentation ADR with implementation date

ADR-036 SHOULD address:

1. Known limitations from retrospective data
2. Related issues linkage
3. Pre-commit hook line reference verification

## Impact Analysis Review

**Not Applicable**: ADR-036 is an architectural decision record, not an implementation plan requiring specialist consultations.

## Blocking Concerns

| Issue | Priority | Description |
|-------|----------|-------------|
| Issue #124 dependency | CRITICAL | ADR may be superseded by unresolved P1 issue requesting template strategy decision |
| Drift recurrence risk | HIGH | No quality gates proposed despite 88-98% historical divergence documented |
| Status ambiguity | MEDIUM | Unclear whether documenting past or proposing future decision |

## Escalation Required

**NO ESCALATION REQUIRED**

**Rationale**: This is an architectural documentation issue with clear revision requirements. No conflicting specialist recommendations or unresolvable technical disagreements.

**Recommendation**: Route back to architect for revision incorporating critique feedback.

---

**Verdict**: NEEDS REVISION
**Confidence**: High (all claims sourced from repository documents and verified infrastructure)
**Next Agent**: architect (for ADR revision)
