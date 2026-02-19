# Claude Code Plugin Marketplaces

> **Research Date**: 2026-02-07
> **Source**: https://code.claude.com/docs/en/plugin-marketplaces
> **Full Analysis**: `.agents/analysis/claude-code-plugin-marketplaces.md`

## Key Concepts

**Marketplace**: JSON catalog (`.claude-plugin/marketplace.json`) listing plugins with sources for distribution.

**Plugin**: Directory with .claude-plugin/plugin.json (removed) manifest containing skills, agents, hooks, MCP servers, or LSP servers.

**Namespacing**: Plugin skills are invoked as `/plugin-name:skill` to prevent conflicts.

## Marketplace Schema

```json
{
  "name": "company-tools",
  "owner": {"name": "Team", "email": "team@example.com"},
  "plugins": [
    {"name": "my-plugin", "source": "./plugins/my-plugin"}
  ]
}
```

## Plugin Sources

| Type | Example |
|------|---------|
| Relative | `"./plugins/formatter"` (Git marketplaces only) |
| GitHub | `{"source": "github", "repo": "owner/repo", "ref": "v1.0"}` |
| Git URL | `{"source": "url", "url": "https://gitlab.com/team/plugin.git"}` |

## Team Configuration

In `.claude/settings.json`:

```json
{
  "extraKnownMarketplaces": {
    "company-tools": {"source": {"source": "github", "repo": "org/plugins"}}
  },
  "enabledPlugins": {"plugin@marketplace": true}
}
```

## Key Commands

- `/plugin marketplace add owner/repo` - Add marketplace
- `/plugin install plugin@marketplace` - Install plugin
- `/plugin validate .` - Validate marketplace

## Project Applicability

- Consider creating internal marketplace for `.claude/skills/`
- Skills would become `/ai-agents:skill-name`
- Use `${CLAUDE_PLUGIN_ROOT}` for script paths in plugins

## Related Memories

- [claude-code-skills-official-guidance](claude-code-skills-official-guidance.md)
- [claude-code-hooks-opportunity-analysis](claude-code-hooks-opportunity-analysis.md)
- [claude-code-slash-commands](claude-code-slash-commands.md)
