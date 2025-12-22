# Skill-Creator-004: Reference Material Extraction

## Statement

SKILL.md MUST contain workflow guidance (what to do). Reference material (exit codes, API endpoints, troubleshooting) MUST be extracted to `references/` directory for progressive disclosure.

## Context

When writing or optimizing SKILL.md for Claude Code skills.

## Pattern

**Bad (everything in SKILL.md)**:

```markdown
# My Skill

## Usage
...workflow...

## Exit Codes          ❌ Reference material in workflow doc
| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Error |

## Troubleshooting     ❌ Rarely needed, consumes tokens
...
```

**Good (progressive disclosure)**:

```markdown
# My Skill

## Usage
...workflow...

## See Also
- `references/api-reference.md` - Exit codes, endpoints, troubleshooting
```

## Why This Matters

Claude reads SKILL.md always; reads references/ only when encountering issues:

- SKILL.md: What to do (always relevant)
- references/: How to debug (rarely relevant)

Token savings: ~200 tokens + improved signal-to-noise ratio.

## Evidence

PR #255 (2025-12-22): SKILL.md reduced from 207 to 145 lines. Reference tables moved to `references/api-reference.md`. Commit `c0a3c1f`.

## Metrics

- Atomicity: 91%
- Category: progressive-disclosure, skill-structure
- Created: 2025-12-22
- Tag: skill-creator
- Validated: 1 (PR #255)

## Related Skills

- Skill-Creator-002 (comment stripping)
- Skill-Documentation-004 (pattern consistency)
