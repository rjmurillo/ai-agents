# Skill-Creator-007: Anthropic Frontmatter Validation Compliance

## Statement

Custom frontmatter properties MUST be nested under `metadata`, not at root level, to pass Anthropic skill-creator validation.

## Context

When creating SKILL.md frontmatter for Claude Code skills that will be validated by Anthropic's skill-creator validation script.

## Pattern

**Bad (root-level custom property)**:

```yaml
---
name: example
description: Example skill
keep_headings: true  # FAILS validation
---
```

**Good (nested under metadata)**:

```yaml
---
name: example
description: Example skill
metadata:
  generator:
    keep_headings: true  # PASSES validation
---
```

## Allowed Root-Level Keys

Anthropic skill-creator validation enforces these allowed root-level frontmatter keys:

- `name`
- `description`
- `license`
- `allowed-tools`
- `metadata`
- `compatibility`

Any custom properties (like `keep_headings`, `strip_comments`, generator configs) must be nested under `metadata`.

## Why This Matters

Anthropic's skill-creator validation script rejects SKILL.md files with non-standard root-level frontmatter keys. This prevents skills from being published or validated in the Claude Code ecosystem.

Generator-specific metadata belongs under `metadata.generator.*` to avoid namespace collisions and maintain forward compatibility.

## Evidence

Issue #369 (2025-12-28): Generate-Skills.ps1 (script deleted in commit d7f2e08, replaced by validate-skill.py) incorrectly accessed `keep_headings` at root level, causing validation failures. Fixed by changing to `metadata.generator.keep_headings`.

Commit: [SHA from fix/issue-369-ci-verification branch]

## Metrics

- Atomicity: 92%
- Category: skill-creator, frontmatter, validation
- Created: 2025-12-28
- Tag: skill-creator
- Validated: 1 (Issue #369)

## Related Skills

- Skill-Creator-001 (frontmatter trigger specification)
- Skill-Creator-005 (schema redundancy elimination)
