# Skill-Creator-002: Token Efficiency via Comment Stripping

## Statement

Config files in skill directories MUST NOT contain inline documentation. Strip comments and move documentation to `references/{config-name}-guide.md`.

## Context

When creating or optimizing Claude Code skills that include configuration files (YAML, JSON, etc.).

## Pattern

**Bad (comments in config)**:

```yaml
# This section configures the synthesis pipeline
# The priority field determines processing order
# Valid values: high, medium, low
synthesis:
  priority: high  # Set to high for critical issues
```

**Good (config only)**:

```yaml
synthesis:
  priority: high
```

**Documentation goes to**: `references/synthesis-config-guide.md`

## Why This Matters

- Claude loads skill configs during execution
- Comments consume tokens but provide no runtime value
- 273 lines with comments = 27 lines without = **~2,400 token savings**

## Evidence

PR #255 (2025-12-22): `copilot-synthesis.yml` reduced from 273 to 27 lines. Commit `69fffd6`.

Token savings: ~2,400 tokens per skill load.

## Metrics

- Atomicity: 92%
- Category: token-optimization, skill-structure
- Created: 2025-12-22
- Tag: skill-creator
- Validated: 1 (PR #255)

## Related Skills

- Skill-Creator-004 (reference extraction)
- Skill-Memory-TokenEfficiency-001 (activation vocabulary)
