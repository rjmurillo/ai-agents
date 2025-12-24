# Skill-Lint-004: Configuration Before Fixes

**Statement**: Create linting configuration file first to establish baseline before any fixes

**Context**: New linting implementation in existing codebase

**Evidence**: 2025-12-13 - `.markdownlint-cli2.yaml` created first, enabled consistent auto-fix behavior

**Atomicity**: 92%

**Impact**: 9/10

## Configuration First

1. Create `.markdownlint-cli2.yaml`
2. Configure disabled rules
3. Set up exclusions
4. Document false positives
5. Then run fixes

## Disabled Rules

| Rule | Reason |
|------|--------|
| MD013 | Line length conflicts with readability |
| MD060 | Table spacing conflicts with tools |
| MD029 | Ordered list prefix style preference |

## Document False Positives

Document known false positives in config comments with file locations.
