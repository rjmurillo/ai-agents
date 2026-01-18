# Skill: Token Impact Documentation

## Statement

Document cumulative token savings when optimizing skills or documentation for measurable improvement tracking.

## Context

When making changes that reduce token consumption (e.g., stripping comments, moving tests, deleting redundant files, extracting references).

## Pattern

### Workflow

1. **Track individual savings per change**:
   - Before: line count or file size
   - After: line count or file size
   - Calculate: approximate tokens saved (rough heuristic: 1 line ≈ 10 tokens)
   - Document in commit message

2. **Aggregate total impact**:
   - Sum all savings across related changes
   - Create summary table in analysis artifact
   - Include breakdown by change type

3. **Document in artifacts**:
   - **Analysis artifact**: Table with change + tokens saved
   - **Session log**: Total impact in outcomes section
   - **Skill memory**: Evidence section cites total savings

4. **Before/after comparison**:
   - Include line counts where possible
   - Percentage reduction (e.g., 273 → 27 lines = 90% reduction)
   - Qualitative impact (signal-to-noise ratio improvement)

### Good Example

From Session 65 (PR #255):

**Analysis Artifact Table**:
```markdown
| Change | Tokens Saved |
|--------|-------------|
| Comment stripping | ~2,400 |
| Test separation | ~1,500 |
| Schema deletion | ~500 |
| Reference extraction | ~200 |
| **Total** | **~4,600** |
```

**Session Log**: "~4,600 tokens saved across GitHub skill by applying patterns."

**Skill Memory**: Each skill-creator skill cites individual token savings in evidence section.

### Bad Example

- "Made improvements to skill" (no metrics)
- "Reduced file size" (no quantification)
- No aggregation across multiple changes

## Evidence

**Session 65**: Documented ~4,600 tokens saved from PR #255
- Individual changes tracked: comment stripping (2,400), test separation (1,500), schema deletion (500), reference extraction (200)
- Aggregated in analysis artifact: `.agents/analysis/pr-255-learnings.md`
- Cited in session log: Session 65 outcomes section
- Referenced in 6 skill memories

## Atomicity

**Score**: 95%

**Justification**: Single concept (document token savings with metrics). Workflow is multi-step but all steps serve one goal: measurable improvement tracking.

## Category

retrospective

## Tag

helpful

## Impact

**Rating**: 8/10

**Justification**: Enables ROI validation for optimization work. Provides concrete evidence for skill effectiveness. Helps prioritize future optimizations.

## Validation Count

1 (Session 65)

## Created

2025-12-22

## Activation Vocabulary

token, savings, optimization, impact, metric, documentation, before, after, aggregation, cumulative, measurement, quantification
