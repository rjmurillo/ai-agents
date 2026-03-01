# Claude Code Plugin File Distribution System

## Overview

When a plugin is installed via `claude plugin install`, Claude Code **copies the entire plugin directory** to `~/.claude/plugins/cache/`, not an in-place reference. This is critical for understanding issue #1352.

## Key Mechanisms

### 1. CLAUDE_PLUGIN_ROOT Environment Variable

Resolves to: `~/.claude/plugins/cache/[plugin-namespace]/[plugin-name]/`

**Works in:**
- Hook configurations (hooks.json, inline plugin.json)
- MCP server configurations (.mcp.json)
- Environment variable expansions in commands

**Does NOT work in:**
- Command markdown files (known bug: [Issue #9354](https://github.com/anthropics/claude-code/issues/9354))
- SessionStart hooks (not populated at that lifecycle: [Issue #27145](https://github.com/anthropics/claude-code/issues/27145))

### 2. Plugin Source Distribution

The `marketplace.json` specifies which source directory gets copied:
```json
{
  "plugins": [
    {
      "name": "claude-agents",
      "source": "./src/claude"
    }
  ]
}
```

Only `./src/claude` is copied to plugin cache. Sibling directories like `./.claude/skills` are NOT distributed.

### 3. Skill Path Resolution

Skills reference scripts using paths relative to the **consumer repo**, not the plugin:
- Skill markdown references: `.claude/skills/github/scripts/pr/Get-PRContext.ps1`
- Resolves in consumer repo: `/path/to/consumer/repo/.claude/skills/github/scripts/pr/Get-PRContext.ps1`
- Plugin cache path: NOT used for this relative reference

## Issue #1352 Root Cause

1. `marketplace.json` specifies only `src/claude/` as source
2. Scripts in `.claude/skills/github/scripts/pr/` are NOT in source
3. Downstream repos receive agents from plugin cache
4. Agents/skills reference `.claude/skills/` in consumer repo
5. Consumer repo lacks `.claude/skills/` directory
6. Script execution fails

## Solution Paths

### Option A: Include scripts in plugin source
Move scripts into distributed directory:
```
src/claude/
├── [agents].md
├── skills/
│   └── github/
│       └── scripts/
│           └── pr/
│               ├── Get-PRContext.ps1
```

### Option B: Use CLAUDE_PLUGIN_ROOT for plugin-internal references
Only viable in hook configurations, not skill markdown.

### Option C: Update marketplace.json source path
Include subdirectories needed for skills:
```json
{
  "plugins": [
    {
      "name": "claude-agents",
      "source": "./src/claude"
    },
    {
      "name": "claude-skills-distribution",
      "source": "./.claude/skills"
    }
  ]
}
```

## Documentation References

- [Claude Code Plugins Reference](https://code.claude.com/docs/en/plugins-reference)
- [Plugin Installation Scopes](https://code.claude.com/docs/en/plugins-reference#plugin-installation-scopes)
- [Environment Variables](https://code.claude.com/docs/en/plugins-reference#environment-variables)
- GitHub Issues: #9354 (CLAUDE_PLUGIN_ROOT in commands), #27145 (SessionStart hooks)

## Related

- [claude-code-agent-teams](claude-code-agent-teams.md)
- [claude-code-hooks-opportunity-analysis](claude-code-hooks-opportunity-analysis.md)
- [claude-code-plugin-marketplaces](claude-code-plugin-marketplaces.md)
- [claude-code-skill-frontmatter-standards](claude-code-skill-frontmatter-standards.md)
- [claude-code-skills-official-guidance](claude-code-skills-official-guidance.md)
