# Copilot Skills Index

**Type**: Domain Index (Level 1)
**Skills**: 3
**Updated**: 2025-12-23

## Purpose

Activation vocabulary for Copilot-related skills. Scan keywords to identify relevant skill, then read atomic file.

## Skills

| Skill | Activation Words (~12) | File | Tokens |
|-------|------------------------|------|--------|
| Platform Priority | P0, P1, P2, RICE, maintenance-only, Claude-Code, VSCode, Copilot-CLI, investment, deprioritization, removal-criteria, context-window | copilot-platform-priority | ~180 |
| Follow-Up PR | duplicate, sub-pr, close, branch, follow-up, gh-pr-close, review-count, copilot/sub-pr-{number}, target-branch, notification, already-fixed | copilot-follow-up-pr | ~120 |
| PR Review | false-positive, consistency-check, triage, actionability, response-template, contradictory, PowerShell-escape, cursor-bot-duplicate, declining-signal, sequence-check | copilot-pr-review | ~350 |

## When to Use Each

| If you need... | Read |
|----------------|------|
| Platform investment decisions, RICE scores | `copilot-platform-priority` |
| Handling duplicate follow-up PRs | `copilot-follow-up-pr` |
| Triaging review comments, response templates | `copilot-pr-review` |

## Related Indices

- `memory-index` (top-level routing)
- `skills-coderabbit-index` (similar bot patterns)
