# Copilot CLI De-Prioritization Decision

**Date**: 2025-12-17
**Status**: Active
**Decision Owner**: User (confirmed by roadmap agent)

## Decision

GitHub Copilot CLI de-prioritized to P2 (Nice to Have / Maintenance Only).

## Platform Priority Hierarchy

| Priority | Platform | Investment Level |
|----------|----------|-----------------|
| P0 | Claude Code | Full investment |
| P1 | VS Code | Active development |
| P2 | Copilot CLI | Maintenance only |

## Key Limitations (Rationale)

1. User-level MCP config only (no project-level, no team sharing)
2. No Plan Mode
3. Limited context window (8k-32k vs 200k+)
4. No semantic code analysis
5. No VS Code configuration reuse
6. Known reliability issues with user-level agent loading

## RICE Score Comparison

- Claude Code: ~20+
- VS Code: ~10+
- Copilot CLI: 0.8

## Investment Decisions

- **DECLINED**: Copilot CLI sync in Sync-McpConfig.ps1
- **MAINTENANCE ONLY**: Existing agents remain, no new features
- **NO PARITY REQUIREMENT**: New features may ship to Claude Code/VS Code only

## Removal Criteria

Copilot CLI support will be evaluated for removal if:
- Maintenance burden > 10% of total development effort
- Zero user requests in 90 days
- No GitHub improvements to critical gaps in 6 months
- >90% users on Claude Code or VS Code

## Impact on v1.1 Epic

- Renamed from "2-Variant Consolidation" to "VS Code Consolidation"
- Copilot CLI excluded from active consolidation
- Scope reduced (6-10 hours from 8-14)
- RICE score improved (12.75 from 9.6)

## Reference Documents

- Analysis: `.agents/analysis/002-copilot-cli-limitations-assessment.md`
- Roadmap: `.agents/roadmap/product-roadmap.md`
