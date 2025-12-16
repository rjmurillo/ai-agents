# Epic: 2-Variant Agent Consolidation

## Summary

- **Priority**: P1 (v1.1 release)
- **RICE Score**: 9.6
- **Effort**: 8-14 hours total

## Phases

1. **2-Variant Consolidation** (4-6 hrs): Merge VS Code and Copilot CLI agents into single source with build-time frontmatter generation
2. **Diff-Linting** (4-8 hrs): CI check for semantic drift, 90-day data collection

## Key Outcomes

- File reduction: 54 to 36 (33%)
- Zero manual sync errors
- Data-driven decision for full templating

## Dependencies

- None blocking
- Enables templating decision after 90-day data collection

## Status

**SUPERSEDED** by three-platform-templating-plan (2025-12-15)

The 2-variant approach was abandoned because:

1. Wrong source of truth (Claude manual, should be generated)
2. Data showed 88-98% divergence, plan deferred action
3. Orchestration failure: all specialists approved flawed direction

See `three-platform-templating-plan` memory for current approach.

## Created

2025-12-15
