# Skill-Labeler-005: ALL PATTERNS Matcher

**Statement**: Use `all-globs-to-any-file` when ALL patterns must find matches somewhere in changeset.

**Context**: When label requires multiple pattern types to be present.

**Example**: Label when both `.ts` AND `.test.ts` files changed.

**Atomicity**: 88%

**Anti-Pattern**: Using multiple separate matchers expecting AND logic (they OR by default).

## Matcher Reference

| Matcher | Logic | Use When |
|---------|-------|----------|
| `any-glob-to-any-file` | ANY -> ANY | Simple presence check |
| `all-globs-to-all-files` | ALL -> ALL | Negation patterns |
| `any-glob-to-all-files` | ANY -> ALL | All files must match |
| `all-globs-to-any-file` | ALL -> ANY | Multiple patterns required |

## Related

- [labeler-001-negation-pattern-matcher-selection](labeler-001-negation-pattern-matcher-selection.md)
- [labeler-003-any-matcher](labeler-003-any-matcher.md)
- [labeler-004-all-files-matcher](labeler-004-all-files-matcher.md)
- [labeler-006-negation-pattern-isolation](labeler-006-negation-pattern-isolation.md)
- [labeler-combined-patterns](labeler-combined-patterns.md)
