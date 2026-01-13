# Skill-Documentation-005: User-Facing Content Restrictions

**Statement**: Exclude internal PR/Issue/Session references from src/ and templates/ directories.

**Context**: When creating or updating user-facing documentation.

**Evidence**: PR #212 - User policy request, 6 files updated.

**Atomicity**: 92% | **Impact**: 9/10 | **Tag**: critical

## Scope

- `src/claude/`
- `src/copilot-cli/`
- `src/vs-code-agents/`
- `templates/agents/`

## Prohibited Content

- `PR #XXX`, `Issue #XXX`, `Session XX`
- `.agents/`, `.serena/` paths

## Permitted Content

- CWE references
- RFC standards
- Generic patterns

## Validation

```bash
grep -r "PR #\|Issue #\|Session \d\+\|\.agents/\|\.serena/" src/ templates/
# Should return no matches
```

## Related

- [documentation-001-systematic-migration-search](documentation-001-systematic-migration-search.md)
- [documentation-002-reference-type-taxonomy](documentation-002-reference-type-taxonomy.md)
- [documentation-003-fallback-preservation](documentation-003-fallback-preservation.md)
- [documentation-004-pattern-consistency](documentation-004-pattern-consistency.md)
- [documentation-006-self-contained-operational-prompts](documentation-006-self-contained-operational-prompts.md)
