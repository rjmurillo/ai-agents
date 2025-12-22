# Claude Code Slash Commands - Complete Reference

> **Source**: https://code.claude.com/docs/en/slash-commands
> **Last Updated**: 2025-12-21
> **Purpose**: Authoritative reference for writing custom slash commands with high fidelity

---

## Overview

Slash commands are Markdown files that extend Claude Code with custom prompts. They support dynamic context injection, argument handling, and tool restrictions.

---

## File Locations

| Type | Location | Scope | Label in /help |
|------|----------|-------|----------------|
| **Project** | `.claude/commands/*.md` | Shared via repository | `(project)` |
| **Personal** | `~/.claude/commands/*.md` | All your projects | `(user)` |

**Precedence**: Project commands override personal commands with the same name.

---

## File Structure

```markdown
---
allowed-tools: Tool1, Tool2(pattern:*)
argument-hint: <required> [optional]
description: Brief description shown in /help
model: claude-3-5-sonnet-20241022
disable-model-invocation: false
---

# Command Title

Prompt content with $ARGUMENTS or $1, $2, etc.

Dynamic context: !`bash command`

File reference: @path/to/file.js
```

---

## YAML Frontmatter Fields

| Field | Type | Purpose | Default |
|-------|------|---------|---------|
| `allowed-tools` | string | Comma-separated list of tools command can use | Inherits from conversation |
| `argument-hint` | string | Expected arguments (shown in autocomplete) | None |
| `description` | string | Brief description for `/help` listing | First line of prompt |
| `model` | string | Specific model to use | Inherits from conversation |
| `disable-model-invocation` | boolean | Prevent SlashCommand tool from calling this | `false` |

### allowed-tools Syntax

```yaml
# Specific tools
allowed-tools: Read, Write, Glob, Grep

# Bash with wildcards
allowed-tools: Bash(git:*), Bash(npm:*)

# Bash with specific commands
allowed-tools: Bash(git add:*), Bash(git commit:*), Bash(git status:*)

# Combined
allowed-tools: Bash(git:*), Bash(gh:*), Task, Read, Write, Edit
```

### argument-hint Syntax

```yaml
# Required arguments in angle brackets
argument-hint: <pr-number>

# Optional arguments in square brackets
argument-hint: [message]

# Combined
argument-hint: <pr-number> [priority] [assignee]

# Multiple options with pipe
argument-hint: [tagId] | remove [tagId] | list
```

---

## Argument Handling

### All Arguments: `$ARGUMENTS`

Captures everything passed to the command as a single string:

```markdown
Fix issue #$ARGUMENTS following our coding standards
```

**Usage**: `/fix-issue 123 high-priority`
**Result**: `$ARGUMENTS` = `"123 high-priority"`

### Positional Arguments: `$1`, `$2`, `$3`, etc.

Access specific arguments by position:

```markdown
---
argument-hint: <pr-number> [priority] [assignee]
---

Review PR #$1 with priority $2 and assign to $3.
```

**Usage**: `/review-pr 456 high alice`
**Result**: `$1="456"`, `$2="high"`, `$3="alice"`

### Best Practice

- Use `$ARGUMENTS` for simple, single-value commands
- Use `$1`, `$2`, etc. when arguments are accessed in multiple locations
- Always include `argument-hint` in frontmatter for discoverability

---

## Dynamic Context: Bash Execution with `!` Prefix

Execute bash commands before the slash command runs. Output is included in context.

### Syntax

```markdown
- Current status: !`git status`
- Recent logs: !`git log --oneline -5`
```

### Requirements

1. MUST include `allowed-tools` with appropriate `Bash` patterns in frontmatter
2. MUST specify exact commands to allow (security)

### Complete Example

```markdown
---
allowed-tools: Bash(git add:*), Bash(git status:*), Bash(git commit:*), Bash(git log:*)
description: Create a git commit with context
---

## Context

- Status: !`git status`
- Diff: !`git diff HEAD`
- Branch: !`git branch --show-current`
- Recent: !`git log --oneline -10`

## Task

Create a conventional commit based on the above changes.
```

---

## File References: `@` Prefix

Include file contents directly in the command prompt:

```markdown
# Single file
Review the implementation in @src/utils/helpers.js

# Multiple files
Compare @src/old-version.js with @src/new-version.js

# Relative paths
Check @./package.json for dependencies
```

---

## Namespacing with Subdirectories

Organize related commands in subdirectories:

| File Path | Command | Label |
|-----------|---------|-------|
| `.claude/commands/frontend/component.md` | `/component` | `(project:frontend)` |
| `.claude/commands/backend/test.md` | `/test` | `(project:backend)` |
| `.claude/commands/git/commit.md` | `/commit` | `(project:git)` |

---

## SlashCommand Tool Integration

Claude can invoke custom slash commands programmatically via the SlashCommand tool.

### Requirements for Discoverability

1. MUST have `description` field in frontmatter
2. Command metadata visible up to character budget (default: 15,000 chars)
3. Can be disabled per-command with `disable-model-invocation: true`

### Permission Rules

```text
SlashCommand:/commit           # Exact match, no arguments
SlashCommand:/review-pr:*      # Prefix match, any arguments
SlashCommand                   # Deny all (in deny rules)
```

---

## Slash Commands vs Skills

| Aspect | Slash Commands | Skills |
|--------|----------------|--------|
| **Complexity** | Simple prompts | Complex capabilities |
| **Structure** | Single .md file | Directory with SKILL.md + resources |
| **Discovery** | Explicit (`/command`) | Automatic (context-based) |
| **Files** | One file only | Multiple files, scripts, templates |
| **Use Case** | Quick prompts, templates | Workflows with scripts/utilities |

### Use Slash Commands For

- Quick, frequently used prompts
- Simple prompt snippets with dynamic context
- Quick reminders or templates
- Commands with 1-3 simple arguments

### Use Skills For

- Complex workflows with multiple steps
- Capabilities requiring scripts/utilities
- Knowledge across multiple files
- Team workflow standardization

---

## Complete Examples

### Example 1: Simple PR Review

```markdown
---
allowed-tools: Bash(gh:*), Bash(git:*), Read, Grep
argument-hint: <pr-number>
description: Review a pull request
---

# PR Review

Review PR #$ARGUMENTS

## Context

- PR details: !`gh pr view $ARGUMENTS --json title,body,files`
- Current branch: !`git branch --show-current`

## Task

Analyze the PR and provide feedback on code quality, security, and best practices.
```

### Example 2: Commit with Context

```markdown
---
allowed-tools: Bash(git add:*), Bash(git status:*), Bash(git commit:*), Bash(git log:*)
argument-hint: [message]
description: Create conventional commit with git history context
---

## Git Context

- Status: !`git status`
- Diff: !`git diff HEAD`
- Branch: !`git branch --show-current`
- Recent: !`git log --oneline -5`

## Task

Create a git commit. If message provided: "$ARGUMENTS"
Otherwise, generate appropriate conventional commit message.
```

### Example 3: Multi-Argument Command

```markdown
---
allowed-tools: Bash(gh:*), Task
argument-hint: <pr-numbers> [--parallel] [--cleanup]
description: Process multiple PR review comments
---

# Batch PR Review

Process PR review comments for: $ARGUMENTS

## Context

- Repository: !`gh repo view --json nameWithOwner -q '.nameWithOwner'`
- Authenticated as: !`gh api user -q '.login'`

## Arguments

Parse: `$ARGUMENTS`
- PR_NUMBERS: Comma-separated (e.g., `53,141,143`) or `all-open`
- --parallel: Use git worktrees for parallel execution
- --cleanup: Clean up worktrees after completion (default: true)

## Workflow

1. Validate each PR exists and is open
2. For each PR, invoke pr-comment-responder
3. Generate summary of actions taken
```

### Example 4: File Comparison

```markdown
---
argument-hint: <file1> <file2>
description: Compare two files and suggest improvements
---

# File Comparison

Compare these files and suggest improvements:

## File 1
@$1

## File 2
@$2

## Task

Analyze differences, identify improvements, suggest refactoring.
```

---

## Anti-Patterns to Avoid

### 1. Missing Frontmatter

```markdown
# WRONG - No frontmatter
Fix issue $ARGUMENTS
```

```markdown
# CORRECT - Has frontmatter
---
description: Fix an issue
argument-hint: <issue-number>
---

Fix issue #$ARGUMENTS
```

### 2. Bash Without allowed-tools

```markdown
# WRONG - Bash commands without permission
---
description: Show git status
---

Status: !`git status`
```

```markdown
# CORRECT - Bash commands with permission
---
allowed-tools: Bash(git status:*)
description: Show git status
---

Status: !`git status`
```

### 3. Documentation-Style Instead of Prompt-Style

```markdown
# WRONG - Too much documentation, not a prompt
## Usage
/fix-issue <number>

## Arguments
| Arg | Description |
|-----|-------------|
| number | Issue number |

## Examples
/fix-issue 123
```

```markdown
# CORRECT - Concise prompt with context
---
argument-hint: <issue-number>
description: Fix a GitHub issue
---

Fix GitHub issue #$ARGUMENTS following our coding standards.

Issue context: !`gh issue view $ARGUMENTS --json title,body`
```

### 4. Overly Long Commands

If your slash command exceeds 200 lines, consider:
- Converting to a Skill instead
- Breaking into multiple smaller commands
- Moving reference documentation elsewhere

---

## Quick Reference Template

```markdown
---
allowed-tools: [tools needed]
argument-hint: <required> [optional]
description: Brief description for /help
---

# [Command Name]

[Prompt instruction with $ARGUMENTS or $1, $2]

## Context

- [Dynamic data]: !`[bash command]`
- [File reference]: @[path/to/file]

## Task

[Clear instruction for Claude]
```

---

## Related

- Skills: `.claude/skills/SKILL.md` for complex capabilities
- Built-in commands: `/help` to list all available
- MCP commands: `/mcp__<server>__<prompt>` for MCP server prompts
