# Git Hook Patterns

## File Staging in Pre-Commit Hooks

### Idempotent Staging Pattern (Preferred)

```bash
# ✅ CORRECT: git add is idempotent
# Safely handles: new files, modified files, unchanged files
if [ -f "$FILE" ]; then
    git add -- "$FILE"
fi
```

### Anti-Pattern: Conditional Staging with git diff

```bash
# ❌ WRONG: git diff --quiet doesn't detect untracked files
# Only works for tracked (existing) files
if ! git diff --quiet -- "$FILE" 2>/dev/null; then
    git add -- "$FILE"
fi
```

### Why git diff --quiet Fails

- `git diff --quiet` compares working tree to index
- Returns 0 (no changes) for **untracked** files
- First-time file creation won't trigger staging
- Silent failure - no error, just doesn't stage

### Evidence

PR #52: cursor[bot] identified this bug at .githooks/pre-commit:300

- First-time mcp.json creation wouldn't be staged
- Fixed by replacing conditional with unconditional `git add`

### Checklist for Pre-Commit File Staging

- [ ] Uses unconditional `git add` (not conditional on `git diff`)
- [ ] Tests first-time setup (file doesn't exist yet)
- [ ] Tests modification (file exists and changed)
- [ ] Tests idempotent (file unchanged, run twice)

---

### Skill-Integration-Testing-Scenarios-001

**Statement**: Integration tests must include first-time setup scenario where config files don't exist yet

**Context**: When writing integration tests for automation that generates or synchronizes configuration files, especially in pre-commit hooks or setup scripts

**Evidence**: PR #52 Issue 1: Implementation assumed mcp.json always exists. No first-time setup test meant git diff --quiet bug not caught.

**Atomicity**: 95%

**Tag**: helpful

**Impact**: 10/10

**Created**: 2025-12-17

**Validated**: 1 (PR #52)

**Checklist**:

- Test when config file doesn't exist
- Test when config file exists but is empty
- Test when config file exists and is valid

## Formal Skills

### Skill-Git-Hook-Staging-001

**Statement**: For pre-commit hooks: prefer unconditional `git add` over conditional checks - git add is idempotent and handles new/modified/unchanged files

**Context**: When writing pre-commit hook file staging logic, especially for auto-generated files that may not exist on first run

**Evidence**: PR #52 Issue 1: `git diff --quiet` doesn't detect untracked files, causing first-time mcp.json creation to not be staged. Fixed with unconditional git add.

**Atomicity**: 92%

**Tag**: helpful

**Impact**: 9/10

**Created**: 2025-12-17

**Validated**: 1 (PR #52)

**Antipattern**: Using `git diff --quiet` before `git add` to check if file changed

## Related

- ADR-004: Pre-commit hook architecture
