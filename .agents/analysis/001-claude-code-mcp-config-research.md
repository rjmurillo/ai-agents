# Analysis: Claude Code MCP Configuration Requirements

## Value Statement

This analysis provides authoritative documentation on Claude Code's MCP configuration requirements, enabling correct setup of MCP servers across different scopes and preventing configuration errors.

## Business Objectives

- Ensure reliable MCP server configuration for team collaboration
- Prevent configuration errors that cause server loading failures
- Enable proper version control of project-scoped MCP servers
- Document schema requirements for automated tooling

## Context

The ai-agents project currently has TWO MCP configuration files with CONFLICTING root keys:
- `.mcp.json` uses `"mcpServers"` (CORRECT)
- `mcp.json` uses `"servers"` (INCORRECT)

This research determines the canonical configuration format to resolve this conflict.

## Methodology

1. Web search of official Anthropic documentation
2. Community documentation and GitHub issues analysis
3. Real-world usage examples from multiple sources
4. Local codebase inspection

## Findings

### 1. File Name

**Verified Fact**: Claude Code supports `.mcp.json` (with leading dot) for project-scoped MCP configuration.

**Evidence**:
- Official Anthropic docs: "Configure MCP servers in `.mcp.json` at your project root"
- GitHub Issue #5037: Confirms `.mcp.json` in project root works correctly
- GitHub Issue #4976: Documents `.claude/.mcp.json` does NOT work (location matters)

**File Name Variants**:
| File Name | Status | Notes |
|-----------|--------|-------|
| `.mcp.json` | CANONICAL | Project-scoped, version-controlled |
| `mcp.json` | NOT DOCUMENTED | No evidence this is recognized |
| `.claude/.mcp.json` | BROKEN | Known issue #5037, #4976 |

### 2. Root Key

**Verified Fact**: The ONLY documented root key is `"mcpServers"` (camelCase).

**Evidence**:
- All official documentation examples use `mcpServers`
- Community guides consistently use `mcpServers`
- FastMCP integration documentation specifies `mcpServers`
- No evidence of `"servers"` key being valid

**Root Key Comparison**:
| Key | Status | Sources |
|-----|--------|---------|
| `"mcpServers"` | CANONICAL | Official docs, all examples |
| `"servers"` | INVALID | No documentation found |

### 3. File Location Priority

**Verified Fact**: Claude Code searches for MCP configuration in the following locations (priority order):

1. **Local scope** (highest): `~/.claude.json` under project path
2. **Project scope**: `.mcp.json` in project root directory
3. **User scope**: `~/.claude.json` global configuration

**Scope Precedence**: When servers with the same name exist at multiple scopes:
- Local-scoped servers override project-scoped
- Project-scoped servers override user-scoped

**File Location Details**:
| Location | File | Scope | Version Control | Security Prompt |
|----------|------|-------|-----------------|-----------------|
| Project root | `.mcp.json` | Project | YES - recommended | YES - approval required |
| User home | `~/.claude.json` | User/Local | NO | NO |
| Project `.claude/` | `.claude/settings.local.json` | Project-local | NO | NO |

**Known Issues**:
- `~/.claude/settings.json` is IGNORED for MCP servers (GitHub Issue #4976)
- `.claude/.mcp.json` does NOT load properly (GitHub Issue #5037)

### 4. Schema Structure

**Verified Fact**: The canonical schema structure for each server entry:

```json
{
  "mcpServers": {
    "server-name": {
      "type": "stdio",           // Required: "stdio", "http", or "sse"
      "command": "executable",   // Required for stdio: command to run
      "args": ["arg1", "arg2"],  // Optional: command arguments
      "env": {                   // Optional: environment variables
        "VAR_NAME": "value"
      }
    }
  }
}
```

**Transport Types**:
| Type | Use Case | Required Fields |
|------|----------|-----------------|
| `stdio` | Local processes | `command`, optionally `args`, `env` |
| `http` | Remote servers | `url`, optionally `headers` |
| `sse` | Server-sent events | `url`, optionally `headers` |

**Field Specifications**:
- `type`: String enum - "stdio", "http", or "sse"
- `command`: String - absolute path or PATH-available executable
- `args`: Array of strings - command-line arguments
- `env`: Object - environment variable key-value pairs
- `url`: String (HTTP/SSE only) - server endpoint URL
- `headers`: Object (HTTP/SSE only) - HTTP headers

**Environment Variable Expansion** (supported in `.mcp.json`):
- `${VAR}` - expands to environment variable value
- `${VAR:-default}` - expands to VAR or default if unset
- Fails to parse if required variable is missing and has no default

### 5. Complete Example Configurations

**stdio Transport (npx-based)**:
```json
{
  "mcpServers": {
    "github": {
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {
        "GITHUB_PERSONAL_ACCESS_TOKEN": "${GITHUB_TOKEN}"
      }
    }
  }
}
```

**HTTP Transport**:
```json
{
  "mcpServers": {
    "api-server": {
      "type": "http",
      "url": "${API_BASE_URL:-https://api.example.com}/mcp",
      "headers": {
        "Authorization": "Bearer ${API_KEY}"
      }
    }
  }
}
```

**Multi-Server Configuration**:
```json
{
  "mcpServers": {
    "serena": {
      "type": "stdio",
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/oraios/serena",
        "serena",
        "start-mcp-server",
        "--context",
        "claude-code"
      ]
    },
    "deepwiki": {
      "type": "http",
      "url": "https://mcp.deepwiki.com/mcp"
    }
  }
}
```

### 6. CLI Integration

**Verified Fact**: Claude CLI supports managing MCP servers with scope options:

```bash
# Add server (stdio)
claude mcp add server-name --scope project --command npx --args "-y" "@package/name"

# Add server (JSON)
claude mcp add-json server-name '{"type":"http","url":"https://..."}' --scope project

# List all servers
claude mcp list

# Get server details
claude mcp get server-name

# Remove server
claude mcp remove server-name
```

**Scope Options**:
- `--scope local` (default): Only you in current project
- `--scope project`: Shared via `.mcp.json` (version-controlled)
- `--scope user`: Available across all projects

### 7. Project-Specific Issue

**Critical Finding**: The ai-agents project has TWO conflicting MCP configuration files:

1. `.mcp.json` - Uses CORRECT `"mcpServers"` key
2. `mcp.json` - Uses INVALID `"servers"` key

**Impact**: `mcp.json` is likely NOT being loaded by Claude Code, meaning any servers configured only in that file are unavailable.

**Evidence from local codebase**:
- `.mcp.json` exists with correct schema (serena, deepwiki)
- `mcp.json` exists with incorrect schema (same servers, wrong key)

## Recommendations

### 1. Immediate: Remove Invalid Configuration

Delete `mcp.json` (no leading dot, invalid root key) to prevent confusion:
```bash
rm D:\src\GitHub\rjmurillo-bot\ai-agents\mcp.json
```

### 2. Canonical Configuration Standard

**For this project**, use ONLY `.mcp.json` with `"mcpServers"` root key:
- File: `.mcp.json` in project root
- Root key: `"mcpServers"`
- Version control: YES (check into git)
- Schema: Follow examples in section 5

### 3. Documentation Update

Document MCP configuration requirements in project docs:
- Specify `.mcp.json` as canonical location
- Provide schema examples
- Reference this analysis document

### 4. Validation Tooling

Consider adding pre-commit validation for `.mcp.json`:
- JSON schema validation
- Root key verification (`mcpServers` required)
- Environment variable syntax check

### 5. Future: MCP Configuration Sync Utility

The existing `Sync-MCPConfig.ps1` utility should:
- Target `.mcp.json` (not `mcp.json`)
- Validate `mcpServers` root key
- Support environment variable expansion syntax
- Generate correct schema format

## Open Questions

### Hypothesis 1: mcp.json Support

**Question**: Does Claude Code support `mcp.json` (without leading dot)?

**Status**: UNVERIFIED - No documentation found supporting this file name

**Evidence Gap**: All documentation exclusively mentions `.mcp.json`

**Recommendation**: Assume NOT supported until proven otherwise

### Hypothesis 2: Schema Evolution

**Question**: Was `"servers"` root key supported in earlier versions?

**Status**: UNVERIFIED - Search focused on current (2025) documentation

**Evidence Gap**: Historical version documentation not reviewed

**Recommendation**: Use current canonical format regardless of history

## Source Citations

### Official Anthropic Documentation

1. [Connect Claude Code to tools via MCP - Claude Code Docs](https://docs.anthropic.com/en/docs/claude-code/mcp)
2. [Claude Code settings - Claude Code Docs](https://code.claude.com/docs/en/settings)

### GitHub Issues (Anthropic Repository)

3. [Documentation incorrect about MCP configuration file location - Issue #4976](https://github.com/anthropics/claude-code/issues/4976)
4. [MCP servers in .claude/.mcp.json not loading properly - Issue #5037](https://github.com/anthropics/claude-code/issues/5037)
5. [Feature Request: Support project-based MCP configuration via .claude subdirectory - Issue #5350](https://github.com/anthropics/claude-code/issues/5350)

### Community Documentation

6. [Configuring MCP Tools in Claude Code - The Better Way - Scott Spence](https://scottspence.com/posts/configuring-mcp-tools-in-claude-code)
7. [Add MCP Servers to Claude Code - Setup & Configuration Guide - MCPcat](https://mcpcat.io/guides/adding-an-mcp-server-to-claude-code/)
8. [Claude Code Configuration Guide - ClaudeLog](https://claudelog.com/configuration/)
9. [MCP JSON Configuration - FastMCP](https://gofastmcp.com/integrations/mcp-json-configuration)

### Technical Resources

10. [Where Are Claude Code Global Settings Files Located - ClaudeLog](https://claudelog.com/faqs/where-are-claude-code-global-settings/)
11. [Set Up MCP with Claude Code - SailPoint Developer Community](https://developer.sailpoint.com/docs/extensibility/mcp/integrations/claude-code/)

## Data Transparency

### Information Successfully Verified

- `.mcp.json` as canonical file name
- `"mcpServers"` as only documented root key
- File location precedence order
- Complete schema structure for stdio, http, sse transports
- Environment variable expansion syntax
- CLI commands for server management
- Security approval requirement for project-scoped servers

### Information NOT Found

- Support for `mcp.json` (without leading dot)
- Support for `"servers"` root key
- Historical schema versions or deprecations
- Official JSON schema definition file
- Timeout/retry configuration options
- Server health check configuration

---

**Analysis Date**: 2025-12-17
**Analyst**: Claude (Analyst Agent)
**Project**: ai-agents
**Issue**: MCP configuration standardization
