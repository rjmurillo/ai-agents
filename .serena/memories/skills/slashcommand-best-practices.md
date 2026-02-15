# Slash Command Best Practices and Patterns

## Overview

Custom slash commands in Claude Code are Markdown files (`.md`) with YAML frontmatter that define reusable prompts with dynamic context injection, argument handling, and tool restrictions.

**Source**: Research from https://code.claude.com/docs/en/slash-commands and community best practices (2026-01-03)

---

## File Structure

| Scope | Location | Precedence | Label |
|-------|----------|------------|-------|
| Project | `.claude/commands/*.md` | High | `(project)` |
| Personal | `~/.claude/commands/*.md` | Low | `(user)` |

**Namespacing**: Use subdirectories to group commands:
- `.claude/commands/pr/review.md` → `/review` (shown as `project:pr`)
- `.claude/commands/git/commit.md` → `/commit` (shown as `project:git`)

---

## Frontmatter Schema

```yaml
---
allowed-tools: Bash(git:*), Bash(gh:*), Read, Write
argument-hint: <pr-number> [priority]
description: Review a pull request. Use when Claude needs to analyze PR changes or provide feedback.
model: claude-3-5-sonnet-20241022
disable-model-invocation: false
---
```

### Required Fields

- `description`: Trigger-based description (specify WHEN to use, not just WHAT it does)
- `argument-hint`: Expected arguments (if command uses arguments)

### Optional Fields

- `allowed-tools`: Tool permissions (REQUIRED if using bash `!` or other tools)
- `model`: Specific Claude model to use
- `disable-model-invocation`: Prevent SlashCommand tool from calling this

---

## Variable Substitution

### All Arguments: `$ARGUMENTS`

Captures all arguments as single string. Best for simple or variable-length arguments.

```markdown
Fix issue #$ARGUMENTS
```

Usage: `/fix-issue 123 high-priority` → `$ARGUMENTS` = `"123 high-priority"`

### Positional Arguments: `$1`, `$2`, `$3`

Access specific arguments by position. Best when arguments are used multiple times.

```markdown
Review PR #$1 with priority $2 and assign to $3
```

Usage: `/review-pr 456 high alice` → `$1="456"`, `$2="high"`, `$3="alice"`

---

## Dynamic Context Injection

### Bash Execution: `!` Prefix

Execute bash commands before command runs. Output included in context.

```markdown
## Context

- Current branch: !`git branch --show-current`
- Git status: !`git status --short`
- PR details: !`gh pr view $1 --json title,body`
```

**SECURITY REQUIREMENT**: MUST include `allowed-tools` with specific patterns:

```yaml
# GOOD - Specific commands
allowed-tools: Bash(git branch:*), Bash(git status:*), Bash(gh pr view:*)

# BAD - Overly permissive
allowed-tools: Bash(*:*)
```

### File References: `@` Prefix

Include file contents directly:

```markdown
Review the implementation in @src/utils/helpers.js

Compare @src/old-version.js with @src/new-version.js
```

---

## Extended Thinking Integration

Use `ultrathink` keyword for complex reasoning (allocates up to 31,999 tokens):

```markdown
ultrathink: Design the architecture for $ARGUMENTS.
Consider scalability, maintainability, performance, security, and cost.
```

**Use Extended Thinking For**:
- Complex architectural decisions
- Challenging bugs (multi-step debugging)
- Multi-step implementation planning
- Trade-off evaluation
- Edge case analysis

**Model Selection**:
- Haiku: Simple prompts, no extended thinking
- Sonnet: Standard operations, optional extended thinking
- Opus: Complex reasoning, use `ultrathink`

---

## Best Practices

### 1. Trigger-Based Descriptions

**Bad** (capability-only):
```yaml
description: GitHub PR operations
```

**Good** (trigger-based):
```yaml
description: GitHub PR operations. Use when Claude needs to review PRs, reply to comments, or merge pull requests.
```

### 2. Namespacing for Scale

Instead of flat naming:
```
post-new.md
post-preview.md
site-build.md
```

Use subdirectories:
```
posts/new.md        → /new (project:posts)
posts/preview.md    → /preview (project:posts)
site/build.md       → /build (project:site)
```

### 3. Graceful Defaults

Markdown should make sense without arguments:

```markdown
Create a new blog post titled "$ARGUMENTS".

If no title provided, generate a draft post with placeholder title.
```

### 4. Security Constraints

**ALWAYS** specify exact bash command patterns:

```yaml
# GOOD - Specific
allowed-tools: Bash(git add:*), Bash(git commit:*), Bash(git status:*)

# BAD - Too broad
allowed-tools: Bash(git:*)

# VERY BAD - Wildcard
allowed-tools: Bash(*:*)
```

---

## Anti-Patterns to Avoid

### 1. Missing Frontmatter

```markdown
# WRONG
Fix issue $ARGUMENTS
```

```markdown
# CORRECT
---
description: Fix an issue
argument-hint: <issue-number>
---

Fix issue #$ARGUMENTS
```

### 2. Documentation-Style Instead of Prompt-Style

```markdown
# WRONG - Too much documentation
## Usage
/fix-issue <number>

## Arguments
| Arg | Description |
```

```markdown
# CORRECT - Concise prompt
---
argument-hint: <issue-number>
description: Fix a GitHub issue
---

Fix GitHub issue #$ARGUMENTS following our coding standards.
Issue context: !`gh issue view $ARGUMENTS --json title,body`
```

### 3. Overly Long Commands

If command exceeds 200 lines:
- Convert to Skill instead
- Break into multiple smaller commands
- Move reference documentation elsewhere

---

## Slash Command vs Skill Decision

### Use Slash Command When

- ✅ Prompt fits in one file (<200 lines)
- ✅ No scripts or utilities required
- ✅ User explicitly invokes command
- ✅ 1-3 simple arguments
- ✅ Primarily prompt text with dynamic context

### Use Skill When

- ✅ Multiple files needed (scripts, templates)
- ✅ Automatic context-based invocation desired
- ✅ Complex multi-step workflow
- ✅ PowerShell/.psm1 modules required

---

## Quality Gates Checklist

- [ ] Frontmatter complete (`description`, `argument-hint` if uses args)
- [ ] Trigger-based description (includes "Use when")
- [ ] Argument handling matches `argument-hint`
- [ ] Bash commands have `allowed-tools` permission
- [ ] No overly permissive wildcards in `allowed-tools`
- [ ] Length <200 lines
- [ ] Passes `markdownlint-cli2`

---

## Integration with ai-agents Project

### Governance Constraints

Per `.agents/governance/PROJECT-CONSTRAINTS.md`:

- MUST include frontmatter with `description` and `argument-hint`
- MUST use trigger-based descriptions (per `creator-001`)
- MUST specify `allowed-tools` for bash commands
- SHOULD use `ultrathink` for complex reasoning commands

### PowerShell Validation Script

`.claude/skills/slashcommandcreator/scripts/Validate-SlashCommand.ps1`:

```powershell
# Check YAML frontmatter parses
# Validate required fields present
# Check trigger-based description pattern
# Validate bash commands have allowed-tools
# Check for overly permissive wildcards
# Lint with markdownlint-cli2
```

### Pre-Commit Hook

`.claude/hooks/pre-commit-slash-commands.ps1`:

```powershell
$stagedCommands = git diff --cached --name-only --diff-filter=ACM | 
    Where-Object { $_ -like "*.claude/commands/*.md" }

foreach ($command in $stagedCommands) {
    & scripts/Validate-SlashCommand.ps1 -CommandPath $command
}
```

---

## Related

- **Skill**: `.claude/skills/slashcommandcreator/` - Systematic slash command creation
- **Specification**: `.agents/planning/slashcommandcreator-skill-spec.md`
- **Memory**: [creator-001-frontmatter-trigger-specification](creator-001-frontmatter-trigger-specification.md) - Trigger-based descriptions
- **Analysis**: `.agents/analysis/custom-slash-commands-research.md` - Complete research

---

## References

- Official Documentation: https://code.claude.com/docs/en/slash-commands
- Extended Thinking: https://code.claude.com/docs/en/common-workflows#use-extended-thinking-thinking-mode
- Community: https://github.com/wshobson/commands, https://github.com/qdhenry/Claude-Command-Suite
