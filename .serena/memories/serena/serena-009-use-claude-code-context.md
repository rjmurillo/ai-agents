# Skill: Use claude-code Context for CLI

**Skill ID**: skill-serena-009-use-claude-code-context
**Category**: Setup
**Impact**: Medium (removes duplicate capabilities)
**Status**: Mandatory for Claude Code CLI

## Trigger Condition

When configuring Serena for use with Claude Code CLI.

## Action Pattern

MCP configuration in `~/.config/claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "serena": {
      "command": "uvx",
      "args": [
        "--from", "git+https://github.com/oraios/serena",
        "serena", "start-mcp-server",
        "--context", "claude-code",
        "--mode", "interactive",
        "--mode", "editing",
        "--project-from-cwd"
      ]
    }
  }
}
```

## Cost Benefit

Prevents duplicate tools and conflicting capabilities between Claude Code and Serena.

## Evidence

From SERENA-BEST-PRACTICES.md lines 116-126 and 262-280:
- claude-code context disables duplicate capabilities
- Recommended for Claude Code CLI environment
- Avoids tool conflicts

## Example

```json
# Use claude-code context (not desktop-app)
"--context", "claude-code"

# Enable interactive and editing modes
"--mode", "interactive",
"--mode", "editing"

# Auto-detect project from working directory
"--project-from-cwd"
```

## Atomicity Score

90% - Single concept: configure claude-code context for CLI

## Validation Count

0 (newly extracted)

## Related Skills

- skill-serena-008-configure-global-limits
- skill-serena-010-session-continuation
