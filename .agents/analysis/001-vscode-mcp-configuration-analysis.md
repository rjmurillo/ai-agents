# Analysis: VS Code MCP Server Configuration

## Value Statement

This analysis provides verified information about VS Code's Model Context Protocol (MCP) server configuration to ensure the mcp-sync utility generates correct configuration files.

## Business Objectives

- Ensure mcp-sync utility generates VS Code-compatible MCP configurations
- Prevent configuration errors and incompatibilities
- Support workspace-level and user-level MCP server configurations

## Context

VS Code added MCP support in version 1.102 (generally available). The configuration format differs from other MCP clients (Claude Desktop, Cursor, Windsurf) in key ways:

1. **Different root key**: VS Code uses `"servers"` while Claude Desktop uses `"mcpServers"`
2. **Different file location**: VS Code uses `.vscode/mcp.json` for workspace configs
3. **Additional features**: VS Code supports input variables for secure credential handling

## Methodology

Research conducted through:
- Official VS Code documentation (code.visualstudio.com)
- Microsoft Learn documentation
- GitHub examples and issue reports
- Real-world configuration examples

## Findings

### Facts (Verified)

#### 1. File Name

**Canonical file name**: `mcp.json`

**No leading dot**: The file is named `mcp.json`, NOT `.mcp.json`

#### 2. Root Key

**VS Code uses**: `"servers"` (NOT `"mcpServers"`)

This is a **breaking difference** from Claude Desktop and other MCP clients:
- **Claude Desktop/Cursor/Windsurf**: Use `"mcpServers"` as root key
- **VS Code**: Uses `"servers"` as root key

#### 3. File Locations (In Order of Precedence)

**For VS Code:**

1. **Workspace configuration** (most common for project-specific):
   - Path: `<workspace-root>/.vscode/mcp.json`
   - Scope: Workspace-specific, can be committed to version control
   - Use case: Sharing MCP configuration with team members

2. **User/Global configuration**:
   - Access via: Command Palette → `MCP: Open User Configuration`
   - Scope: All workspaces for the user
   - Use case: Personal MCP servers used across all projects

**For Visual Studio (Windows):**

1. `<SOLUTIONDIR>\.vscode\mcp.json` - Workspace/solution level
2. `<SOLUTIONDIR>\.cursor\mcp.json` - Workspace/solution level
3. `<SOLUTIONDIR>\.vs\mcp.json` - Visual Studio specific, user-scoped
4. `<SOLUTIONDIR>\.mcp.json` - Solution root, can be committed to source control
5. `%USERPROFILE%\.mcp.json` - Global user configuration

#### 4. Schema Structure

**Top-level schema**:

```json
{
  "inputs": [/* optional input variables */],
  "servers": {/* required server definitions */}
}
```

**Server definition schema** (stdio transport):

```json
{
  "servers": {
    "server-name": {
      "type": "stdio",
      "command": "executable-path-or-name",
      "args": ["arg1", "arg2"],
      "env": {
        "VAR_NAME": "value"
      }
    }
  }
}
```

**Server definition schema** (HTTP transport):

```json
{
  "servers": {
    "server-name": {
      "type": "http",
      "url": "https://example.com/mcp"
    }
  }
}
```

Or simplified HTTP format:

```json
{
  "servers": {
    "server-name": {
      "url": "https://example.com/mcp"
    }
  }
}
```

**Input variables schema** (for secure credential handling):

```json
{
  "inputs": [
    {
      "type": "promptString",
      "id": "variable-id",
      "description": "User-facing description",
      "password": true,
      "default": "optional-default-value"
    }
  ],
  "servers": {
    "server-name": {
      "type": "stdio",
      "command": "command",
      "env": {
        "API_KEY": "${input:variable-id}"
      }
    }
  }
}
```

#### 5. Complete Working Examples

**Example 1: Simple stdio server (Go executable)**

```json
{
  "servers": {
    "mcpgo1": {
      "type": "stdio",
      "command": "C:\\Users\\user\\git\\mcp-tutorial\\go-server\\mcpgo.exe",
      "args": []
    }
  }
}
```

**Example 2: Python server using uv**

```json
{
  "servers": {
    "blog-search": {
      "type": "stdio",
      "command": "~/.local/bin/uv",
      "args": [
        "run",
        "--with",
        "google-search-results",
        "--with",
        "mcp[cli]",
        "mcp",
        "run",
        "~/projects/blog-search-mcp/src/server.py"
      ]
    }
  }
}
```

**Example 3: npx server with secure API key input**

```json
{
  "inputs": [
    {
      "type": "promptString",
      "id": "perplexity-key",
      "description": "Perplexity API Key",
      "password": true
    }
  ],
  "servers": {
    "Perplexity": {
      "type": "stdio",
      "command": "npx",
      "args": [
        "-y",
        "@modelcontextprotocol/server-perplexity-ask"
      ],
      "env": {
        "PERPLEXITY_API_KEY": "${input:perplexity-key}"
      }
    }
  }
}
```

**Example 4: .NET project**

```json
{
  "servers": {
    "SampleMcpServer": {
      "type": "stdio",
      "command": "dotnet",
      "args": [
        "run",
        "--project",
        "path/to/project.csproj"
      ]
    }
  }
}
```

**Example 5: Remote HTTP server**

```json
{
  "servers": {
    "my-mcp-server": {
      "url": "http://localhost:5000/mcp"
    }
  }
}
```

**Example 6: Azure Functions with headers**

```json
{
  "inputs": [
    {
      "type": "promptString",
      "id": "function-key",
      "description": "Azure Function Key",
      "password": true
    }
  ],
  "servers": {
    "azure-mcp": {
      "type": "http",
      "url": "https://myfunction.azurewebsites.net/api/mcp",
      "headers": {
        "x-functions-key": "${input:function-key}"
      }
    }
  }
}
```

#### 6. Key Configuration Properties

**Required fields for stdio servers:**
- `type`: Must be `"stdio"` for standard input/output transport
- `command`: Executable path (absolute or in PATH)
- `args`: Array of command-line arguments (can be empty `[]`)

**Optional fields for stdio servers:**
- `env`: Object with environment variable key-value pairs

**Required fields for HTTP servers:**
- `url`: HTTP endpoint URL

**Optional fields for HTTP servers:**
- `type`: Can be `"http"` (optional if `url` is present)
- `headers`: Object with HTTP header key-value pairs

**Input variable fields:**
- `type`: Must be `"promptString"`
- `id`: Unique identifier for the input variable
- `description`: User-facing prompt text
- `password`: Boolean (true hides input like a password field)
- `default`: Optional default value

#### 7. Variable Substitution

VS Code supports input variable substitution using `${input:variable-id}` syntax in:
- `env` object values
- `headers` object values (for HTTP servers)

**Known limitation**: The `{workspaceFolder}` variable (used in tasks.json, launch.json) is NOT currently supported in `mcp.json` (as of December 2024).

#### 8. VS Code Features

**Server management commands**:
- `MCP: Add Server` - Interactive server configuration
- `MCP: Open User Configuration` - Opens global mcp.json
- Start/Stop/Restart commands (available in editor when viewing mcp.json)

**Settings**:
- `chat.mcp.autostart` - Automatically restart MCP servers on config changes (experimental)

**IntelliSense support**:
- VS Code provides JSON schema validation and autocomplete for mcp.json files

**MCP Marketplace**:
- VS Code now includes built-in MCP marketplace in Extensions view
- Powered by GitHub MCP registry

### Hypotheses (Unverified)

1. **Schema validation differences**: Some MCP servers return JSON schemas using Draft 2020-12 features (`$dynamicRef`) that may not be fully supported by VS Code's validator
2. **Variable resolution order**: Unclear if input variables can reference other input variables
3. **Conflict resolution**: When both workspace and user configs define the same server name, precedence rules are not explicitly documented

## Recommendations

### For mcp-sync Utility

1. **Generate separate files for different clients**:
   - `claude_desktop_config.json` → Use `"mcpServers"` root key
   - `.vscode/mcp.json` → Use `"servers"` root key

2. **Support workspace-scoped configuration**:
   - Create `.vscode/mcp.json` in workspace root
   - Include in `.gitignore` if contains sensitive data
   - Commit to source control if using input variables for secrets

3. **Transform root key based on target**:
   ```javascript
   // Pseudo-code
   if (target === 'vscode') {
     config.servers = sourceConfig.mcpServers;
   } else if (target === 'claude') {
     config.mcpServers = sourceConfig.servers;
   }
   ```

4. **Handle input variables**:
   - Extract environment variable references from source config
   - Generate `inputs` array with `promptString` entries
   - Replace hardcoded secrets with `${input:variable-id}` references

5. **Validate generated configuration**:
   - Ensure `command` paths are absolute or in PATH
   - Verify `args` is always an array
   - Check `env` values are strings (no objects or arrays)

6. **Document differences**:
   - Warn users about `mcpServers` vs `servers` key difference
   - Explain workspace vs user configuration trade-offs
   - Provide migration guide from Claude Desktop format

### Schema Compatibility Matrix

| Feature | Claude Desktop | VS Code | Notes |
|---------|---------------|---------|-------|
| Root key | `mcpServers` | `servers` | BREAKING DIFFERENCE |
| File name | `claude_desktop_config.json` | `mcp.json` | Different names |
| Location | `~/Library/Application Support/Claude/` | `.vscode/` or user profile | Different paths |
| Input variables | ❌ Not supported | ✅ Supported | VS Code feature |
| stdio transport | ✅ Supported | ✅ Supported | Compatible |
| HTTP transport | ❓ Unknown | ✅ Supported | VS Code documented |
| Env variables | ✅ Supported | ✅ Supported | Compatible |

## Open Questions

1. **Does VS Code support SSE transport?** - Documentation mentions "server-sent events (sse)" but examples show only stdio and HTTP
2. **Variable resolution in user config?** - Can user-level mcp.json reference workspace-specific paths?
3. **Headers in stdio transport?** - Can headers be specified for stdio servers, or only HTTP?
4. **Conflict resolution priority?** - What happens if both workspace and user configs define same server name?
5. **Windows path handling?** - Are forward slashes `/` automatically converted to backslashes `\` on Windows?

## Source Citations

### Official Documentation

1. [Use MCP servers in VS Code](https://code.visualstudio.com/docs/copilot/customization/mcp-servers) - Primary VS Code documentation
2. [MCP developer guide - VS Code Extension API](https://code.visualstudio.com/api/extension-guides/ai/mcp) - Developer-focused documentation
3. [Use MCP Servers - Visual Studio (Windows)](https://learn.microsoft.com/en-us/visualstudio/ide/mcp-servers?view=vs-2022) - Visual Studio documentation
4. [Get started using Azure MCP Server with VS Code](https://learn.microsoft.com/en-us/azure/developer/azure-mcp-server/get-started/tools/visual-studio-code) - Azure MCP example
5. [Extending GitHub Copilot Chat with MCP servers](https://docs.github.com/copilot/customizing-copilot/using-model-context-protocol/extending-copilot-chat-with-mcp) - GitHub Copilot integration

### Community Resources

6. [VS Code MCP tutorial - GitHub](https://github.com/msalemor/mcp-vscode-tutorial) - Complete working example
7. [MCP for beginners - Microsoft](https://github.com/microsoft/mcp-for-beginners/blob/main/03-GettingStarted/04-vscode/README.md) - Tutorial
8. [How to Set Up mcp.json in VS Code - Medium](https://medium.com/@praveen.valaboju1/%EF%B8%8F-how-to-set-up-mcp-json-in-visual-studio-code-03ff29c6b00b) - Setup guide
9. [Configure Local Python MCP Server in VS Code](https://jtemporal.com/configure-local-python-mcp-server-in-vscode/) - Python example
10. [Stop Guessing: MCP Elicitations in VS Code](https://den.dev/blog/vscode-mcp-elicitations-stop-guessing/) - Input variables guide

### Issue Reports

11. [User mcp.json should follow standard schema - Issue #252907](https://github.com/microsoft/vscode/issues/252907) - Schema compatibility discussion
12. [Support {workspaceFolder} Variable - Issue #251263](https://github.com/microsoft/vscode/issues/251263) - Variable support request
13. [Update VS Code installation instructions - PR #2328](https://github.com/modelcontextprotocol/servers/pull/2328/files) - Documentation update

---

**Analysis completed**: 2025-12-17
**Analyst**: analyst agent
**Confidence level**: High (verified against official documentation and multiple working examples)
