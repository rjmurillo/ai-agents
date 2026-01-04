# Skill Frontmatter Validator Alignment

**Date**: 2026-01-03
**Sessions**: 366, 356

## Key Learning

SkillForge's `validate-skill.py` is the authoritative source for skill frontmatter structure.

## Required Top-Level Fields

Per validate-skill.py (upstream, do not modify):

```yaml
---
name: skill-name       # Required
version: X.Y.Z         # Required
description: ...       # Required
license: MIT           # Required
model: claude-*-4-5    # Required
allowed-tools: ...     # Optional
metadata:              # Optional - domain-specific fields only
  ...
---
```

## Changes Made (Session 366)

1. **Pre-commit hook**: Replaced `Generate-Skills.ps1` with `validate-skill.py`
2. **ADR-040**: Updated to reflect validate-skill.py as authoritative
3. **9 skills updated**: Moved version/model from metadata to top-level
4. **Orphaned files removed**: `build/tests/Generate-Skills.Tests.ps1` and references

## Important Notes

- Do NOT modify validate-skill.py (upstream code)
- quick_validate.py is for packaging, validate-skill.py is for structure
- Structural validation (Triggers, Process sections) is separate from frontmatter

## Commits

- d7f2e08: Replace generation with validation
- 1e79e86: Align frontmatter with validate-skill.py
- 212ee4c, e08a51b, ca96f59: Cleanup vestiges
