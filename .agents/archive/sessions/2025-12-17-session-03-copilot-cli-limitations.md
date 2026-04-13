# Session Log: Copilot CLI Limitations Documentation

**Session ID**: 2025-12-17-session-03
**Date**: 2025-12-17
**Agent**: orchestrator (direct)
**Branch**: `fix/copilot-mcp`

---

## Protocol Compliance

- [x] Phase 1: Serena activated with `mcp__serena__activate_project`
- [x] Phase 1: `mcp__serena__initial_instructions` called
- [x] Phase 2: `.agents/HANDOFF.md` read
- [x] Phase 3: Session log created (this file)
- [x] Session End: HANDOFF.md updated
- [x] Session End: Markdownlint run
- [x] Session End: Changes committed (3a6e499)

---

## Objective

Document comprehensive limitations of GitHub Copilot CLI compared to Claude Code and VS Code, and make a strategic decision on whether to continue supporting Copilot CLI in the roadmap.

## Context

- Prior retrospective (`.agents/retrospective/2025-12-18-mcp-config.md`) recommended updating `Sync-McpConfig.ps1` to sync to Copilot CLI home config
- User declined this recommendation due to Copilot CLI's limited functionality
- Need to thoroughly document limitations to inform roadmap priorities

## Research Summary

### Copilot CLI Key Limitations vs Claude Code / VS Code

| Capability | Claude Code | VS Code | Copilot CLI |
|------------|-------------|---------|-------------|
| Workspace-level MCP config | ✅ `.mcp.json` | ✅ `.vscode/mcp.json` | ❌ User-level only |
| Project-level agent config | ✅ | ✅ `.github/agents/` | ⚠️ Known issues |
| Input variables for secrets | ✅ | ✅ `${input:id}` | ❌ Requires `COPILOT_MCP_` prefix |
| Plan Mode | ✅ | ✅ | ❌ |
| Agent Sessions view | N/A | ✅ | ❌ |
| Chat checkpoints | ✅ (via memory) | ✅ | ❌ |
| LSP/semantic code analysis | ✅ (via Serena) | ✅ (native) | ❌ Text search only |
| Custom model endpoints | ❌ | ⚠️ Limited | ❌ |
| Context window | Large (varies) | 64k-128k | 8k-32k (limited) |
| Offline/air-gapped | ✅ (local models) | ⚠️ Limited | ❌ Requires internet |

### MCP Configuration Differences

| Aspect | Claude Code | VS Code | Copilot CLI |
|--------|-------------|---------|-------------|
| File name | `.mcp.json` | `mcp.json` | `mcp-config.json` |
| Root key | `mcpServers` | `servers` | `mcpServers` |
| Location | Project root | `.vscode/` | `~/.copilot/` (user-level) |
| Scope | Project-level | Workspace-level | User-level only |

### Critical Strategic Issues

1. **No workspace-level config**: Copilot CLI only loads from `~/.copilot/mcp-config.json` - cannot have project-specific MCP servers
2. **No VS Code integration**: Despite sharing the Copilot brand, CLI is a completely separate product with no config sharing
3. **Limited competitive advantage**: Users question value vs Codex CLI or Claude Code which offer more features
4. **Context window constraints**: Significantly smaller than VS Code/Claude Code

## Decision

**DECLINE** the retrospective recommendation to add Copilot CLI sync to `Sync-McpConfig.ps1`.

### Rationale

1. **User-level config risk**: Syncing to `~/.copilot/` would modify user's global config, not project-specific
2. **Limited ROI**: Copilot CLI lacks features that make the investment worthwhile
3. **Platform focus**: Claude Code and VS Code provide significantly better capabilities
4. **Maintenance burden**: Adding Copilot CLI sync adds complexity for minimal user value

## Deliverables

- [x] Create `.agents/analysis/002-copilot-cli-limitations-assessment.md`
- [x] Update `.agents/roadmap/product-roadmap.md` with Copilot CLI de-prioritization
- [x] Update `.agents/HANDOFF.md` with session summary and decision

## Sources

- [GitHub Issue #54: CLI should integrate VS Code features](https://github.com/github/copilot-cli/issues/54)
- [VS Code MCP Servers Documentation](https://code.visualstudio.com/docs/copilot/customization/mcp-servers)
- [DeepWiki: Copilot CLI MCP Configuration](https://deepwiki.com/github/copilot-cli/5.3-mcp-server-configuration)
- [GitHub Docs: Setting up GitHub MCP Server](https://docs.github.com/en/copilot/how-tos/provide-context/use-mcp/set-up-the-github-mcp-server)
