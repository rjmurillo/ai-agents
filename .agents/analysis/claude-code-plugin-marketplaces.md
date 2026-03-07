# Claude Code Plugin Marketplaces: Comprehensive Analysis

> **Research Date**: 2026-02-07
> **Source**: https://code.claude.com/docs/en/plugin-marketplaces, https://code.claude.com/docs/en/plugins
> **Context**: Plugin distribution system for sharing Claude Code extensions across teams and communities

## Executive Summary

Claude Code's plugin marketplace system provides a standardized way to distribute collections of skills, agents, hooks, MCP servers, and LSP servers. Marketplaces use a declarative JSON catalog format, support multiple hosting options (GitHub, GitLab, local paths, URLs), and enable team-wide plugin management through repository configuration.

**Key Takeaways**:

1. Marketplaces are JSON catalogs that list plugins and their sources
2. Plugins are namespaced to prevent conflicts (`/plugin-name:skill`)
3. Distribution via Git repositories is recommended for relative path support
4. Organizations can enforce approved marketplaces via `strictKnownMarketplaces`
5. This project should evaluate creating an internal marketplace for skill distribution

---

## Core Concepts

### What is a Plugin?

A plugin is a directory containing:

- `.claude-plugin/plugin.json` - Manifest with name, description, version
- `commands/` - Slash command Markdown files
- `skills/` - Agent Skills with SKILL.md files
- `agents/` - Custom agent definitions
- `hooks/` - Event handlers in hooks.json
- `.mcp.json` - MCP server configurations
- `.lsp.json` - LSP server configurations

### What is a Marketplace?

A marketplace is a catalog file (`.claude-plugin/marketplace.json`) that:

- Lists available plugins with their sources
- Provides metadata (owner, description, versioning)
- Enables discovery and installation via `/plugin marketplace add`
- Supports automatic updates when hosted in Git repositories

### Plugin vs Standalone Configuration

| Approach | Skill Names | Best For |
|----------|-------------|----------|
| Standalone (`.claude/`) | `/hello` | Personal workflows, project-specific, quick experiments |
| Plugins | `/plugin-name:hello` | Team sharing, cross-project reuse, versioned releases |

---

## Marketplace Architecture

### Directory Structure

```text
my-marketplace/
├── .claude-plugin/
│   └── marketplace.json     # Catalog file
└── plugins/
    └── review-plugin/
        ├── .claude-plugin/
        │   └── plugin.json  # Plugin manifest
        └── skills/
            └── review/
                └── SKILL.md
```

### Marketplace Schema

```json
{
  "name": "company-tools",           // Required: kebab-case identifier
  "owner": {
    "name": "DevTools Team",         // Required: maintainer name
    "email": "devtools@example.com"  // Optional: contact email
  },
  "metadata": {
    "description": "Internal tooling plugins",
    "version": "1.0.0",
    "pluginRoot": "./plugins"        // Base path for relative sources
  },
  "plugins": [
    {
      "name": "code-formatter",
      "source": "./plugins/formatter",
      "description": "Automatic code formatting",
      "version": "2.1.0"
    }
  ]
}
```

### Plugin Sources

| Source Type | Example | Notes |
|-------------|---------|-------|
| Relative path | `"./plugins/my-plugin"` | Only works with Git-based marketplaces |
| GitHub | `{"source": "github", "repo": "owner/repo"}` | Supports ref and sha pinning |
| Git URL | `{"source": "url", "url": "https://gitlab.com/team/plugin.git"}` | Any Git host |

**Version Pinning**:

```json
{
  "source": "github",
  "repo": "owner/repo",
  "ref": "v2.0.0",
  "sha": "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0"
}
```

---

## Key Workflows

### Creating a Marketplace

1. Create directory structure with `.claude-plugin/marketplace.json`
2. Add plugins to `plugins/` subdirectory or reference external sources
3. Validate with `claude plugin validate .` or `/plugin validate .`
4. Host on GitHub, GitLab, or other Git service
5. Share URL with users

### Installing Plugins

```bash
# Add marketplace
/plugin marketplace add owner/repo
/plugin marketplace add https://gitlab.com/team/plugins.git
/plugin marketplace add ./local-marketplace

# Install plugin
/plugin install plugin-name@marketplace-name

# Update marketplace
/plugin marketplace update
```

### Team-Wide Configuration

Add to `.claude/settings.json` in repository:

```json
{
  "extraKnownMarketplaces": {
    "company-tools": {
      "source": {
        "source": "github",
        "repo": "your-org/claude-plugins"
      }
    }
  },
  "enabledPlugins": {
    "code-formatter@company-tools": true
  }
}
```

### Enterprise Restrictions

Use `strictKnownMarketplaces` in managed settings to restrict allowed marketplaces:

```json
{
  "strictKnownMarketplaces": [
    {"source": "github", "repo": "acme-corp/approved-plugins"},
    {"source": "hostPattern", "hostPattern": "^github\\.example\\.com$"}
  ]
}
```

| Value | Behavior |
|-------|----------|
| Undefined | No restrictions |
| Empty array `[]` | Complete lockdown |
| List of sources | Allowlist only |

---

## Plugin Components

### Skills

```yaml
---
description: Reviews code for best practices
disable-model-invocation: true
---

Review the code for:
- Potential bugs
- Security concerns
- Performance issues
```

Skills in plugins are namespaced: `/plugin-name:skill-name`

### Hooks

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [
          {
            "type": "command",
            "command": "${CLAUDE_PLUGIN_ROOT}/scripts/validate.sh"
          }
        ]
      }
    ]
  }
}
```

Use `${CLAUDE_PLUGIN_ROOT}` to reference files within the plugin installation directory.

### MCP Servers

```json
{
  "mcpServers": {
    "enterprise-db": {
      "command": "${CLAUDE_PLUGIN_ROOT}/servers/db-server",
      "args": ["--config", "${CLAUDE_PLUGIN_ROOT}/config.json"]
    }
  }
}
```

### LSP Servers

```json
{
  "go": {
    "command": "gopls",
    "args": ["serve"],
    "extensionToLanguage": {
      ".go": "go"
    }
  }
}
```

---

## Failure Modes and Anti-Patterns

### Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| Relative paths fail in URL marketplaces | URL download only gets marketplace.json | Use Git-based marketplace or external sources |
| Files not found after install | Plugins copied to cache; `../` paths break | Use symlinks or restructure directories |
| Authentication fails for private repos | Missing token for background updates | Set `GITHUB_TOKEN`, `GITLAB_TOKEN`, etc. |
| Reserved marketplace names | Using names like `anthropic-plugins` | Choose unique, non-official-sounding names |

### Reserved Names

The following marketplace names are reserved for Anthropic:

- `claude-code-marketplace`
- `claude-code-plugins`
- `claude-plugins-official`
- `anthropic-marketplace`
- `anthropic-plugins`
- `agent-skills`
- `life-sciences`

### Plugin Caching

Plugins are copied to a cache directory on install. This means:

- Files outside the plugin directory are not available
- Use symlinks (followed during copy) or restructure
- Reference plugin files via `${CLAUDE_PLUGIN_ROOT}`

---

## Project Applicability

### Current State

This project (`ai-agents`) has:

- ~50 skills in `.claude/skills/`
- Multiple hooks in `.claude/hooks/`
- GitHub skill scripts in `.claude/skills/github/`
- Memory skills in `.claude/skills/memory/`

### Integration Opportunities

| Opportunity | Priority | Effort | Benefit |
|-------------|----------|--------|---------|
| Convert skills to plugin format | High | Medium | Cross-project reuse, versioning |
| Create internal marketplace | High | Low | Centralized skill distribution |
| Package GitHub skills plugin | Medium | Low | Standalone GitHub operations package |
| Create hooks plugin | Medium | Medium | Shareable automation patterns |
| Publish to community | Low | High | Open source contribution |

### Migration Path

1. **Phase 1**: Create `.claude-plugin/` directory structure alongside existing `.claude/`
2. **Phase 2**: Create `marketplace.json` listing internal plugins
3. **Phase 3**: Test plugin installation workflow
4. **Phase 4**: Migrate high-value skills to plugin format
5. **Phase 5**: Evaluate community marketplace publication

### Considerations

- **Namespace Impact**: Plugin skills become `/ai-agents:skill` instead of `/skill`
- **Hook Migration**: Hooks must move to `hooks/hooks.json` format
- **Script Paths**: Use `${CLAUDE_PLUGIN_ROOT}` for script references
- **Breaking Changes**: Existing skill invocations would need updating

---

## Related Concepts

| Concept | Relationship |
|---------|--------------|
| Claude Code Skills | Skills are one component of plugins |
| MCP Servers | Plugins can bundle MCP server configurations |
| Claude Code Hooks | Plugins can define hooks in `hooks.json` |
| Agent System | Plugins can include custom agents |
| LSP Integration | Plugins can add language server support |

---

## References

- [Claude Code Plugin Marketplaces Documentation](https://code.claude.com/docs/en/plugin-marketplaces)
- [Create Plugins Guide](https://code.claude.com/docs/en/plugins)
- [Discover and Install Plugins](https://code.claude.com/docs/en/discover-plugins)
- [Plugins Reference (Technical Specification)](https://code.claude.com/docs/en/plugins-reference)
- [Awesome Claude Code Plugins (Community)](https://github.com/ccplugins/awesome-claude-code-plugins)
- [Anthropic Claude Code Plugins Blog](https://claude.com/blog/claude-code-plugins)

---

## Action Items

- [ ] Evaluate converting `.claude/skills/` to plugin format
- [ ] Create `.claude-plugin/marketplace.json` for internal distribution
- [ ] Document namespace changes in skill invocation
- [ ] Test plugin installation workflow with subset of skills
- [ ] Update SKILL-QUICK-REF.md if migration occurs

---

## Memory Cross-References

- `claude-code-skills-official-guidance` - Skill frontmatter standards
- `skills-documentation` - Documentation skill patterns
- `claude-code-hooks-opportunity-analysis` - Hook system analysis
- `claude-code-slash-commands` - Command system reference
