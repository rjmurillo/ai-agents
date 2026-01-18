# Skill Sidecar Learnings: MCP Integration

**Last Updated**: 2026-01-18
**Sessions Analyzed**: 1 (batch 28)

## Constraints (HIGH confidence)

None yet.

## Preferences (MED confidence)

### Skill-MCP-004: GitHub MCP Gaps Requiring GraphQL Fallback
**Pattern**: When evaluating MCP server adoption, audit capabilities against current usage to identify GraphQL/API fallback needs. github/github-mcp-server (as of 2025-12-23) exposes 40+ tools but has gaps requiring hybrid approach: MCP for CRUD operations, GraphQL for advanced features.

**Evidence**: Session 81 cataloged GitHub MCP server capabilities (2025-12-23):
- **Covered**: PR CRUD (create, update, merge, list), Issue CRUD, Labels, Milestones
- **Missing**: Dedicated `add_reaction` tool, explicit GraphQL query passthrough, review thread resolution APIs

Current PowerShell skills in `.claude/skills/github/` use GraphQL for reactions and thread resolution. Migration requires maintaining GraphQL fallback.

**When Applied**: When planning MCP server migration. Map existing capabilities to MCP tools, identify gaps, design hybrid integration.

**Limitation**: MCP server may add missing tools in future. Gap analysis valid as of snapshot date (2025-12-23).

**Session**: batch-28, 2026-01-18

---

## Edge Cases (MED confidence)

None yet.

## Notes for Review (LOW confidence)

None yet.
