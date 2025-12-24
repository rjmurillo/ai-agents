# Skill-Creator-005: Schema Redundancy Elimination

## Statement

JSON schema files that duplicate YAML config structure MUST be deleted from skill directories. Schema validation is a CI concern, not a skill execution concern.

## Context

When reviewing skill directories for token efficiency.

## Pattern

**Bad (redundant schema)**:

```text
.claude/skills/github/
├── copilot-synthesis.yml      # Source of truth
└── copilot-synthesis.schema.json  ❌ Duplicates structure (~500 tokens)
```

**Good (single source)**:

```text
.claude/skills/github/
└── copilot-synthesis.yml      # Source of truth
```

## Why This Matters

- YAML is the source of truth for Claude
- JSON schema adds no value to skill execution
- Schema validation belongs in CI pipeline, not skill directory
- Token savings: ~500 tokens

## Decision Tree

```text
Does the file help Claude execute the skill?
├─ Yes → Keep in skill directory
└─ No → Move to CI (.github/) or delete
```

## Evidence

PR #255 (2025-12-22): `copilot-synthesis.schema.json` (106 lines) deleted. Commit `ae58331`.

## Metrics

- Atomicity: 96%
- Category: token-optimization, redundancy
- Created: 2025-12-22
- Tag: skill-creator
- Validated: 1 (PR #255)

## Related Skills

- Skill-Creator-003 (test separation)
- Skill-Creator-002 (comment stripping)
