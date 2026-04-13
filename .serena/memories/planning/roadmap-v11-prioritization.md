# Roadmap v1.1 Prioritization Decision

**Date**: 2025-12-15
**Decision**: 2-Variant Consolidation approved at P1

## Epic: 2-Variant Consolidation + Diff-Linting

### Priority Assessment

- **Priority**: P1 (Important, Should Have)
- **Wave**: Next Release (v1.1)
- **RICE Score**: 9.6
- **Estimated Effort**: 8-14 hours

### Rationale

1. VS Code and Copilot CLI agents are 99%+ identical (only frontmatter differs)
2. Merge into single source with trivial frontmatter generation
3. Result: 36 files instead of 54 (33% reduction)
4. CI diff-linting collects drift data for 90 days

### Strategic Decision

Full templating (LiquidJS, 20-31 hours) DEFERRED to v1.2+ pending:

- 90-day diff-linting data showing Claude drift from VS Code/Copilot
- Continued maintenance burden after consolidation
- Contributor feedback

### 80/20 Rule Applied

2-Variant Consolidation gets 80% of the benefit at 20% of the effort.

### Sequencing Recommendation

1. Pre-PR Security Gate (documentation, ~1 day) - addresses active process gap
2. 2-Variant Consolidation Phase 1 (4-6 hours)
3. Diff-Linting CI Phase 2 (4-8 hours)

### Roadmap Document

`.agents/roadmap/product-roadmap.md`
