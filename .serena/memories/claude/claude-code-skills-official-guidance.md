# Claude Code Skills: Official Guidance Summary

> **Source**: Anthropic documentation, engineering blog, official skills repository
> **Date**: 2026-01-04
> **Context**: Research session 308

## Required Frontmatter Fields

Only two fields are required:
1. `name`: lowercase, numbers, hyphens only, max 64 chars
2. `description`: max 1024 chars, primary triggering mechanism

## Optional Frontmatter Fields

- `allowed-tools`: Comma-separated tool names or patterns for least privilege
- `model`: Model ID or family alias (e.g., `claude-opus-4-5`)

## NOT in Official Spec

These fields are NOT recognized by Claude Code (project uses them but Claude ignores):
- `version`
- `license`
- `metadata` block

## Progressive Disclosure Pattern

Three levels of loading:
1. **Level 1**: Name + description loaded at startup into system prompt
2. **Level 2**: Complete SKILL.md body loaded when skill is relevant
3. **Level 3+**: Bundled files (scripts, references) loaded on-demand

Keep SKILL.md under 500 lines using references.

## Skill Activation Flow

1. Claude detects user intent matching skill description
2. Calls Skill tool with command name
3. System returns base path + SKILL.md body
4. Claude executes scripts relative to base path

## Description Best Practices

Answer two questions:
1. What does it do? (capability)
2. When should Claude use it? (trigger context)

Include keywords users would naturally mention.

**Good**: "Execute GitHub operations (PRs, issues, labels). Use when working with pull requests or review comments."

**Bad**: "Helps with GitHub things."

## Tool Restrictions Pattern

```yaml
# Read-only
allowed-tools: Read, Grep, Glob

# PowerShell execution
allowed-tools: Bash(pwsh:*), Read, Write

# Specific commands only
allowed-tools: Bash(gh api:*), Bash(git:*)
```

## Project Alignment

The ai-agents project is 90% aligned with official patterns:
- Progressive disclosure via references/ directories
- Trigger-based descriptions
- PowerShell script bundling

Gaps:
- Some skills missing `allowed-tools`
- Non-standard frontmatter fields present

## Related

- Analysis: `.agents/analysis/building-skills-for-claude-code.md`
- Existing memory: [claude-code-skill-frontmatter-standards](claude-code-skill-frontmatter-standards.md)
- [claude-code-hooks-opportunity-analysis](claude-code-hooks-opportunity-analysis.md)
- [claude-code-slash-commands](claude-code-slash-commands.md)
- [claude-flow-research-2025-12-20](claude-flow-research-2025-12-20.md)
- [claude-md-anthropic-best-practices](claude-md-anthropic-best-practices.md)
