# Skill-Creator-001: Frontmatter Trigger Specification

## Statement

Skill frontmatter descriptions MUST specify WHEN to use the skill (trigger context), not just WHAT it does (capabilities).

## Context

When writing or reviewing skill frontmatter for Claude Code skills.

## Pattern

**Bad (capability-only)**:

```yaml
description: GitHub CLI operations for PRs, Issues, Labels, Milestones, Comments, and Reactions.
```

**Good (trigger-based)**:

```yaml
description: |
  GitHub CLI operations for PRs, Issues, Labels, Milestones, Comments, and Reactions.
  Use when Claude needs to: (1) Get PR context, diff, or changed files, (2) Reply to
  PR review comments preserving threads, (3) Post idempotent issue comments...
```

## Format Template

```yaml
description: |
  [Capability summary - one sentence]
  Use when Claude needs to: (1) [trigger 1], (2) [trigger 2], (3) [trigger 3]...
```

## Why This Matters

Claude selects skills based on frontmatter matching against the current task. Capability descriptions match on domain (e.g., "GitHub" matches many tasks). Trigger descriptions match on intent (e.g., "reply to PR review comments" matches specific tasks).

Result: Higher precision skill activation, fewer false positives.

## Evidence

PR #255 (2025-12-22): GitHub skill frontmatter rewritten with trigger context. Commit `97d7f10`.

## Metrics

- Atomicity: 95%
- Category: skill-creation, frontmatter, activation
- Created: 2025-12-22
- Tag: skill-creator
- Validated: 1 (PR #255)

## Related Skills

- Skill-Memory-TokenEfficiency-001 (activation vocabulary)
- Skill-Creator-002 (token optimization)

## Related

- [creator-002-token-efficiency-comment-stripping](creator-002-token-efficiency-comment-stripping.md)
- [creator-003-test-separation-skill-directory](creator-003-test-separation-skill-directory.md)
- [creator-004-reference-material-extraction](creator-004-reference-material-extraction.md)
- [creator-005-schema-redundancy-elimination](creator-005-schema-redundancy-elimination.md)
- [creator-006-toc-requirement-long-files](creator-006-toc-requirement-long-files.md)
