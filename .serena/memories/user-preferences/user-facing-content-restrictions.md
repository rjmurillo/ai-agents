# User-Facing Content Restrictions

**Created**: 2025-12-20
**Source**: PR #212 review feedback

## Scope

This policy applies to all files that are distributed to end-users:

- `src/claude/` - Claude agent definitions
- `src/copilot-cli/` - Copilot CLI agent definitions
- `src/vs-code-agents/` - VS Code agent definitions
- `templates/agents/` - Agent templates

## PROHIBITED Content

The following content types MUST NOT appear in user-facing files:

### 1. Internal PR References

- **Prohibited**: `PR #60`, `PR #211`, `PR #212`, or any internal PR numbers
- **Rationale**: End-users do not know or care about issues internal to our repository
- **Alternative**: Describe the pattern generically without referencing specific internal PRs

### 2. Internal Issue References

- **Prohibited**: `Issue #16`, `Issue #183`, or any internal issue numbers
- **Rationale**: Same as above - internal tracking is meaningless to users

### 3. Session References

- **Prohibited**: `Session 44`, `Session 15`, or any session identifiers
- **Rationale**: These are internal implementation details

### 4. Internal File Paths

- **Prohibited**: References to `.agents/`, `.serena/`, or other internal directories
- **Rationale**: Users may not have the same directory structure

## PERMITTED Content

- Generic descriptions of patterns and behaviors
- Security vulnerability identifiers (CWE-20, CWE-78, etc.) - these are public standards
- Best practice recommendations without internal context

## Example Fix

**Before (prohibited)**:

```markdown
| **Security** | ... | Security issues can cause critical damage; CWE-20/CWE-78 introduced in PR #60 went undetected until PR #211 quality gate |
```

**After (compliant)**:

```markdown
| **Security** | ... | Security issues can cause critical damage if missed during review |
```

## Validation

Before committing changes to user-facing directories, verify no internal references are present.
