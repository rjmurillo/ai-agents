# ADR-051: Synthesis Panel Frontmatter Standard

## Status

Accepted

## Date

2026-03-07

## Context

DESIGN-REVIEW documents (architect synthesis panels) contain critical metadata embedded in prose format, preventing automated enforcement of blocking verdicts. PR #908 was created and merged despite a P1 BLOCKING architect review, demonstrating the enforcement gap.

Current state:
- DESIGN-REVIEW verdicts (`PASS`, `NEEDS_CHANGES`, `BLOCKED`) are prose-only
- No machine-readable structure for review status, priority, or blocking status
- Architect reviews are advisory; no CI gate prevents PR merge despite blocking verdict
- Inconsistent document structure across existing DESIGN-REVIEW files
- Review automation requires unreliable regex parsing of prose

This violates the project's commitment to automated quality gates (ADR-010) and creates a critical gap between architect authority and enforcement capability.

## Decision

**All DESIGN-REVIEW documents MUST include YAML frontmatter with structured metadata.**

### Frontmatter Schema

```yaml
---
status: APPROVED | NEEDS_CHANGES | BLOCKED
priority: P0 | P1 | P2
blocking: true | false
reviewer: architect
date: YYYY-MM-DD
pr-branch: branch-name          # optional
scope: Brief scope description  # optional
---
```

### Field Semantics

| Field | Type | Values | Purpose |
|-------|------|--------|---------|
| `status` | enum | `APPROVED`, `NEEDS_CHANGES`, `BLOCKED` | Review outcome |
| `priority` | enum | `P0`, `P1`, `P2` | Issue severity if not approved |
| `blocking` | boolean | `true`, `false` | Whether CI should block merge |
| `reviewer` | string | agent name | Identity of reviewing agent |
| `date` | date | `YYYY-MM-DD` | Review date (ISO 8601) |
| `pr-branch` | string | branch name | Git branch under review (optional) |
| `scope` | string | free text | Brief description of review scope (optional) |

### CI Gate Logic

**For each DESIGN-REVIEW file in PR:**

1. Parse frontmatter YAML
2. If `blocking: true` AND (`status: NEEDS_CHANGES` OR `status: BLOCKED`):
   - **Block merge** with reason: "Blocking architect review requires changes"
3. If `blocking: true` AND `status: APPROVED`:
   - **Allow merge** (review passed)
4. If `blocking: false`:
   - **Allow merge** (advisory review)

**Result:** No PR can merge to main if it modifies DESIGN-REVIEW files with active blocking reviews.

## Rationale

### Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
|-------------|------|------|----------------|
| **Status Quo** (prose only) | Simple; no syntax overhead | Cannot automate; PR #908 proves enforcement fails | Unacceptable: violates ADR-010 quality gate principle |
| **JSON sidecar files** (DESIGN-REVIEW.json) | Separates concerns | Splits context; maintenance burden; harder to read | Would create parallel document problem |
| **Markdown tables** | Easier to read in markdown | Brittle parsing; not standard; hard to validate | YAML is markdown-ecosystem standard |
| **Plain-text header** (First line: "VERDICT: BLOCKED") | Minimal syntax | No structure; easy to miss; hard to parse | Not machine-friendly |
| **Frontmatter + schema validation** (proposed) | Structured; automated; standard | Slight syntax overhead on authors | Solves PR #908; aligns with ADR-040; enables automation |

### Trade-offs

**Syntax Overhead vs Enforcement Power:**

- Frontmatter adds 7 lines per document (~5% overhead)
- Enables complete automation of blocking reviews
- Decision: Overhead is negligible compared to enforcement value

**Migration Effort vs Long-term Clarity:**

- New requirement applies to all new DESIGN-REVIEW files
- Existing documents can migrate gradually (optional)
- Decision: New files required; gradual migration acceptable

## Consequences

### Positive

- **Automated enforcement**: Blocking reviews now prevent merge via CI gate
- **Machine-readable status**: Tools can parse review outcomes reliably
- **PR #908 prevention**: No PR can merge despite blocking architect review
- **Consistent structure**: All DESIGN-REVIEW documents follow same format
- **Quality gate alignment**: Fulfills ADR-010 principle for automated gates
- **Backwards compatible**: YAML frontmatter is ignored by markdown renderers; documents remain readable
- **Reuses patterns**: YAML frontmatter already established in ADR-040 (skill files) and session protocol

### Negative

- **Syntax burden**: Authors must remember 6 required frontmatter fields
- **Migration work**: Existing DESIGN-REVIEW files lack frontmatter (optional but recommended)
- **Script maintenance**: New validation and CI gate scripts to maintain
- **Requires tooling**: PowerShell validation script and CI gate workflow needed

### Neutral

- **Document body unchanged**: Existing DESIGN-REVIEW body structure remains compatible
- **No breaking changes**: Advisory reviews (`blocking: false`) unaffected
- **Gradual adoption**: Old documents continue working; focus on new documents first

## Implementation Notes

### Phase 1: Schema & Template Definition

1. Create `.agents/architecture/DESIGN-REVIEW-template.md` with frontmatter and body sections
2. Document ADR-051 with full specification
3. Update architect agent prompt to reference template

### Phase 2: Validation Script

1. Create `scripts/Validate-DesignReview.ps1` following ADR-005 (PowerShell-only) pattern
2. Validate required fields: `status`, `priority`, `blocking`, `reviewer`, `date`
3. Validate field values against allowed enums
4. Validate date format (YYYY-MM-DD)
5. Integrate with existing `Validate-PrePR.ps1` validation pipeline
6. Create Pester tests in `tests/Validate-DesignReview.Tests.ps1`

### Phase 3: CI Gate Workflow

1. Create `.github/workflows/architect-review-gate.yml` following ADR-006 (thin workflows) pattern
2. Trigger on PR to main branch
3. Detect DESIGN-REVIEW files in diff
4. Parse frontmatter of review files
5. Block merge if `blocking: true` AND `status` is not `APPROVED`
6. Post status check to PR

### Phase 4: Architect Agent Update

1. Update `src/claude/architect.md` to require frontmatter
2. Add frontmatter example (copy-paste ready)
3. Add checklist: "Verify all required frontmatter fields are present"

### Phase 5: Migration (Optional, Non-Blocking)

1. Create migration script to add frontmatter to existing DESIGN-REVIEW files
2. Not required; can be done ad-hoc when documents are reviewed again

## Convergence with Related ADRs

- **ADR-005**: PowerShell-Only Scripting → Validation script in PowerShell
- **ADR-006**: Thin Workflows → CI workflow delegates to PowerShell module
- **ADR-010**: Quality Gates Evaluator Optimizer → Frontmatter enables automated gate
- **ADR-040**: Skill Frontmatter Standardization → Reuses YAML frontmatter pattern
- **ADR-043**: Scoped Tool Execution → CI gate applies scoped checking (only DESIGN-REVIEW files)

## Implementation Roadmap

```
1. Create schema + template + ADR-051 (Issue #944) → 2 hours
2. Create validation script + tests (Issue #945) → 6 hours
3. Create CI gate workflow (Issue #946) → 4 hours
4. Update architect agent prompt (Issue #947) → 1 hour
5. Optional: Migrate existing files (Issue #948) → 4 hours
```

**Critical Path**: Schema → Template → Validation → CI Gate → Agent Update
**Blocking dependencies**: None (all phases can proceed in parallel after schema definition)

## Related Decisions

- **ADR-010**: Quality Gates Evaluator Optimizer (establishes gate automation principles)
- **ADR-040**: Skill Frontmatter Standardization (established YAML frontmatter pattern for skills)
- **ADR-005**: PowerShell-Only Scripting (validation script language)
- **ADR-006**: Thin Workflows (CI workflow architecture)

## Related Issues

- **Issue #937**: Create DESIGN-REVIEW template (depends on this ADR)
- **Issue #934**: Pre-PR validation parsing (depends on this ADR)
- **Issue #942**: CI gate workflow (depends on this ADR)
- **Issue #947**: Architect agent prompt update (depends on this ADR)
- **PR #908**: Architect BLOCKED but PR created anyway (incident that motivated this ADR)

## References

- `.agents/architecture/ADR-040-skill-frontmatter-standardization.md` (frontmatter pattern reference)
- `.agents/retrospective/2026-01-15-pr-908-comprehensive-retrospective.md` (incident analysis)
- `.agents/SESSION-PROTOCOL.md` (YAML frontmatter precedent in session logs)
- `scripts/Validate-SkillFormat.ps1` (validation pattern reference)
- `.github/workflows/ai-session-protocol.yml` (CI workflow pattern reference)

---

*Created: 2026-03-07*
*GitHub Issue: #946*
*Complexity: Medium (schema definition + scripting + CI)*
*Priority: P1 (blocks automated enforcement of architect reviews)*
