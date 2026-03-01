# Skill Authoring Guide

This guide covers how to create Claude Code skills with correct YAML frontmatter, model selection, and file structure.

Based on the analysis in `.agents/analysis/claude-code-skill-frontmatter-2026.md`.

## Frontmatter Schema

Every skill lives in a `SKILL.md` file inside a directory under `.claude/skills/`. The file starts with YAML frontmatter.

### Required Fields

| Field | Type | Constraints | Purpose |
|-------|------|-------------|---------|
| `name` | string | Lowercase, alphanumeric + hyphens, max 64 chars | Skill identifier. Must match directory name. |
| `description` | string | Max 1024 characters | Primary trigger mechanism. Claude uses this to decide when to activate the skill. |

### Optional Fields

| Field | Type | Constraints | Purpose |
|-------|------|-------------|---------|
| `model` | string | Valid model alias or dated ID | Which Claude model executes the skill. |
| `allowed-tools` | string | Comma-separated tool names | Restricts which tools Claude can use during execution. |
| `version` | string | Semantic versioning (e.g., `1.0.0`) | Tracks skill evolution. Not validated by Claude Code. |
| `license` | string | SPDX identifier (e.g., `MIT`) | Legal licensing. Not validated by Claude Code. |
| `metadata` | object | Custom key-value pairs | Domain-specific configuration. |

### Minimum Valid Frontmatter

```yaml
---
name: my-skill
description: Does something useful when you need it
---
```

### Full Frontmatter

```yaml
---
name: advanced-skill
version: 2.0.0
model: claude-opus-4-5
license: MIT
description: Complex orchestration skill requiring maximum reasoning capability
allowed-tools: Bash(pwsh:*), Read, Write, Grep
metadata:
  domains: [architecture, planning]
  type: orchestrator
  complexity: advanced
---
```

## Validation Rules

**YAML syntax:**

- Frontmatter MUST start with `---` on line 1. No blank lines before it.
- Frontmatter MUST end with `---` before Markdown content.
- Use spaces for indentation. Tabs are not allowed.

**Field validation:**

- `name`: Only lowercase letters, numbers, hyphens. Regex: `^[a-z0-9-]{1,64}$`
- `description`: Non-empty, max 1024 characters, no XML tags.
- `model`: Must be a valid model identifier (see Model Selection below).
- `allowed-tools`: Tool names must match available Claude Code tools.

**File structure:**

- `SKILL.md` is the only required file in a skill directory.
- Keep `SKILL.md` under 500 lines for optimal performance.
- Use progressive disclosure for longer skills (see File Structure below).

## Model Selection

Use model aliases in skills. Aliases auto-update when Anthropic releases new snapshots.

### Model Tiers

| Tier | Alias | Cost (Input/Output per MTok) | Use When |
|------|-------|------------------------------|----------|
| Opus | `claude-opus-4-5` | $5 / $25 | Deep reasoning, multi-agent coordination, architectural decisions |
| Sonnet | `claude-sonnet-4-5` | $3 / $15 | Standard coding workflows, documentation, security detection |
| Haiku | `claude-haiku-4-5` | $1 / $5 | Simple pattern matching, format fixes, fast hooks |

### Decision Matrix

| Characteristic | Haiku | Sonnet | Opus |
|----------------|-------|--------|------|
| Reasoning depth | Simple rules | Standard logic | Complex multi-step |
| Orchestration | None | Single agent | Multi-agent coordination |
| Latency sensitivity | <1s critical | <5s acceptable | <30s acceptable |
| Frequency | Very high (hooks) | High (workflows) | Moderate (orchestration) |
| Error impact | Low (cosmetic) | Medium (workflow) | High (architectural) |

### When to Include the Model Field

Include `model` when:

- The skill requires specific capabilities (extended thinking, deep reasoning).
- The skill orchestrates subagents and needs consistency.
- The skill has performance or cost requirements.
- The skill is part of an automated workflow.

Omit `model` when:

- The skill should adapt to the user's default model.
- Model selection is a user preference.
- The skill is purely instructional.

### Alias vs. Dated ID

Use aliases (`claude-opus-4-5`) for skills. Dated snapshots (`claude-opus-4-5-20251101`) are for production API integrations that need reproducible behavior.

## Description Best Practices

The `description` field is the primary triggering mechanism. Include:

1. **What**: Clear statement of skill functionality.
2. **When**: Explicit trigger conditions.
3. **Keywords**: Terms users would naturally say.

```yaml
# Bad: too generic
description: Helps with testing

# Good: specific with triggers
description: Execute Pester tests with coverage analysis. Use when asked to "run tests", "check coverage", or "verify test suite".

# Bad: missing triggers
description: Analyzes code quality and suggests improvements

# Good: includes natural language triggers
description: Static analysis with Roslyn analyzers. Use for "check code quality", "run analyzers", "find code smells", or "enforce style guidelines".
```

## Allowed-Tools Configuration

Use `allowed-tools` to enforce least privilege.

```yaml
# Read-only analysis
allowed-tools: Read, Grep, Glob

# GitHub operations
allowed-tools: Bash(gh:*), Bash(pwsh:*), Read, Write
```

**Tool name patterns:**

- Exact tool: `Read`, `Write`, `Edit`
- Command prefix: `Bash(pwsh:*)`, `Bash(git:*)`
- Multiple: `Read, Write, Grep, Glob`

## File Structure

For skills under 500 lines, a single `SKILL.md` is sufficient.

For larger skills, use progressive disclosure:

```text
.claude/skills/my-skill/
  SKILL.md              # Essential info only (< 500 lines)
  references/
    workflow.md          # Detailed workflow diagrams
    examples.md          # Comprehensive examples
    api-reference.md     # Complete API documentation
  scripts/
    helper.py            # Automation scripts
```

`SKILL.md` should link to reference docs but not embed them.

## Working Examples

### Haiku: Simple Pattern Matching

```yaml
---
name: fix-markdown-fences
description: "Repair malformed markdown code fence closings. Use when markdown files have closing fences with language identifiers or when generating markdown with code blocks to ensure proper fence closure."
license: MIT
model: claude-haiku-4-5
---
```

### Sonnet: Standard Workflow

```yaml
---
name: doc-sync
description: Synchronizes CLAUDE.md navigation indexes and README.md architecture docs across a repository. Use when asked to "sync docs", "update CLAUDE.md files", "ensure documentation is in sync", or when documentation maintenance is needed after code changes.
license: MIT
model: claude-sonnet-4-5
---
```

### Opus: Multi-Agent Orchestration

```yaml
---
name: analyze
version: 1.0.0
model: claude-opus-4-5
description: Analyze codebase architecture, security posture, or code quality through guided multi-step investigation. Use when performing architecture reviews, security assessments, quality evaluations, or deep technical investigations. Produces prioritized findings with evidence.
license: MIT
---
```

## Frontmatter Checklist

Before committing a new skill, verify:

- [ ] Frontmatter starts with `---` on line 1 (no blank lines before)
- [ ] `name` field: lowercase, alphanumeric + hyphens, < 64 chars
- [ ] `description` field: includes trigger keywords, < 1024 chars
- [ ] `model` field (if present): valid alias or dated ID
- [ ] `allowed-tools` (if present): comma-separated valid tool names
- [ ] Frontmatter ends with `---` before Markdown content
- [ ] YAML uses spaces for indentation (not tabs)
- [ ] SKILL.md under 500 lines (use progressive disclosure if larger)
- [ ] Pre-commit validation passes (`scripts/Validate-SkillFrontmatter.ps1`)

## Troubleshooting

### 404 Not Found Error

**Symptom**: `404 not_found_error: model 'sonnet-4.5' not found`

**Fix**: Use canonical identifier, not descriptive name.

```yaml
# Wrong
model: sonnet-4.5

# Correct
model: claude-sonnet-4-5
```

### Skill Not Triggering

**Cause**: Description lacks natural language trigger keywords.

**Fix**: Add explicit trigger phrases that match how users ask for the skill.

### Platform Mismatch

**Symptom**: Skill works in Claude Code but fails on Bedrock/Vertex.

**Cause**: Aliases are Anthropic API only. Use platform-specific identifiers or document requirements in metadata.

## References

- [Agent Skills, Claude Code Docs](https://code.claude.com/docs/en/skills)
- [Models overview, Claude Docs](https://platform.claude.com/docs/en/about-claude/models/overview)
- [Skill authoring best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)
- Source analysis: `.agents/analysis/claude-code-skill-frontmatter-2026.md`
