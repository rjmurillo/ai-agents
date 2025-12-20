# Skill: Google Gemini Code Assist Configuration

**Last Updated**: 2025-12-18
**Documentation Source**: https://developers.google.com/gemini-code-assist/docs/customize-gemini-behavior-github
**Status**: Complete Configuration Schema Extracted

## Overview

Google Gemini Code Assist can be customized for GitHub repositories using configuration files placed in a `.gemini/` folder at the repository root. This skill documents the complete configuration schema, path exclusion patterns, style guide format, and best practices.

## Configuration Files

### 1. `.gemini/config.yaml` - Repository Configuration

**Location**: `.gemini/config.yaml` (repository root)

**Purpose**: Controls Gemini Code Assist behavior including code review settings, path exclusions, and feature toggles.

#### Complete Schema

```yaml
$schema: "http://json-schema.org/draft-07/schema#"
title: RepoConfig
description: Configuration for Gemini Code Assist on a repository
type: object
properties:
  have_fun:
    type: boolean
    description: "Enables fun features such as a poem in the initial pull request summary"
    default: false

  ignore_patterns:
    type: array
    items:
      type: string
    description: "A list of glob patterns for files and directories to skip during interactions"
    default: []

  memory_config:
    type: object
    description: Configuration for persistent memory
    properties:
      disabled:
        type: boolean
        description: "Disable persistent memory for this specific repository"
        default: false

  code_review:
    type: object
    description: Configuration for code reviews
    properties:
      disable:
        type: boolean
        description: "Disables Gemini from acting on pull requests"
        default: false

      comment_severity_threshold:
        type: string
        enum: [LOW, MEDIUM, HIGH, CRITICAL]
        description: "Minimum severity of review comments to include"
        default: MEDIUM

      max_review_comments:
        type: integer
        format: int64
        description: "Maximum review comments (-1 for unlimited)"
        default: -1

      pull_request_opened:
        type: object
        description: Configuration for pull request opened events
        properties:
          help:
            type: boolean
            description: "Post help message on PR open"
            default: false

          summary:
            type: boolean
            description: "Post pull request summary on open"
            default: true

          code_review:
            type: boolean
            description: "Post code review on open"
            default: true

          include_drafts:
            type: boolean
            description: "Enable agent functionality on draft pull requests"
            default: true
```

#### Default Configuration Example

```yaml
have_fun: false
memory_config:
  disabled: false
code_review:
  disable: false
  comment_severity_threshold: MEDIUM
  max_review_comments: -1
  pull_request_opened:
    help: false
    summary: true
    code_review: true
    include_drafts: true
ignore_patterns: []
```

#### Key Configuration Options

##### Code Review Settings

| Setting | Type | Default | Purpose |
|---------|------|---------|---------|
| `code_review.disable` | boolean | false | Disables Gemini from acting on pull requests entirely |
| `code_review.pull_request_opened.code_review` | boolean | true | Enable code review comments on PR open |
| `code_review.pull_request_opened.summary` | boolean | true | Enable PR summary generation |
| `code_review.pull_request_opened.include_drafts` | boolean | true | Apply functionality to draft PRs |
| `code_review.pull_request_opened.help` | boolean | false | Post help message on PR open |
| `code_review.comment_severity_threshold` | enum | MEDIUM | Minimum severity: LOW, MEDIUM, HIGH, CRITICAL |
| `code_review.max_review_comments` | integer | -1 | Maximum comments (-1 = unlimited) |

##### Path Exclusions

**Field**: `ignore_patterns`
**Type**: Array of strings (glob patterns)
**Default**: `[]`

**Purpose**: Exclude files and directories from all Gemini interactions (code review, summaries, etc.)

**Glob Pattern Syntax**: Uses [VS Code glob patterns](https://code.visualstudio.com/docs/editor/glob-patterns)

**Examples**:
```yaml
ignore_patterns:
  - ".agents/**"
  - ".serena/memories/**"
  - "**/*.generated.cs"
  - "**/bin/**"
  - "**/obj/**"
  - "*.min.js"
```

**Common Exclusion Patterns**:
- `**/*.{ext}` - All files with extension anywhere
- `**/folder/**` - Entire directory tree
- `folder/*` - Direct children only
- `!pattern` - Negation (include exception)

##### Other Settings

| Setting | Type | Default | Purpose |
|---------|------|---------|---------|
| `have_fun` | boolean | false | Enables fun features like poems in PR summaries |
| `memory_config.disabled` | boolean | false | Disable persistent memory for this repository |

### 2. `.gemini/styleguide.md` - Custom Style Guide

**Location**: `.gemini/styleguide.md` (repository root)

**Purpose**: Define custom coding standards, best practices, and organizational conventions that extend or override language-standard review prompts.

#### Format Requirements

- **Natural language Markdown** (no strict schema)
- Treated as regular Markdown that expands the standard review prompt
- Combined with group-level style guides (enterprise version)
- Used to customize review focus areas

#### Recommended Structure

```markdown
# [Project Name] Coding Style Guide

## Introduction
[High-level principles and philosophy]

## Language Standards
[Deviations from standard conventions like PEP 8, Google Style Guide, etc.]

## Code Organization

### Line Length
[Maximum characters, exceptions]

### Indentation
[Spaces vs tabs, size, alignment rules]

### Import Organization
[Order, grouping, absolute vs relative]

## Naming Conventions

### Variables
[camelCase, snake_case, prefixes]

### Constants
[UPPER_CASE, naming patterns]

### Functions/Methods
[Naming patterns, verb conventions]

### Classes
[PascalCase, interface naming]

### Modules/Files
[File naming, organization]

## Documentation

### Docstrings
[Format, required sections, examples]

### Type Hints
[When required, format, generics]

### Comments
[When to comment, style, TODOs]

## Code Patterns

### Error Handling
[Exception types, logging, recovery]

### Logging
[Levels, format, what to log]

### Asynchronous Code
[async/await patterns, Task usage]

## Tooling

### Required Tools
[Linters, formatters, analyzers]

### Configuration
[EditorConfig, .editorconfig settings]

## Examples

### Good
```language
[Example of preferred code]
```

### Avoid
```language
[Example of anti-pattern]
```
```

#### Interaction with Standard Reviews

When **no custom style guide exists**, Gemini reviews focus on:

1. **Correctness** - Logic errors, edge cases, race conditions, incorrect API usage
2. **Efficiency** - Performance bottlenecks, excessive loops, memory leaks, inefficient data structures, redundant calculations
3. **Maintainability** - Readability, modularity, naming, documentation, code duplication, formatting, magic numbers
4. **Security** - Vulnerabilities, data handling, input validation, injection attacks, access controls, CSRF, IDOR
5. **Miscellaneous** - Testing, performance, scalability, modularity, error logging, monitoring

When **custom style guide exists**, it **extends** these categories with project-specific rules.

## Multi-Repository Configuration

### Enterprise Version

**Group-Level Configuration**:
- Managed via Google Cloud console
- Apply settings to Developer Connect connection groups
- Set organization-wide style guides

**Configuration Precedence**:
- Repository `config.yaml` **overrides** group settings
- **Exception**: "Improve response quality" can only be **disabled** in `config.yaml`, not enabled
- Repository `styleguide.md` is **combined** with group style guide (not replaced)

### Consumer Version

- Toggle settings for all repositories via Code review page in Gemini Code Assist
- Per-account settings

## Configuration for AI Agent Repositories

### Recommended `.gemini/config.yaml` for ai-agents Project

```yaml
# Enable code review on all PRs including drafts
code_review:
  disable: false
  pull_request_opened:
    code_review: true
    summary: false  # Disable summaries to avoid noise
    include_drafts: true
    help: false
  comment_severity_threshold: MEDIUM
  max_review_comments: -1  # Unlimited

# Exclude agent artifacts and memory files from review
ignore_patterns:
  - ".agents/**"
  - ".serena/memories/**"
  - "**/*.generated.*"
  - "**/bin/**"
  - "**/obj/**"

# Disable fun features for professional context
have_fun: false

# Keep persistent memory enabled
memory_config:
  disabled: false
```

### Recommended `.gemini/styleguide.md` for ai-agents Project

Should include:
- PowerShell scripting standards (PascalCase functions, approved verbs)
- Markdown linting requirements (markdownlint-cli2)
- Agent protocol patterns (handoff format, memory usage)
- Security requirements (input validation, injection prevention)
- Git commit message format (conventional commits)
- Documentation standards (ADR format, RFC 2119 keywords)

## Best Practices

### Path Exclusions

**Do Exclude**:
- Generated files (`**/*.generated.*`)
- Build outputs (`**/bin/**`, `**/obj/**`)
- Agent artifacts (`.agents/**`)
- Memory stores (`.serena/memories/**`)
- Third-party code (`**/vendor/**`, `**/node_modules/**`)
- Minified files (`**/*.min.js`)

**Don't Exclude**:
- Core source code
- Test files (unless intentionally)
- Configuration files that should be reviewed
- Documentation

### Code Review Settings

**Enable Reviews When**:
- Team wants automated feedback
- Consistent style enforcement needed
- Security vulnerability detection desired

**Disable Summaries When**:
- PR titles/descriptions are sufficient
- Reducing comment noise is priority
- Team prefers human-written summaries

**Include Drafts When**:
- Early feedback is valuable
- Iterative review process preferred

**Exclude Drafts When**:
- Draft PRs are exploratory/incomplete
- Review noise should be minimized

### Style Guide Content

**Effective Style Guides**:
- Specific and actionable rules
- Code examples for clarity
- Rationale for non-obvious rules
- Links to external standards
- Concise (avoid wall of text)

**Avoid**:
- Restating language defaults without deviation
- Vague principles without concrete rules
- Overly prescriptive micro-management
- Conflicting guidance

## Anti-Patterns

### Configuration Anti-Patterns

**Don't**:
- Set `max_review_comments: 0` (use `code_review.disable: true` instead)
- Use `ignore_patterns` for temporary exclusions (use PR-level settings)
- Enable `have_fun` in professional repositories
- Disable memory without clear reason

### Style Guide Anti-Patterns

**Don't**:
- Copy-paste entire language style guides (link instead)
- Write style guides longer than actual code
- Contradict linter/formatter rules
- Include non-style content (architecture, deployment)

## Troubleshooting

### Reviews Not Appearing
- Check `code_review.disable` is `false`
- Verify `pull_request_opened.code_review` is `true`
- Confirm PR is not on excluded paths
- Check `include_drafts` setting for draft PRs

### Too Many Comments
- Increase `comment_severity_threshold` to HIGH or CRITICAL
- Set `max_review_comments` to lower value
- Refine `ignore_patterns` to exclude more files

### Custom Rules Ignored
- Verify `styleguide.md` is in `.gemini/` folder
- Check Markdown syntax is valid
- Ensure rules are specific and actionable
- Confirm no group-level override (enterprise)

## References

- **Official Documentation**: https://developers.google.com/gemini-code-assist/docs/customize-gemini-behavior-github
- **Glob Pattern Syntax**: https://code.visualstudio.com/docs/editor/glob-patterns
- **JSON Schema Draft 07**: http://json-schema.org/draft-07/schema#

## Change Log

- **2025-12-18**: Initial extraction from official documentation
  - Complete schema documented
  - Path exclusion patterns researched
  - Style guide format requirements extracted
  - Best practices and anti-patterns identified
