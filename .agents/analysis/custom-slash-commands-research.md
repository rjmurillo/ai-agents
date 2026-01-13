# Custom Slash Commands: Comprehensive Research and Integration Analysis

**Research Date**: 2026-01-03
**Purpose**: Comprehensive analysis of Claude Code custom slash commands for ai-agents project integration
**Sources**: Official Claude Code documentation, community best practices, existing project patterns

---

## Executive Summary

Custom slash commands in Claude Code provide a mechanism for defining reusable prompts as Markdown files with dynamic context injection, argument handling, and tool restrictions. This research identifies patterns for creating high-quality slash commands and proposes a `slashcommandcreator` skill modeled after the `skillcreator` framework to systematize slash command development in the ai-agents project.

**Key Findings**:

1. **Slash commands complement skills**: Commands handle simple, frequent prompts (one file); skills handle complex workflows (multiple files, scripts)
2. **Frontmatter-driven architecture**: YAML frontmatter controls tool permissions, argument hints, model selection, and discoverability
3. **Dynamic context injection**: Bash command execution (`!`) and file references (`@`) enable context-aware prompts
4. **Extended thinking integration**: `ultrathink` keyword activates deep reasoning (up to 31,999 tokens)
5. **Community maturity**: Production repositories demonstrate patterns for organization, naming, and reusability

**Recommendations**:

1. Create `slashcommandcreator` skill using skillcreator framework principles
2. Establish slash command quality gates (frontmatter validation, argument hints, description requirements)
3. Migrate simple prompt-style skills to slash commands
4. Document slash command vs skill decision criteria

---

## 1. Slash Command Architecture

### 1.1 File Structure

Custom slash commands are Markdown files organized by scope:

| Scope | Location | Precedence | Label in `/help` |
|-------|----------|------------|------------------|
| **Project** | `.claude/commands/*.md` | High | `(project)` |
| **Personal** | `~/.claude/commands/*.md` | Low | `(user)` |

**Priority Rule**: Project commands override personal commands with the same name.

**Namespacing**: Subdirectories create namespaces:
- `.claude/commands/pr/review.md` → `/review` (shown as `project:pr`)
- `.claude/commands/git/commit.md` → `/commit` (shown as `project:git`)

### 1.2 YAML Frontmatter Schema

```yaml
---
allowed-tools: Tool1, Tool2(pattern:*)
argument-hint: <required> [optional]
description: Brief description shown in /help
model: claude-3-5-sonnet-20241022
disable-model-invocation: false
---
```

| Field | Type | Purpose | Default |
|-------|------|---------|---------|
| `allowed-tools` | string | Comma-separated list of allowed tools | Inherits from conversation |
| `argument-hint` | string | Expected arguments (shown in autocomplete) | None |
| `description` | string | Brief description for `/help` and SlashCommand tool | First line of prompt |
| `model` | string | Specific model to use | Inherits from conversation |
| `disable-model-invocation` | boolean | Prevent SlashCommand tool from calling this | `false` |

**Tool Permission Syntax**:

```yaml
# Specific tools
allowed-tools: Read, Write, Glob, Grep

# Bash with wildcards
allowed-tools: Bash(git:*), Bash(npm:*)

# Bash with specific commands (security constraint)
allowed-tools: Bash(git add:*), Bash(git commit:*), Bash(git status:*)

# Combined
allowed-tools: Bash(git:*), Bash(gh:*), Task, Read, Write, Edit
```

**Argument Hint Syntax**:

```yaml
# Required arguments in angle brackets
argument-hint: <pr-number>

# Optional arguments in square brackets
argument-hint: [message]

# Combined
argument-hint: <pr-number> [priority] [assignee]

# Multiple options with pipe
argument-hint: add [tagId] | remove [tagId] | list
```

---

## 2. Variable Substitution Patterns

### 2.1 All Arguments: `$ARGUMENTS`

Captures all arguments passed to the command as a single string.

**Example**:

```markdown
---
argument-hint: <issue-number> [priority]
description: Fix a GitHub issue
---

Fix issue #$ARGUMENTS following our coding standards.
```

**Usage**: `/fix-issue 123 high-priority`
**Result**: `$ARGUMENTS` = `"123 high-priority"`

**Best for**: Simple commands where arguments are used once, commands with variable-length arguments.

### 2.2 Positional Arguments: `$1`, `$2`, `$3`, etc.

Access specific arguments by position (similar to shell scripts).

**Example**:

```markdown
---
argument-hint: <pr-number> [priority] [assignee]
description: Review pull request with context
---

Review PR #$1 with priority $2 and assign to $3.

Context:
- PR details: !`gh pr view $1 --json title,body,files`
```

**Usage**: `/review-pr 456 high alice`
**Result**: `$1="456"`, `$2="high"`, `3="alice"`

**Best for**: Commands where arguments are accessed in multiple locations, commands with structured parameter roles.

---

## 3. Dynamic Context Injection

### 3.1 Bash Command Execution: `!` Prefix

Execute bash commands before the slash command runs. Output is included in context.

**Syntax**:

```markdown
- Current status: !`git status`
- Recent logs: !`git log --oneline -5`
```

**Security Requirements**:

1. MUST include `allowed-tools` with appropriate `Bash` patterns in frontmatter
2. MUST specify exact commands to allow (use wildcards judiciously)

**Complete Example**:

```markdown
---
allowed-tools: Bash(git add:*), Bash(git status:*), Bash(git commit:*), Bash(git log:*)
description: Create a conventional commit with git history context
---

## Git Context

- Status: !`git status`
- Diff: !`git diff HEAD`
- Branch: !`git branch --show-current`
- Recent: !`git log --oneline -10`

## Task

Create a conventional commit based on the above changes.
```

**Anti-Pattern**:

```markdown
# WRONG - Bash commands without allowed-tools permission
---
description: Show git status
---

Status: !`git status`
```

### 3.2 File References: `@` Prefix

Include file contents directly in the command prompt.

**Examples**:

```markdown
# Single file
Review the implementation in @src/utils/helpers.js

# Multiple files
Compare @src/old-version.js with @src/new-version.js

# Relative paths
Check @./package.json for dependencies
```

**Use Cases**:
- Code review commands
- File comparison commands
- Configuration validation commands

---

## 4. Extended Thinking Integration

### 4.1 Triggering Extended Thinking

Extended thinking mode allocates up to 31,999 tokens for deep reasoning before generating output.

**Methods**:

1. **Global Configuration**: `/config` → `alwaysThinkingEnabled` in `~/.claude/settings.json`
2. **Environment Variable**: `export MAX_THINKING_TOKENS=1024`
3. **Per-Request Keyword**: Include `ultrathink` in message

**Keyword Activation**:

```markdown
---
description: Design architecture with deep reasoning
---

ultrathink: Design the architecture for $ARGUMENTS.
Consider scalability, maintainability, performance, security, and cost implications.
Analyze trade-offs between approaches.
```

**Important**: `ultrathink` keyword:
- Only works when `MAX_THINKING_TOKENS` is NOT set
- Semantically signals Claude to reason more thoroughly
- Allocates up to 31,999 tokens for reasoning

### 4.2 When to Use Extended Thinking

**Use Extended Thinking For**:
- Complex architectural decisions
- Challenging bugs with multi-step debugging
- Multi-step implementation planning (edits across many files)
- Evaluating trade-offs between approaches
- Edge case analysis

**Use Regular Mode For**:
- Simple questions or quick lookups
- Fast responses needed
- Straightforward code changes
- Code exploration (use Plan Mode instead)

### 4.3 Performance Implications

- **Cost**: You are charged for ALL thinking tokens used
- **Benefits**: More solution approaches explored, thorough edge case analysis, self-correction
- **Token Budget**: Configure via `MAX_THINKING_TOKENS` environment variable

**Example Configuration**:

```json
// ~/.claude/settings.json
{
  "thinking": {
    "alwaysThinkingEnabled": true,
    "defaultTokenBudget": 16000
  }
}
```

---

## 5. SlashCommand Tool Integration

### 5.1 Programmatic Invocation

Claude can invoke custom slash commands programmatically via the `SlashCommand` tool.

**Requirements for Discoverability**:

1. MUST have `description` field in frontmatter
2. Command metadata visible up to character budget (default: 15,000 chars)
3. Can be disabled per-command with `disable-model-invocation: true`

**Permission Rules**:

```text
SlashCommand:/commit           # Exact match, no arguments
SlashCommand:/review-pr:*      # Prefix match, any arguments
SlashCommand                   # Deny all (in deny rules)
```

**Design Implication**: Commands with good `description` frontmatter are more likely to be invoked automatically by Claude when context matches.

---

## 6. Slash Commands vs Skills

### 6.1 Decision Matrix

| Aspect | Slash Commands | Skills |
|--------|----------------|--------|
| **Complexity** | Simple prompts | Complex capabilities |
| **Structure** | Single .md file | Directory with SKILL.md + resources |
| **Discovery** | Explicit (`/command`) | Automatic (context-based) |
| **Files** | One file only | Multiple files, scripts, templates |
| **Arguments** | `$ARGUMENTS`, `$1`, `$2`, etc. | Script parameters |
| **Context** | Bash `!` and file `@` injection | Full script logic |
| **Tool Restrictions** | Frontmatter `allowed-tools` | No restrictions |
| **Version Control** | Markdown file | Directory structure |

### 6.2 Use Slash Commands For

- Quick, frequently used prompts that fit in one file
- Simple prompt snippets with dynamic context
- Quick reminders or templates
- Commands with 1-3 simple arguments
- Standardizing common queries across team

### 6.3 Use Skills For

- Complex workflows with multiple steps
- Capabilities requiring scripts/utilities
- Knowledge across multiple files
- Team workflow standardization with complex logic
- Multi-file edits or orchestration

---

## 7. Best Practices from Community and Documentation

### 7.1 Organization Patterns

**Namespacing Strategy** (from cloudartisan.com case study):

Instead of flat naming:
```
.claude/commands/post-new.md
.claude/commands/post-preview.md
.claude/commands/site-build.md
```

Use subdirectory structure:
```
.claude/commands/posts/new.md        → /new (project:posts)
.claude/commands/posts/preview.md    → /preview (project:posts)
.claude/commands/site/build.md       → /build (project:site)
```

**Benefits**:
- Scales better as command count grows
- Logical grouping by domain
- Reduced naming collisions
- Clearer `/help` output

### 7.2 Argument Handling

**Flexible Argument Design**:

Markdown should "still make sense" when arguments aren't supplied, allowing graceful defaults.

**Example**:

```markdown
---
argument-hint: [title]
description: Create a new blog post
---

Create a new blog post titled "$ARGUMENTS".

If no title provided, generate a draft post with placeholder title.
```

### 7.3 Documentation and Discoverability

**Command Catalog Pattern**:

Create a `/project:view_commands` helper listing all available commands:

```markdown
---
description: List all custom slash commands
---

List all custom slash commands in this project with their descriptions and argument hints.
```

**Why**: Critical for remembering command names after context-switching.

### 7.4 Version Control Integration

Store commands as Markdown files in Git:
- Enables rollback capability
- Provides change history
- Shares commands with team (anyone who clones the repo gets all commands)

### 7.5 Anti-Patterns to Avoid

**1. Missing Frontmatter**

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

**2. Overly Specific Commands**

Instead of separate commands for each task, combine related operations into parametrized workflows.

**Bad**:
```
/pr-review-high
/pr-review-medium
/pr-review-low
```

**Good**:
```
/pr-review <number> [priority]
```

**3. Documentation-Style Instead of Prompt-Style**

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

**4. Overly Long Commands**

If your slash command exceeds 200 lines, consider:
- Converting to a Skill instead
- Breaking into multiple smaller commands
- Moving reference documentation elsewhere

---

## 8. Analysis of ai-agents Project Current Commands

### 8.1 Existing Commands Inventory

Current commands in `.claude/commands/`:

| Command | Frontmatter | Dynamic Context | Argument Handling | Extended Thinking |
|---------|-------------|-----------------|-------------------|-------------------|
| `memory-list.md` | ✅ Yes | ❌ No | ❌ No | ❌ No |
| `memory-save.md` | ✅ Yes | ❌ No | ✅ `$ARGUMENTS` | ❌ No |
| `memory-explore.md` | ✅ Yes | ❌ No | ✅ `$ARGUMENTS` | ❌ No |
| `context_gather.md` | ✅ Yes | ❌ No | ✅ Placeholder | ❌ No |
| `memory-search.md` | ✅ Yes | ❌ No | ✅ `$ARGUMENTS` | ❌ No |
| `context-hub-setup.md` | ❌ No | ❌ No | ❌ No | ❌ No |
| `research.md` | ❌ No | ❌ No | ❌ Structured input | ❌ No |
| `pr-review.md` | ✅ Yes | ✅ Yes | ✅ Complex | ❌ No |
| `memory-documentary.md` | ✅ Yes | ❌ No | ✅ `$ARGUMENTS` | ❌ No |

### 8.2 Quality Analysis

**Strengths**:
- Most commands have frontmatter with `description`
- `pr-review.md` demonstrates advanced patterns (dynamic context with `!` prefix, multi-argument handling)
- Commands follow trigger-based description pattern (per `creator-001-frontmatter-trigger-specification`)

**Gaps**:
- No extended thinking integration (no `ultrathink` usage)
- `context-hub-setup.md` and `research.md` lack frontmatter
- `research.md` uses structured input format instead of standard argument handling
- No slash command quality gate or validation

### 8.3 Improvement Opportunities

1. **Add Extended Thinking**: Architectural/research commands (`research`, `memory-documentary`, `pr-review`) should use `ultrathink`
2. **Standardize Frontmatter**: All commands should have complete frontmatter
3. **Argument Handling**: `research.md` should migrate to standard `$ARGUMENTS` pattern
4. **Dynamic Context**: Memory commands could benefit from `!` prefix for current project context
5. **Tool Restrictions**: Commands should specify `allowed-tools` for security

**Example Improvement for `research.md`**:

```markdown
---
allowed-tools: WebFetch, WebSearch, mcp__forgetful__*, mcp__serena__*, Read, Write, Glob, Grep
argument-hint: <topic> [context] [--urls=url1,url2]
description: Research external topics and incorporate learnings. Use when investigating new concepts, evaluating tools, or documenting architectural decisions.
model: claude-opus-4-5-20251101
---

ultrathink: Research and incorporate the following topic: $ARGUMENTS

Perform comprehensive research including:
1. Check existing knowledge in Forgetful and Serena
2. Fetch and analyze provided URLs
3. Perform web searches for additional context
4. Write 3000-5000 word analysis
5. Map integration points with ai-agents project
6. Create Serena memory and atomic Forgetful memories
7. Evaluate if GitHub issue needed for implementation

Current project context:
- Branch: !`git branch --show-current`
- Recent work: !`git log --oneline -5`
```

---

## 9. Proposed `slashcommandcreator` Skill

### 9.1 Skill Purpose

Create a systematic workflow for designing, validating, and implementing high-quality custom slash commands using the same rigor as `skillcreator`.

**Rationale**: Just as `skillcreator` systematizes skill development with 11 thinking models and multi-agent synthesis, `slashcommandcreator` should systematize slash command development with quality gates and best practice enforcement.

### 9.2 Framework Principles (from `skillcreator`)

Apply these `skillcreator` principles to slash commands:

1. **Deep Iterative Analysis**: Multiple thinking models evaluate command design
2. **Regression Questioning**: Challenge assumptions about command necessity, scope, and design
3. **Evolution and Timelessness**: Commands should be future-proof and adaptable
4. **Multi-Agent Synthesis**: Unanimous approval from analyst, architect, security, independent-thinker
5. **Automation Analysis**: Evaluate if command should be a script/automation instead

### 9.3 `slashcommandcreator` Workflow

**Phase 1: Discovery and Analysis**

1. **Clarify Intent**: What prompt is being repeated? What context is needed?
2. **Existing Command Check**: Search `.claude/commands/` for similar commands
3. **Slash Command vs Skill Decision**:
   - Complexity: One file sufficient? Or multiple files/scripts needed?
   - Invocation: Explicit user request? Or automatic context-based?
   - Reusability: Generic prompt? Or team workflow standardization?

**Phase 2: Design**

4. **Command Naming**: Follow namespace conventions (e.g., `pr/review`, `memory/search`)
5. **Argument Design**: Required vs optional, positional vs `$ARGUMENTS`, defaults
6. **Frontmatter Schema**:
   - `description`: Trigger-based (per `creator-001-frontmatter-trigger-specification`)
   - `argument-hint`: Clear expectations for autocomplete
   - `allowed-tools`: Security-constrained tool permissions
   - `model`: Opus 4.5 for complex reasoning, Sonnet 4.5 for standard, Haiku for simple
7. **Dynamic Context**: Identify bash commands (`!`) and file references (`@`) needed
8. **Extended Thinking**: Evaluate if `ultrathink` keyword appropriate for command

**Phase 3: Multi-Agent Validation**

9. **Security Review**: Validate `allowed-tools` constraints (no overly permissive wildcards)
10. **Architect Review**: Ensure command doesn't duplicate existing skill, appropriate scope
11. **Independent-Thinker Review**: Challenge necessity, alternative approaches
12. **Critic Review**: Validate frontmatter completeness, argument handling, error cases

**Phase 4: Implementation**

13. **Create Command File**: Write Markdown with frontmatter and prompt
14. **Test Invocation**: Test with various argument combinations
15. **Documentation**: Add to command catalog (if exists), update CLAUDE.md if project-level

**Phase 5: Quality Gates**

16. **Frontmatter Validation**: YAML parses correctly, all required fields present
17. **Argument Validation**: `argument-hint` matches usage in prompt
18. **Security Validation**: No bash commands without `allowed-tools` permission
19. **Length Validation**: If >200 lines, recommend converting to skill
20. **Lint Validation**: Run `markdownlint-cli2` on command file

### 9.4 Quality Gates Checklist

```markdown
## Slash Command Quality Gates

- [ ] **Frontmatter Complete**: `description`, `argument-hint` present
- [ ] **Trigger-Based Description**: Describes WHEN to use, not just WHAT it does
- [ ] **Argument Handling**: Uses `$ARGUMENTS` or `$1`/`$2` appropriately
- [ ] **Security**: Bash commands have `allowed-tools` with specific patterns
- [ ] **Extended Thinking**: `ultrathink` used for complex reasoning tasks
- [ ] **Model Selection**: Appropriate model for task complexity
- [ ] **Length**: <200 lines (or converted to skill)
- [ ] **Linting**: Passes `markdownlint-cli2`
- [ ] **Testing**: Tested with multiple argument combinations
- [ ] **Documentation**: Added to command catalog or CLAUDE.md
```

### 9.5 Decision Criteria: Slash Command vs Skill

**Use Slash Command When**:
- ✅ Prompt fits in one file (<200 lines)
- ✅ No scripts or utilities required
- ✅ User explicitly invokes command
- ✅ 1-3 simple arguments
- ✅ Primarily prompt text with dynamic context

**Use Skill When**:
- ✅ Multiple files needed (scripts, templates, utilities)
- ✅ Automatic context-based invocation desired
- ✅ Complex multi-step workflow
- ✅ Team workflow standardization with complex logic
- ✅ PowerShell/.psm1 modules required

**Migration Path**: If slash command grows beyond 200 lines or requires scripts, migrate to skill.

---

## 10. Integration with ai-agents Project

### 10.1 Immediate Actions

1. **Create `slashcommandcreator` Skill**:
   - Location: `.claude/skills/slashcommandcreator/`
   - Structure: `SKILL.md` + `scripts/New-SlashCommand.ps1` (PowerShell per ADR-005)
   - Quality Gates: Automated validation in PowerShell script

2. **Establish Slash Command Governance**:
   - Add to `.agents/governance/PROJECT-CONSTRAINTS.md`:
     - MUST include frontmatter with `description` and `argument-hint`
     - MUST use trigger-based descriptions (per `creator-001`)
     - MUST specify `allowed-tools` for bash commands
     - SHOULD use `ultrathink` for complex reasoning commands

3. **Improve Existing Commands**:
   - Add frontmatter to `context-hub-setup.md` and `research.md`
   - Add `ultrathink` to `research.md`, `memory-documentary.md`, `pr-review.md`
   - Specify `allowed-tools` for security

4. **Documentation**:
   - Add slash command section to `CLAUDE.md`
   - Create `.claude/commands/README.md` with catalog
   - Document slash command vs skill decision criteria

### 10.2 Long-Term Enhancements

1. **Pre-Commit Hook**: Validate slash command frontmatter
2. **CI/CD Quality Gate**: Lint all slash commands
3. **Command Catalog Automation**: Auto-generate command catalog from frontmatter
4. **Migration Analysis**: Identify simple skills that should be slash commands

### 10.3 Metrics for Success

| Metric | Target | Measurement |
|--------|--------|-------------|
| **Frontmatter Coverage** | 100% | All `.claude/commands/*.md` have frontmatter |
| **Trigger-Based Descriptions** | 100% | All `description` fields specify WHEN to use |
| **Security Compliance** | 100% | All bash commands have `allowed-tools` |
| **Extended Thinking Adoption** | 50%+ | Complex commands use `ultrathink` |
| **Quality Gate Failures** | <5% | Pre-commit hook rejection rate |

---

## 11. Related Work and Community Patterns

### 11.1 Production Repositories

**wshobson/commands**:
- 57 production-ready slash commands
- 15 workflows + 42 tools
- Multi-agent orchestration capabilities
- Pattern: Separate workflow commands from tool commands

**qdhenry/Claude-Command-Suite**:
- 148+ slash commands, 54 AI agents
- Coverage: code review, testing, deployment, business scenarios
- Pattern: Domain-specific subdirectories (code/, test/, deploy/, business/)

**hesreallyhim/awesome-claude-code**:
- Curated collection of best practices
- Tips and techniques from community
- Pattern: Community-driven knowledge sharing

### 11.2 Community Best Practices

**From cloudartisan.com case study**:
- **Post Creation Automation**: Eliminate repetitive workflows with parametrized commands
- **Content Verification**: Specialized commands for common pain points (language checker, image verifier, link validator)
- **Site Management**: Smart design with clickable URLs for easy navigation
- **Organization**: Subdirectory structure with namespaced commands
- **Version Control**: Commands in Git for team sharing and rollback

**From Shipyard cheat sheet**:
- Use `.claude/commands/` for project-specific prompts
- Use `~/.claude/commands/` for personal cross-project commands
- Leverage `$ARGUMENTS` for dynamic content
- Store commands in version control

---

## 12. Conclusion

Custom slash commands provide a lightweight mechanism for standardizing frequent prompts with dynamic context injection. The ai-agents project should:

1. **Systematize slash command creation** via `slashcommandcreator` skill using rigorous validation
2. **Establish quality gates** for frontmatter, security, and extended thinking usage
3. **Improve existing commands** with frontmatter, `ultrathink`, and `allowed-tools`
4. **Document decision criteria** for slash command vs skill selection
5. **Integrate with governance** via pre-commit hooks and CI/CD validation

By applying the same rigor to slash commands as skills (via `skillcreator` framework), the project can maintain high quality, security, and discoverability for both mechanisms.

---

## Sources

- [Slash commands - Claude Code Docs](https://code.claude.com/docs/en/slash-commands)
- [Claude Code: Best practices for agentic coding](https://www.anthropic.com/engineering/claude-code-best-practices)
- [Claude Code Tips & Tricks: Custom Slash Commands](https://cloudartisan.com/posts/2025-04-14-claude-code-tips-slash-commands/)
- [GitHub - wshobson/commands](https://github.com/wshobson/commands)
- [How I use Claude Code (+ my best tips)](https://www.builder.io/blog/claude-code)
- [GitHub - hesreallyhim/awesome-claude-code](https://github.com/hesreallyhim/awesome-claude-code)
- [How to Create Custom Slash Commands in Claude Code](https://en.bioerrorlog.work/entry/claude-code-custom-slash-command)
- [Shipyard | Claude Code CLI Cheatsheet](https://shipyard.build/blog/claude-code-cheat-sheet/)
- [Claude Code Tutorial: YouTube Research Agent](https://creatoreconomy.so/p/claude-code-tutorial-build-a-youtube-research-agent-in-15-min)
- [GitHub - qdhenry/Claude-Command-Suite](https://github.com/qdhenry/Claude-Command-Suite)
