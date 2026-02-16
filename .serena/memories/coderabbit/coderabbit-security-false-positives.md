## Skill-003: Infrastructure Naming Avoids Spaces (90%)

Infrastructure files don't need space-handling code. Naming conventions prevent spaces.

**Evidence**: PR #57

## Skill-004: Expression Injection Labeling (95%)

"VULNERABLE" labels on `${{ }}` echo statements are accurate, not hyperbolic. These are real security risks.

**Evidence**: PR #57

## Quick Reference

| Pattern | Action |
|---------|--------|
| Missing space handling in infra | Dismiss (naming conventions) |
| "VULNERABLE" on expression injection | Keep (accurate severity) |

## Related

- [coderabbit-config-strategy](coderabbit-config-strategy.md)
- [coderabbit-documentation-false-positives](coderabbit-documentation-false-positives.md)
- [coderabbit-markdownlint](coderabbit-markdownlint.md)
- [coderabbit-mcp-false-positives](coderabbit-mcp-false-positives.md)
- [coderabbit-path-instructions](coderabbit-path-instructions.md)
