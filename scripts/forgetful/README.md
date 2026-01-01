# Forgetful MCP Server Setup

Forgetful provides semantic memory with automatic knowledge graph construction for AI agents.

## Why HTTP Transport?

Forgetful's stdio transport is broken due to FastMCP banner corruption ([upstream issue #19](https://github.com/ScottRBK/forgetful/issues/19)). **Use HTTP transport instead.**

## Prerequisites

| Requirement | Version | Check Command |
|-------------|---------|---------------|
| Python | 3.11+ | `python --version` |
| uv | Latest | `uv --version` or install via `pip install uv` |
| uvx | Latest | Included with uv |

### Install uv (if missing)

```bash
# Linux/macOS
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

## Quick Start

### Option 1: Manual (Testing)

```bash
# Start Forgetful HTTP server on port 8020
uvx forgetful-ai --transport http --port 8020
```

### Option 2: Linux Systemd Service (Recommended)

```bash
# Run the setup script
pwsh scripts/forgetful/Install-ForgetfulLinux.ps1

# Or manually:
mkdir -p ~/.config/systemd/user
cat > ~/.config/systemd/user/forgetful.service << 'EOF'
[Unit]
Description=Forgetful MCP Server
After=network.target

[Service]
ExecStart=%h/.local/bin/uvx forgetful-ai --transport http --port 8020
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable forgetful
systemctl --user start forgetful
```

### Option 3: Windows Service (Recommended)

```powershell
# Run the setup script
pwsh scripts/forgetful/Install-ForgetfulWindows.ps1

# This creates a scheduled task that runs at login
```

## Configuration

### Project .mcp.json

Add Forgetful to your project's `.mcp.json`:

```json
{
  "mcpServers": {
    "forgetful": {
      "type": "http",
      "url": "http://localhost:8020/mcp"
    }
  }
}
```

### Claude Code Settings

Enable the Forgetful plugin in `.claude/settings.json`:

```json
{
  "enabledPlugins": {
    "forgetful@scottrbk": true
  }
}
```

## Health Check

Verify Forgetful is operational:

```bash
# Using the health check script
pwsh scripts/forgetful/Test-ForgetfulHealth.ps1

# Manual check
curl -s -X POST http://localhost:8020/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"tools/list","id":1}'
```

Expected: JSON response with tool definitions.

## Service Management

### Linux (systemd)

```bash
# Status
systemctl --user status forgetful

# Logs
journalctl --user -u forgetful -f

# Restart
systemctl --user restart forgetful

# Stop
systemctl --user stop forgetful

# Disable
systemctl --user disable forgetful
```

### Windows (Scheduled Task)

```powershell
# Status
Get-ScheduledTask -TaskName "ForgetfulMCP" | Get-ScheduledTaskInfo

# Stop
Stop-ScheduledTask -TaskName "ForgetfulMCP"

# Start
Start-ScheduledTask -TaskName "ForgetfulMCP"

# Remove
Unregister-ScheduledTask -TaskName "ForgetfulMCP" -Confirm:$false
```

## Troubleshooting

### Port Already in Use

```bash
# Find process using port 8020
lsof -i :8020  # Linux/macOS
netstat -ano | findstr :8020  # Windows

# Kill if needed
kill <PID>  # Linux/macOS
taskkill /PID <PID> /F  # Windows
```

### uvx Not Found

```bash
# Ensure uv is in PATH
export PATH="$HOME/.local/bin:$PATH"  # Linux/macOS
$env:PATH = "$env:USERPROFILE\.local\bin;$env:PATH"  # Windows
```

### Database Location

Forgetful stores data in:

- **Linux/macOS**: `~/.local/share/forgetful/`
- **Windows**: `%LOCALAPPDATA%\forgetful\`

### Logs Show No Activity

1. Check if Claude Code is connecting: Look for POST requests in logs
2. Verify `.mcp.json` has correct URL (`http://localhost:8020/mcp`)
3. Verify plugin is enabled in `.claude/settings.json`

## Integration with AI Agents

### Memory-First Architecture (ADR-007)

Forgetful is a **supplementary** memory layer. Serena is canonical:

```text
1. Read from Serena (canonical, always available)
2. Augment with Forgetful (if available) - semantic search
3. Persist to Serena (markdown files)
4. Commit with code
```

### Fallback Behavior

When Forgetful is unavailable:

- Use Serena `memory-index` for keyword-based discovery
- Proceed with Serena memories already loaded
- Document in session log: `(Forgetful unavailable - Serena only)`

### Tools Available

| Tool | Purpose |
|------|---------|
| `discover_forgetful_tools` | List all available tools by category |
| `execute_forgetful_tool` | Execute any tool dynamically |
| `how_to_use_forgetful_tool` | Get detailed docs for a tool |

Common operations:

```python
# Search memories
mcp__forgetful__execute_forgetful_tool("query_memory", {"query": "search terms", "query_context": "why"})

# Create memory
mcp__forgetful__execute_forgetful_tool("create_memory", {
    "title": "Title",
    "content": "Content",
    "context": "Why this matters",
    "keywords": ["kw1"],
    "tags": ["tag1"],
    "importance": 7,
    "project_ids": [1]
})

# List projects
mcp__forgetful__execute_forgetful_tool("list_projects", {})
```

## Related Documentation

- [Forgetful GitHub](https://github.com/ScottRBK/forgetful)
- [ADR-007: Memory-First Architecture](.agents/architecture/ADR-007-memory-first-architecture.md)
- [CLAUDE.md](CLAUDE.md) - Memory System section
