# MCP Tool Ecosystem

This document describes the Model Context Protocol (MCP) tool ecosystem for ai-agents.

## Current MCP Servers

| Server | Purpose | Status |
|--------|---------|--------|
| **Serena** | Code navigation, symbol analysis, memory management | Active |
| **DeepWiki** | Repository documentation and AI-powered knowledge | Active |
| **Forgetful** | Semantic memory with vector search | Planned |

### Configuration

MCP servers are configured in `.mcp.json`:

```json
{
  "mcpServers": {
    "serena": { "type": "stdio", "command": "uvx", "args": ["--from", "git+https://github.com/oraios/serena", "serena", "start-mcp-server", "--project", "${workspaceFolder:-.}", "--context", "claude-code"] },
    "deepwiki": { "type": "http", "url": "https://mcp.deepwiki.com/mcp" },
    "forgetful": { "type": "stdio", "command": "uvx", "args": ["forgetful-ai"] }
  }
}
```

## Planned MCP Expansion

Per [ADR-048](../.agents/architecture/ADR-048-mcp-tool-ecosystem-expansion.md), the ecosystem will expand in four phases.

### Phase 1: Foundation

Build on existing ADRs for core infrastructure MCPs.

| MCP | Tools | ADR | Issue |
|-----|-------|-----|-------|
| Session State | `session_start`, `validate_gate`, `advance_phase`, `session_end` | [ADR-011](../.agents/architecture/ADR-011-session-state-mcp.md) | #219 |
| Skill Catalog | `search_skills`, `get_skill`, `check_skill_exists`, `cite_skill` | [ADR-012](../.agents/architecture/ADR-012-skill-catalog-mcp.md) | #220 |
| Agent Orchestration | `invoke_agent`, `track_handoff`, `get_routing_recommendation` | [ADR-013](../.agents/architecture/ADR-013-agent-orchestration-mcp.md) | #221 |

### Phase 2: GitHub Integration

Replace skill-based GitHub operations with MCP tools.

| Tool | Purpose | Current Approach |
|------|---------|------------------|
| `github_repo_analyze` | Repository structure analysis | Manual exploration |
| `github_pr_manage` | PR creation, review, merge | PowerShell skills |
| `github_issue_track` | Issue management, labeling | `gh` CLI via skills |
| `github_release_manage` | Release coordination | Manual `gh release` |

### Phase 3: Performance Tools

Add observability and performance analysis.

| Tool | Purpose |
|------|---------|
| `performance_report` | Generate session/agent performance summary |
| `bottleneck_analyze` | Identify slow operations |
| `benchmark_run` | Execute benchmarks |
| `metrics_collect` | Gather system metrics |

### Phase 4: Neural/Learning Tools

Enable pattern learning from execution history.

| Tool | Purpose |
|------|---------|
| `neural_train` | Train patterns from successful workflows |
| `neural_patterns` | Query learned patterns |
| `learning_adapt` | Apply adaptive learning |
| `skill_consolidate` | Auto-extract skills from retrospectives |

## Using MCP Tools

### Tool Discovery

Use ToolSearch to find available MCP tools:

```text
ToolSearch("serena memory")
ToolSearch("select:mcp__serena__read_memory")
```

### Serena Tools

| Tool | Purpose |
|------|---------|
| `mcp__serena__activate_project` | Initialize Serena for project |
| `mcp__serena__initial_instructions` | Get project-specific instructions |
| `mcp__serena__read_memory` | Read from memory store |
| `mcp__serena__write_memory` | Write to memory store |
| `mcp__serena__list_memories` | List available memories |
| `mcp__serena__find_symbol` | Find code symbols |
| `mcp__serena__get_symbols_overview` | Get symbol overview |
| `mcp__serena__find_referencing_symbols` | Find symbol references |

### DeepWiki Tools

| Tool | Purpose |
|------|---------|
| `mcp__deepwiki__read_wiki_structure` | Get documentation topics |
| `mcp__deepwiki__read_wiki_contents` | View documentation |
| `mcp__deepwiki__ask_question` | AI-powered Q&A |

## Related Documents

- [ADR-048: MCP Tool Ecosystem Expansion](../.agents/architecture/ADR-048-mcp-tool-ecosystem-expansion.md)
- [ADR-011: Session State MCP](../.agents/architecture/ADR-011-session-state-mcp.md)
- [ADR-012: Skill Catalog MCP](../.agents/architecture/ADR-012-skill-catalog-mcp.md)
- [ADR-013: Agent Orchestration MCP](../.agents/architecture/ADR-013-agent-orchestration-mcp.md)
- [Claude-flow Architecture Analysis](../.agents/analysis/claude-flow-architecture-analysis.md)
