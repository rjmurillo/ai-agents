# Three-Platform Templating Plan

## Summary

Redesign of agent template system to generate ALL THREE platforms from templates:

- Claude: `src/claude/*.md` (GENERATED)
- VS Code: `src/vs-code-agents/*.agent.md` (GENERATED)
- Copilot CLI: `src/copilot-cli/*.agent.md` (GENERATED)

## Key Decision

Templates (`templates/agents/*.shared.md`) are the SINGLE SOURCE OF TRUTH.

## Why Prior 2-Variant Approach Failed

1. Wrong source of truth (Claude was kept manual, should be generated)
2. Deferred decision despite 88-98% divergence data
3. All specialists approved flawed direction (orchestration failure)

## Documents Created

| Document | Location |
|----------|----------|
| Context | `.agents/analysis/three-platform-templating-context.md` |
| Independent Thinker Review | `.agents/analysis/independent-thinker-review-three-platform.md` |
| High-Level Advisor Verdict | `.agents/analysis/high-level-advisor-verdict-three-platform.md` |
| ADR | `.agents/architecture/ADR-001-three-platform-template-generation.md` |
| Design Spec | `.agents/architecture/claude-platform-config-design.md` |
| Plan | `.agents/planning/001-three-platform-templating-plan.md` |
| Task Breakdown | `.agents/planning/tasks-three-platform-templating.md` |
| Critique | `.agents/critique/001-three-platform-templating-critique.md` |

## Effort Estimate

12-17 hours total across 5 milestones, 19 tasks

## Status

Approved by Critic. Ready for implementation.

## Created

2025-12-15
