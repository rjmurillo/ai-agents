# Regex Skills

**Created**: 2025-12-20
**Source**: PR #212 retrospective

## Skill-Regex-001: Atomic Optional Group for Trailing Characters

**Statement**: Use `([pattern])?$` not `[pattern]?$` for optional trailing characters to prevent special char bypass

**Context**: When building validation regex with optional trailing characters

**Evidence**: PR #212 Copilot review - 5 instances of `[a-zA-Z0-9]?$` allowing trailing special chars

**Atomicity**: 93%

**Tag**: helpful (security, validation)

**Impact**: 9/10 (prevents validation bypass)

**Created**: 2025-12-20

**Problem**:

```regex
# WRONG - Allows trailing special characters
^[a-zA-Z0-9][a-zA-Z0-9 _\-\.]{0,48}[a-zA-Z0-9]?$

# Example bypass:
# "valid123!" matches because [a-zA-Z0-9]? is optional and ! is after it
```

**Solution**:

```regex
# CORRECT - Atomic group prevents special char bypass
^[a-zA-Z0-9]([a-zA-Z0-9 _\-\.]{0,48}[a-zA-Z0-9])?$

# Now "valid123!" fails because the entire group ([...])? is atomic
```

**Why It Matters**:

When `[pattern]?` is used at the end of a regex, the `?` makes only the character class optional, not the validation constraint. An atomic group `([pattern])?` makes the entire trailing validation optional as a unit, preventing special characters from appearing after the validated content.

**Pattern**:

```regex
# Safe pattern for optional trailing validation
^[start_pattern](middle_pattern[end_pattern])?$

# Example: Label validation
^[a-zA-Z0-9]([a-zA-Z0-9 _\-\.]{0,48}[a-zA-Z0-9])?$
```

**Anti-Pattern**:

```regex
# Unsafe - trailing special chars can bypass
^[start_pattern]middle_pattern[end_pattern]?$
```

**Validation**: 1 (PR #212, 5 instances fixed)

**Related**: Skill-PowerShell-Security-001 (hardened regex for AI output)

---

## Application Checklist

When writing validation regex:

1. [ ] Use atomic groups `(...)` for optional multi-character patterns
2. [ ] Test with trailing special characters (`!`, `;`, `$`, etc.)
3. [ ] Verify that `?` applies to the correct scope
4. [ ] Consider using anchors `^` and `$` for full string validation
5. [ ] Test with edge cases: empty string, single char, max length

## Common Validation Patterns

### Label/Tag Validation

```regex
# Alphanumeric start, optional middle with spaces/hyphens/dots, alphanumeric end
^[a-zA-Z0-9]([a-zA-Z0-9 _\-\.]{0,48}[a-zA-Z0-9])?$
```

### Username/Identifier Validation

```regex
# Alphanumeric start, optional middle with hyphens/underscores, alphanumeric end
^[a-zA-Z0-9]([a-zA-Z0-9_\-]{0,38}[a-zA-Z0-9])?$
```

### Filename Validation (safe characters only)

```regex
# Alphanumeric start, optional middle with dots/hyphens/underscores, alphanumeric end
^[a-zA-Z0-9]([a-zA-Z0-9._\-]{0,253}[a-zA-Z0-9])?$
```

## References

- PR #212: Security remediation for CWE-20/CWE-78
- Copilot review comments: 5 instances of atomic group fix
