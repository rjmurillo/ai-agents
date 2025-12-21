# Documentation Skills

**Created**: 2025-12-20
**Sources**: Various retrospectives and PR reviews

## Skill-Documentation-005: User-Facing Content Restrictions

**Statement**: Exclude internal PR/Issue/Session references from src/ and templates/ directories

**Context**: When creating or updating user-facing documentation

**Evidence**: PR #212 - User policy request, 6 files updated to remove internal references

**Atomicity**: 92%

**Tag**: critical (user experience)

**Impact**: 9/10 (maintains professional external documentation)

**Created**: 2025-12-20

**Scope**:

This policy applies to all files distributed to end-users:

- `src/claude/` - Claude agent definitions
- `src/copilot-cli/` - Copilot CLI agent definitions
- `src/vs-code-agents/` - VS Code agent definitions
- `templates/agents/` - Agent templates

**Prohibited Content**:

### 1. Internal PR References

- **Prohibited**: `PR #60`, `PR #211`, `PR #212`, or any internal PR numbers
- **Rationale**: End-users do not know or care about issues internal to our repository
- **Alternative**: Describe the pattern generically without referencing specific internal PRs

**Example Fix:**

```markdown
<!-- WRONG -->
Security issues can cause critical damage; CWE-20/CWE-78 introduced in PR #60 went undetected until PR #211

<!-- CORRECT -->
Security issues can cause critical damage if missed during review
```

### 2. Internal Issue References

- **Prohibited**: `Issue #16`, `Issue #183`, or any internal issue numbers
- **Rationale**: Same as above - internal tracking is meaningless to users

### 3. Session References

- **Prohibited**: `Session 44`, `Session 15`, or any session identifiers
- **Rationale**: These are internal implementation details

### 4. Internal File Paths

- **Prohibited**: References to `.agents/`, `.serena/`, or other internal directories
- **Rationale**: Users may not have the same directory structure

**Permitted Content**:

- Generic descriptions of patterns and behaviors
- Security vulnerability identifiers (CWE-20, CWE-78, etc.) - these are public standards
- Best practice recommendations without internal context
- Public references (RFC numbers, standard specifications)

**Validation**:

Before committing changes to user-facing directories, verify no internal references are present.

**Pattern**:

```bash
# Scan for internal references before commit
grep -r "PR #\|Issue #\|Session \d\+\|\.agents/\|\.serena/" src/ templates/
# Should return no matches in user-facing files
```

**Anti-Pattern**:

Including internal tracking numbers or file paths in templates that users will copy.

**Validation**: 1 (PR #212, 6 files updated)

**Related Memory**: `user-facing-content-restrictions` (policy reference)

---

## Application Checklist

When creating/updating user-facing documentation:

1. [ ] Remove all `PR #XXX` references
2. [ ] Remove all `Issue #XXX` references
3. [ ] Remove all `Session XX` references
4. [ ] Remove all `.agents/` and `.serena/` path references
5. [ ] Replace specific examples with generic patterns
6. [ ] Keep public standard references (CWE, RFC, etc.)
7. [ ] Verify no internal tracking numbers remain

---

## Related Skills

- Skill-Documentation-001: Systematic migration search
- Skill-Documentation-002: Reference type taxonomy
- Skill-Documentation-003: Fallback preservation
- Skill-Documentation-004: Pattern consistency

## References

- PR #212: User policy creation
- Memory: `user-facing-content-restrictions`
