# Copilot Platform Priority Decision

**Date**: 2025-12-17 | **Status**: Active

## Platform Hierarchy

| Priority | Platform | Investment Level |
|----------|----------|------------------|
| P0 | Claude Code | Full investment |
| P1 | VS Code | Active development |
| P2 | Copilot CLI | Maintenance only |

## Key Limitations (Copilot CLI)

- User-level MCP config only (no project-level, no team sharing)
- No Plan Mode
- Limited context window (8k-32k vs 200k+)
- No semantic code analysis
- Known reliability issues with user-level agent loading

## RICE Score Comparison

- Claude Code: ~20+
- VS Code: ~10+
- Copilot CLI: 0.8

## Investment Decisions

- DECLINED: Copilot CLI sync in Sync-McpConfig.ps1
- MAINTENANCE ONLY: Existing agents remain, no new features
- NO PARITY REQUIREMENT: New features may ship to Claude Code/VS Code only

## Removal Criteria

Evaluate for removal if any apply:

- Maintenance burden >10% of total development effort
- Zero user requests in 90 days
- No GitHub improvements to critical gaps in 6 months
- >90% users on Claude Code or VS Code

## Index

Parent: `skills-copilot-index`
