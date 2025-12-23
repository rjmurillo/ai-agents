# Git Hook Skills

**Created**: 2025-12-23 (consolidated from 4 memories)
**Sources**: PR #52, ADR-004, Session protocol retrospectives
**Skills**: 6

---

## Part 1: Pre-Commit Architecture (ADR-004)

**Categories**:

| Category | Behavior | Exit Code | Example |
|----------|----------|-----------|---------|
| BLOCKING | Fail commit on error | Non-zero | Syntax validation |
| WARNING | Warn but allow commit | Zero | Security detection |
| AUTO-FIX | Auto-fix then stage | Zero | Markdown lint, MCP sync |

**Design Principles**:
- Fail-fast for critical issues (invalid JSON, syntax errors)
- Warn-only for advisory (planning, security)
- Auto-fix when deterministic (markdown lint, config transforms)
- Security-hardened (symlink rejection, path validation)

**When to use pre-commit vs CI**:
- Pre-commit: Fast (<2s), local-only, auto-fixable, non-destructive
- CI: Slow, network-dependent, complex analysis, security-sensitive

---

## Part 2: AUTO-FIX Pattern

```bash
# At top of hook
AUTOFIX=1
if [ "${SKIP_AUTOFIX:-}" = "1" ]; then
    AUTOFIX=0
    echo "Auto-fix disabled (SKIP_AUTOFIX=1)"
fi

# In AUTO-FIX section
if [ "$AUTOFIX" = "1" ]; then
    if fix_tool "$FILES"; then
        git add -- "$FILES"  # git add is idempotent
        echo "Fixed and staged: $FILES"
    fi
fi
```

**Key**: Respect `SKIP_AUTOFIX` for CI "check only" mode.

---

## Part 3: Cross-Language Integration (Bash → PowerShell)

```bash
SCRIPT="$REPO_ROOT/scripts/Script.ps1"

# Security: Reject symlinks
if [ -L "$SCRIPT" ]; then
    echo "Warning: Script is a symlink"
else
    OUTPUT=$(pwsh -NoProfile -File "$SCRIPT" -PassThru 2>&1)
    EXIT_CODE=$?
    
    if [ $EXIT_CODE -eq 0 ]; then
        # Use anchored grep for exact match
        if echo "$OUTPUT" | grep -q '^True$'; then
            FILES_FIXED=1
        fi
    fi
fi
```

**CRITICAL**: PowerShell `return` exits with code 0. Use `exit N` for explicit exit codes.

---

## Part 4: Grep Pattern Best Practices

**Anti-Pattern**:
```bash
if echo "$OUTPUT" | grep -q "True"; then  # BUG: substring match
```

**Problem**: Matches "True" in paths like `/Users/TrueUser/repo/file.json`

**Solution**: Anchored patterns for exact matches:
```bash
if echo "$OUTPUT" | grep -q '^True$'; then  # FIXED: exact line match
```

**Best Practices**:
- `grep -E '\.md$'` - Match file extensions
- `grep -q '^True$'` - Match exact boolean
- `grep -E '^[^/]'` - Match non-path lines

---

## Part 5: Security - TOCTOU Defense

**Problem**: Time-of-check to time-of-use race condition when security check runs in child process but action runs in parent.

**Anti-Pattern**:
```bash
RESULT=$(pwsh -File sync-script.ps1)  # Symlink check in PowerShell
git add -- "$FILE"                     # Action in bash - RACE WINDOW
```

**Solution**: Defense-in-depth - re-validate in same process as action:
```bash
RESULT=$(pwsh -File sync-script.ps1)  # First check
if [ -L "$FILE" ]; then               # Defense-in-depth in bash
    echo "Error: symlink detected"
else
    git add -- "$FILE"                # Action in same process as check
fi
```

**Security Checklist**:
- [ ] Use `-NoProfile` with pwsh
- [ ] Reject symlinks (MEDIUM-002)
- [ ] Validate paths exist before use
- [ ] Quote all variables
- [ ] Use `--` separator for arguments

---

## Part 6: Session Validation Hook

**Skill-Git-001**: Block commit if `Validate-SessionEnd.ps1` exits non-zero

**Evidence**: 91.7% (22/24) sessions closed without committing - no technical gate prevented this.

**Implementation**:
```bash
#!/bin/bash
# .git/hooks/pre-commit

SESSION_LOG=$(find .agents/sessions -name "$(date +%Y-%m-%d)-session-*.md" \
    -type f -printf '%T@ %p\n' | sort -rn | head -1 | cut -d' ' -f2)

if [ -n "$SESSION_LOG" ]; then
    pwsh -File scripts/Validate-SessionEnd.ps1 -SessionLogPath "$SESSION_LOG"
    if [ $? -ne 0 ]; then
        echo "❌ COMMIT BLOCKED: Session End checklist incomplete"
        exit 1
    fi
fi
```

**Atomicity**: 96% | **Impact**: 10/10 | **Tag**: CRITICAL

---

## Quick Reference

| Skill | When to Use |
|-------|-------------|
| Part 1 | Deciding blocking level for new validation |
| Part 2 | Adding auto-fix capability to hook |
| Part 3 | Calling PowerShell from bash hook |
| Part 4 | Parsing command output with grep |
| Part 5 | Any security check before file operation |
| Part 6 | Session protocol enforcement |

## Common Pitfalls

| Pitfall | Solution |
|---------|----------|
| Pattern blindness | `grep -n "AUTOFIX" .githooks/pre-commit` before adding |
| PowerShell return semantics | Use `exit 1` not `return $false` |
| Untracked file detection | Use unconditional `git add` (idempotent) |
| grep false positives | Use `^pattern$` for exact match |

## Related Files

- `.githooks/pre-commit` - Main hook implementation
- `.agents/architecture/ADR-004-pre-commit-hook-architecture.md`
- `scripts/Validate-SessionEnd.ps1` - Session validation script
- `scripts/Sync-McpConfig.ps1` - MCP config sync script
