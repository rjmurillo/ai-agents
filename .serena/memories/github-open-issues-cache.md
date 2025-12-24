# GitHub Open Issues Cache

**Last Updated**: 2025-12-23T21:00:00Z
**TTL**: 1 hour
**Next Refresh**: After 2025-12-24T00:00:00Z (or on issue state change)

## Cache-Aside Pattern

Before querying GitHub API for open issues:
1. Read this memory
2. Check if `now < Next Refresh`
3. If FRESH: use cached data
4. If STALE: query API, update this file

## Priority Issues

### P0 (Critical)
| Issue | Title | Labels |
|-------|-------|--------|
| #307 | Memory Automation: Index, Consolidation, and Smart Retrieval | agent-memory, agent-qa, P0 |

### P1 (Important)
| Issue | Title | Labels |
|-------|-------|--------|
| #318 | [ALERT] PR Maintenance Workflow Failed | bug, automation, P1 |
| #317 | [ALERT] PR Maintenance Workflow Failed | bug, automation, P1 |
| #316 | [ALERT] PR Maintenance Workflow Failed | bug, automation, P1 |
| #314 | [ALERT] PR Maintenance Workflow Failed | bug, automation, P1 |
| #312 | [ALERT] PR Maintenance Workflow Failed | bug, automation, P1 |
| #309 | [ALERT] PR Maintenance Workflow Failed | bug, automation, P1 |
| #306 | [ALERT] PR Maintenance Workflow Failed | bug, automation, P1 |
| #305 | [ALERT] PR Maintenance Workflow Failed | bug, automation, P1 |
| #304 | Harden PowerShell module supply chain in CI/CD | security, P1 |
| #289 | Implement GitHub MCP skill for Claude Code and VS Code | skills, P1 |
| #286 | Rewrite simple GitHub skills to use gh CLI directly | skills, P1 |

### P2 (Normal)
| Issue | Title | Labels |
|-------|-------|--------|
| #311 | Migrate legacy consolidated memories to tiered index | agent-memory, P2 |
| #297 | Agent Drift Detected - 2025-12-23 | drift-detected, P2 |
| #293 | Add merged-PR detection to empty diff categorization | enhancement, P2 |
| #292 | Add PR number validation to Copilot follow-up detection | enhancement, P2 |
| #291 | Improve Pester test coverage for Detect-CopilotFollowUpPR.ps1 | enhancement, P2 |
| #288 | Document hybrid PowerShell architecture decision | documentation, P2 |
| #284 | Implement -NoProfile when shelling out to pwsh | enhancement, P2 |

## By Category

**Workflow Alerts (Duplicates)**: #318, #317, #316, #314, #312, #309, #306, #305
- Root cause: PR maintenance workflow failing repeatedly
- Consider: Consolidating into single tracking issue

**Memory/Skills**: #307, #311
**Security**: #304
**GitHub Integration**: #289, #286
**Documentation**: #288, #297
**Enhancements**: #293, #292, #291, #284
