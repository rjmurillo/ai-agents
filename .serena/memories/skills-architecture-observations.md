# Skill Sidecar Learnings: Architecture

**Last Updated**: 2026-01-18
**Sessions Analyzed**: 1 (batch 28)

## Constraints (HIGH confidence)

### Skill-Architecture-009: GitHub MCP Agent Isolation Pattern
**Pattern**: When integrating domain-specific MCP servers with many tools (40+), use agent-specific MCP server binding via YAML frontmatter instead of global enablement. This implements agent isolation to firewall toolsets from main session context, preventing context pollution.

**Evidence**: Session 81 GitHub MCP architecture analysis (2025-12-23) studied superpowers-chrome pattern. Agent YAML declares:
```yaml
name: browser-user
tools: [mcp__plugin_superpowers-chrome_chrome__use_browser]
```

github/github-mcp-server exposes 40+ tools:
- PR operations: 10 tools (create, update, merge, review, etc.)
- Issue operations: 8 tools (CRUD, comments, sub-issues)
- Labels: 3 tools
- Milestones: via issue_write parameter

**When Applied**: When integrating MCP servers that expose large toolsets. Main session delegates to specialized agent via Task tool. Only specialized agent sees domain tools (e.g., GitHub agent sees PR/issue tools, main session doesn't).

**Anti-Pattern**: Global MCP server enablement (`enableAllProjectMcpServers: true`) exposing 40+ tools to all sessions, bloating context and increasing token costs.

**Session**: batch-28, 2026-01-18

---

## Preferences (MED confidence)

None yet.

## Edge Cases (MED confidence)

None yet.

## Notes for Review (LOW confidence)

None yet.

## Related

- [skills-agent-workflow-index](skills-agent-workflow-index.md)
- [skills-analysis-index](skills-analysis-index.md)
- [skills-architecture-index](skills-architecture-index.md)
- [skills-autonomous-execution-index](skills-autonomous-execution-index.md)
- [skills-bash-integration-index](skills-bash-integration-index.md)
