# Regex Skills

**Extracted**: 2025-12-20
**Source**: PR #212 retrospective analysis

## Skill-Regex-001: Atomic Optional Groups for Trailing Characters

**Statement**: Use `([pattern])?` instead of `[pattern]?` for optional trailing characters in regex to ensure atomic matching.

**Context**: When parsing structured output (labels, milestones, file names) that may have optional trailing characters.

**Evidence**: PR #212 - Regex `[a-zA-Z0-9]?$` failed to match expected patterns; fixed with `([a-zA-Z0-9])?$`

**Atomicity**: 93%

**Tag**: helpful (prevents regex mismatch bugs)

**Impact**: 8/10 (improves pattern reliability)

**Created**: 2025-12-20

**Problem**:

```regex
# WRONG - Character class with ? makes single char optional, not the group
^[a-zA-Z0-9][a-zA-Z0-9 _\-\.]{0,48}[a-zA-Z0-9]?$
```

**Solution**:

```regex
# CORRECT - Capture group with ? makes entire pattern optional
^[a-zA-Z0-9]([a-zA-Z0-9 _\-\.]{0,48}[a-zA-Z0-9])?$
```

**Why It Matters**:

In regex, `[abc]?` means "optionally match ONE character from this class", while `([abc]+)?` means "optionally match the ENTIRE group". For patterns where you want either a full match or nothing (not partial), use the group syntax.

**Pattern**:

```regex
# For optional trailing sections, wrap in group
^prefix(middle-section)?$

# For optional single character at specific position
^prefix[char-class]?suffix$  # Only if single char is truly optional
```

**Anti-Pattern**:

```regex
# Using character class ? when you mean group ?
^start[a-z]{1,10}[a-z]?$  # Ambiguous - is trailing [a-z]? needed?
```

**Validation**: 1 (PR #212)

---

## Related Skills

- Skill-PowerShell-Security-001: Hardened Regex for AI Output (uses atomic grouping)

## Related

- [utilities-cva-refactoring](utilities-cva-refactoring.md)
- [utilities-markdown-fences](utilities-markdown-fences.md)
- [utilities-pathinfo-conversion](utilities-pathinfo-conversion.md)
- [utilities-precommit-hook](utilities-precommit-hook.md)
- [utilities-security-patterns](utilities-security-patterns.md)
