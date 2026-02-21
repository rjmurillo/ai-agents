# GitHub MCP Server Installation

Configure the official GitHub MCP server for Claude Code.

## Prerequisites

- GitHub personal access token with required scopes
- Node.js 18+ or Docker

## Quick Setup (npx)

Add to `~/.claude/settings.json`:

```json
{
  "mcpServers": {
    "github": {
      "command": "npx",
      "args": ["-y", "@github/mcp-server"],
      "env": {
        "GITHUB_PERSONAL_ACCESS_TOKEN": "ghp_xxxx"
      }
    }
  }
}
```

## Docker Setup

```json
{
  "mcpServers": {
    "github": {
      "command": "docker",
      "args": [
        "run", "-i", "--rm",
        "-e", "GITHUB_PERSONAL_ACCESS_TOKEN",
        "ghcr.io/github/github-mcp-server"
      ],
      "env": {
        "GITHUB_PERSONAL_ACCESS_TOKEN": "ghp_xxxx"
      }
    }
  }
}
```

## Token Scopes

Required scopes depend on operations:

| Scope | Operations |
|-------|------------|
| `repo` | Full repository access (read/write) |
| `read:org` | Team and organization info |
| `gist` | Gist management |
| `read:discussion` | Discussion access |
| `workflow` | Actions workflow management |
| `security_events` | Code scanning alerts |

## Toolset Configuration

Enable specific toolsets via environment variable:

```json
{
  "env": {
    "GITHUB_PERSONAL_ACCESS_TOKEN": "ghp_xxxx",
    "GITHUB_TOOLSETS": "repos,issues,pull_requests,actions"
  }
}
```

Available toolsets: `context`, `repos`, `issues`, `pull_requests`, `users`, `actions`, `code_security`, `dependabot`, `discussions`, `gists`.

## Verification

After configuration, verify tools are available:

```
/tools mcp__github__GetMe
```

Expected output shows the tool definition with parameters.

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `mcp__github__*` tools not found | Restart Claude Code after config change |
| Authentication failed | Verify token has required scopes |
| Rate limiting | Check GitHub API rate limit status |
| Toolset not available | Add toolset to `GITHUB_TOOLSETS` env var |

## References

- [GitHub MCP Server](https://github.com/github/github-mcp-server) - Official repository
- [MCP Protocol](https://modelcontextprotocol.io/) - Protocol specification
- [Creating Tokens](https://github.com/settings/tokens) - GitHub token management
