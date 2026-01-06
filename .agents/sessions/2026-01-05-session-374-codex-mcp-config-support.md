# Session 374: Codex MCP Configuration Support

**Date**: 2026-01-05
**Branch**: `copilot/implement-qa-validation-gate`
**Issue**: #804
**Session Type**: Feature Implementation

## Session Info

- **Agent**: Claude Sonnet 4.5
- **Duration**: ~30 minutes
- **Focus**: Issue clarification and PRD documentation

## Session Start

### Git Status

- **Branch**: copilot/implement-qa-validation-gate
- **Status**: Clean
- **Starting Commit**: 0fa61641

### Objective

Update Sync-McpConfig.ps1 to support Codex's TOML configuration file format. Currently, Codex CLI cannot function in this project because:

1. AGENTS.md requires Serena initialization before proceeding
2. Codex requires `.codex/config.toml` for MCP server configuration
3. Sync-McpConfig.ps1 does not support TOML format

### Context Retrieved

- Read HANDOFF.md (read-only reference)
- Read usage-mandatory memory (skill-first pattern)
- Current branch: copilot/implement-qa-validation-gate

## Work Log

### Investigation Phase

#### Current State Analysis

**Sync-McpConfig.ps1 Capabilities**:
- Syncs from `.mcp.json` (Claude Code format)
- Targets: VS Code (`.vscode/mcp.json`) and Factory (`.factory/mcp.json`)
- Format: JSON only
- Server transformations: Serena (context/port changes for VS Code)

**Gap Identified**:
- Codex CLI requires `.codex/config.toml` (TOML format)
- No TOML generation capability exists
- Issue #804 PRD focuses on OpenAI Codex MCP support but doesn't address TOML format

**Blocker**:
- AGENTS.md requires Serena initialization at session start
- Codex CLI cannot function without `.codex/config.toml`
- Without TOML support, Codex is unusable in this project

#### Codex TOML Format Requirements

From OpenAI Codex documentation (Issue #804 comment):

**File Location**: `~/.codex/config.toml` (user home) or `.codex/config.toml` (repo-local)

**TOML Structure**:
```toml
[mcp_servers.server_name]
command = "executable"
args = ["arg1", "arg2"]
startup_timeout_sec = 30
tool_timeout_sec = 120
enabled = true

[mcp_servers.server_name.env]
ENV_VAR = "value"
```

**Key Differences from JSON**:
- TOML uses `[mcp_servers.<name>]` table syntax
- Arrays use square brackets: `["item1", "item2"]`
- Environment variables in separate `[mcp_servers.<name>.env]` table
- No nested object structure like JSON

#### Implementation Plan

**Approach**: Manual TOML generation (no external dependencies)
- Simple format with predictable structure
- Avoids module dependency management
- Cross-platform PowerShell compatibility

### Issue Update Completed

**Updated Issue #804** with comprehensive PRD including:

1. **Problem Statement Clarification**:
   - Codex CLI requires TOML format (`.codex/config.toml`)
   - Current script only supports JSON (VS Code, Factory)
   - Blocks Codex CLI usage in project

2. **TOML Format Documentation**:
   - File locations (repo-local and user home)
   - TOML structure with `[mcp_servers.name]` tables
   - Comparison table: JSON vs TOML differences
   - Example transformation from .mcp.json to config.toml

3. **Acceptance Criteria** (8 criteria):
   - AC1: Codex target support
   - AC2: TOML format correctness
   - AC3: SyncAll support (all three targets)
   - AC4: Custom destination path
   - AC5: Server-specific transformations
   - AC6: Documentation updates
   - AC7: Test coverage
   - AC8: Security validation

4. **Implementation Plan** (4 phases):
   - Phase 1: TOML generation function
   - Phase 2: Target integration
   - Phase 3: Testing
   - Phase 4: Documentation

5. **Technical Design**:
   - ConvertTo-Toml function signature
   - Script changes for 'codex' target
   - Default path resolution

**Issue URL**: https://github.com/rjmurillo/ai-agents/issues/804

## Outcome

Issue #804 has been updated with a comprehensive PRD that clarifies:

1. The actual requirement: TOML format support for Codex CLI (not just OpenAI MCP server)
2. The blocker: Codex requires `.codex/config.toml` to function
3. A complete implementation plan with 4 phases
4. 8 acceptance criteria covering functionality, testing, documentation, and security
5. Technical design showing ConvertTo-Toml function and script modifications

**No code changes made** per user request. Issue is ready for implementation by another agent or future session.

## Protocol Compliance

### Session Start - COMPLETE ALL before any work

- [x] Initialize Serena (mcp__serena__activate_project + initial_instructions)
- [x] Read HANDOFF.md (read-only reference)
- [x] Read usage-mandatory memory
- [x] Create session log
- [x] Verify branch (copilot/implement-qa-validation-gate)

### Session End - COMPLETE ALL before closing

- [x] Complete session log with outcomes
- [x] Do NOT update HANDOFF.md (read-only)
- [x] Run markdownlint
- [x] Commit all changes
- [x] Run session protocol validation (PASS)

## Session End Checklist

- [x] Session log completed with outcomes
- [x] Issue #804 updated with comprehensive PRD
- [x] TOML format requirements documented
- [x] Acceptance criteria defined (8 criteria)
- [x] Implementation plan outlined (4 phases)
- [x] Technical design provided
- [x] Run markdownlint
- [x] Commit changes
- [x] Run session protocol validation (PASS)

## Evidence

| Requirement | Evidence |
|-------------|----------|
| Issue updated | https://github.com/rjmurillo/ai-agents/issues/804 |
| TOML format documented | Issue body sections: "Codex TOML Format Requirements" |
| Acceptance criteria | Issue body section: "Acceptance Criteria" (AC1-AC8) |
| Implementation plan | Issue body section: "Implementation Plan" (4 phases) |
| Commit SHA | 5ef9b46f |

