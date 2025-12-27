# Skill-Lint-005: Exclude Generated Directories

**Statement**: Exclude generated artifact directories from linting using both globs and ignores

**Context**: Managing linting for mixed codebase with generated content

**Atomicity**: 90%

**Impact**: 8/10

## Implementation

In `.markdownlint-cli2.yaml`:

```yaml
ignores:
  - ".agents/**"
  - "node_modules/**"
  - "dist/**"
globs:
  - "!.agents/**"
```

## Why Exclude .agents/

ADRs/plans have different formatting needs:

- Intentional nested code blocks
- Templates with special syntax
- Generated content

## False Positives

Document known false positives in config comments:

```yaml
# Known false positives:
# - retrospective.md: nested templates trigger MD040
# - roadmap.md: nested templates trigger MD040
```

## Anti-Pattern

- Disabling rules without documentation
- **Prevention**: Add inline comments explaining why
