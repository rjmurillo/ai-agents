# Research: Agent Templating System

**Date**: 2025-12-15
**Type**: Ideation Research
**Status**: Complete - Recommend Proceed

## Summary

CVA analysis of 18 agents across 3 platforms (Claude Code, VS Code, Copilot CLI) found:

- 80-90% content overlap (shared)
- 11 variation points (platform-specific)

## Key Variation Points

1. YAML front matter schema (name, model, tools)
2. Tool declaration location (YAML vs body section)
3. Tool syntax format (mcp__ prefix vs path notation)
4. Handoff invocation syntax (3 different patterns)
5. Platform-specific tool sections

## Recommendation

**Proceed** with LiquidJS (Node.js) + optional Scriban (.NET)

- Evidence: Strong (CVA confirms high overlap)
- Risk: Low (build-time only, reversible)
- Effort: 20-31 hours (~3-4 days)

## Output Document

`.agents/analysis/ideation-agent-templating.md`

## Next Steps

1. Route to high-level-advisor for validation
2. Route to architect for template structure design
3. Route to planner for work breakdown
