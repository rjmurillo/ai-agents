# Git Hook Patterns

## Overview

Patterns and best practices for git hooks, particularly pre-commit hooks with bash and PowerShell integration.

---

## Pre-Commit Hook Architecture

### Section Categories (from ADR-004)

| Category | Behavior | Exit Code | Example |
|----------|----------|-----------|---------|
| BLOCKING | Fail commit on error | Non-zero | Syntax validation |
| WARNING | Warn but allow commit | Zero | Security detection |
| AUTO-FIX | Auto-fix then stage | Zero | Markdown lint, MCP sync |

### AUTO-FIX Pattern

```bash
# Check for files needing processing
STAGED_FILES=$(git diff --cached --name-only --diff-filter=ACM)

if [ -n "$STAGED_FILES_MATCHING_PATTERN" ]; then
    # CRITICAL: Respect SKIP_AUTOFIX for CI "check only" mode
    if [ "$AUTOFIX" = "1" ]; then
        echo "Auto-fixing files..."
        
        # Run fix tool
        if fix_tool "$FILES"; then
            # Stage fixed files (git add is idempotent)
            git add -- "$FILES"
            echo "Fixed and staged: $FILES"
            FILES_FIXED=1
        else
            echo "Warning: Fix failed"
        fi
    else
        echo "Auto-fix skipped (SKIP_AUTOFIX=1)."
    fi
fi
```

### AUTOFIX Variable Pattern

```bash
# At top of hook
AUTOFIX=1
if [ "${SKIP_AUTOFIX:-}" = "1" ]; then
    AUTOFIX=0
    echo "Auto-fix disabled (SKIP_AUTOFIX=1)"
fi

# Before any AUTO-FIX section
if [ "$AUTOFIX" = "1" ]; then
    # Auto-fix code here
fi
```

---

## Cross-Language Integration

### Bash Calling PowerShell

```bash
# Pattern for calling PowerShell with exit code checking
SCRIPT="$REPO_ROOT/scripts/Script.ps1"

# Security: Reject symlinks
if [ -L "$SCRIPT" ]; then
    echo "Warning: Script is a symlink"
else
    # Run with PassThru to capture boolean result
    OUTPUT=$(pwsh -NoProfile -File "$SCRIPT" -PassThru 2>&1)
    EXIT_CODE=$?
    
    if [ $EXIT_CODE -eq 0 ]; then
        # Check PassThru output for actual result
        if echo "$OUTPUT" | grep -q '^True$'; then
            echo "Files were modified"
            FILES_FIXED=1
        else
            echo "Already in sync"
        fi
    else
        echo "Script failed (exit code $EXIT_CODE)"
    fi
fi
```

### Exit Code Contract

| Exit Code | Meaning | Bash Check |
|-----------|---------|------------|
| 0 | Success | `if [ $? -eq 0 ]` |
| Non-zero | Failure | `if [ $? -ne 0 ]` |

**CRITICAL**: PowerShell `return` in script scope exits with code 0. Use `exit N` for explicit exit codes.

---

## Security Patterns

### Symlink Rejection (TOCTOU Defense)

```bash
# Check script path
if [ -L "$SCRIPT_PATH" ]; then
    echo "Warning: Rejecting symlink"
    exit 0  # Non-blocking warning
fi

# Check output file before staging
if [ -L "$OUTPUT_FILE" ]; then
    echo "Warning: Output is symlink, not staging"
else
    git add -- "$OUTPUT_FILE"
fi
```

### Path Validation

```bash
# Use -- to prevent path injection
git add -- "$FILE"

# Quote all paths
git diff --cached --name-only "$FILE"
```

---

## Testing Patterns

### Exit Code Testing (Pester)

```powershell
Describe "Exit Codes" {
    It "Returns non-zero on error" {
        & $scriptPath -SourcePath "nonexistent.json" 2>&1 | Out-Null
        $LASTEXITCODE | Should -Not -Be 0
    }
    
    It "Returns 0 on success" {
        & $scriptPath -SourcePath $validPath
        $LASTEXITCODE | Should -Be 0
    }
}
```

### Hook Testing (Manual)

```bash
# Test with auto-fix enabled (default)
git add . && git commit -m "test"

# Test with auto-fix disabled (CI mode)
SKIP_AUTOFIX=1 git add . && git commit -m "test"

# Test specific file patterns
echo "test" > test.md
git add test.md
git commit -m "test markdown"
```

---

## Common Pitfalls

### 1. Pattern Blindness

**Problem**: Adding new section without checking existing patterns
**Solution**: `grep -n "AUTOFIX" .githooks/pre-commit` before implementing

### 2. PowerShell Return Semantics

**Problem**: `return $false` exits with code 0 in script scope
**Solution**: Use `exit 1` directly for error paths

### 3. Untracked File Detection

**Problem**: `git diff --quiet` doesn't detect untracked files
**Solution**: Use unconditional `git add` (idempotent)

### 4. grep False Positives

**Problem**: `grep "True"` matches path containing "True"
**Solution**: Use `grep '^True$'` for exact match

---

## Related Memories

- `skills-bash-integration.md` - Atomic skills for bash integration
- `pr-52-retrospective-learnings.md` - Full retrospective with Five Whys analysis

---

*Last updated: 2025-12-17*
*Source: PR #52, ADR-004*
