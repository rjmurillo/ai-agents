# PRD: 2-Variant Agent Consolidation - Context Summary

**Created**: 2025-12-15
**Status**: Draft - Awaiting Critic Review

## Quick Reference

- **Location**: `.agents/planning/prd-agent-consolidation.md`
- **Feature**: Consolidate VS Code + Copilot CLI agents into single shared source
- **File Reduction**: 54 to 36 files (33%)

## Key Decisions

1. **2-Variant Approach**: Claude remains separate; VS Code/Copilot share source
2. **Build Script**: PowerShell-based generation from `templates/agents/*.shared.md`
3. **Drift Detection**: Weekly CI comparing Claude vs shared variants

## User Stories

| ID | Summary |
|----|---------|
| US-1 | Maintainer edits single shared source file |
| US-2 | Build script generates platform outputs |
| US-3 | CI validates generated files match source |
| US-4 | CI detects semantic drift Claude vs shared |
| US-5 | Contributor understands generation workflow |

## Effort Estimate

- Phase 1 (Consolidation): 8-10 hours
- Phase 2 (Diff-Linting): 4-6 hours
- Total: 12-16 hours

## Next Steps

1. Route to **critic** for validation
2. Route to **task-generator** for atomic breakdown
3. Implement per roadmap sequencing (after Pre-PR Security Gate)

## Related Documents

- Ideation: `.agents/analysis/ideation-agent-templating.md`
- Critique: `.agents/critique/001-agent-templating-critique.md`
- Roadmap: `.agents/roadmap/product-roadmap.md`
