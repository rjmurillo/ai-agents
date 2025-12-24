# Utility Skills

Category: Automation Tools and Scripts
Source: `.claude/skills/fix-markdown-fences/SKILL.md`
Migrated: 2025-12-13

## Skill-Utility-001: Fix Markdown Code Fence Closings

- **Atomicity**: 92%
- **Location**: `.claude/skills/fix-markdown-fences/`
- **Implementations**: Python (`fix_fences.py`), PowerShell (`fix_fences.ps1`)

### Problem

When generating markdown with code blocks, closing fences sometimes include language identifiers:

```markdown
<!-- Wrong -->
` ` `python
def hello():
    pass
` ` `python  <!-- Should be just ``` -->

<!-- Correct -->
` ` `python
def hello():
    pass
` ` `
```

### When to Use

1. After generating markdown with multiple code blocks
2. When fixing existing markdown files with rendering issues
3. When code blocks appear to "bleed" into surrounding content
4. As a validation step before committing markdown documentation

### Algorithm

1. **Opening fence**: Line matches `^\s*` ` `\w+` and not inside block. Enter "inside block" state.
2. **Malformed closing fence**: Line matches `^\s*` ` `\w+` while inside block. Insert proper closing fence before this line.
3. **Valid closing fence**: Line matches `^\s*` ` `\s*$`. Exit "inside block" state.
4. **End of file**: If still inside block, append closing fence.

### Usage

```bash
# PowerShell
pwsh .claude/skills/fix-markdown-fences/fix_fences.ps1

# Python
python .claude/skills/fix-markdown-fences/fix_fences.py
```

### Edge Cases Handled

- Nested indentation: Preserves indent level from opening fence
- Multiple consecutive blocks: Each block tracked independently
- File ending inside block: Automatically closes unclosed blocks
- Mixed line endings: Handles both `\n` and `\r\n`

### Prevention

When generating markdown with code blocks:

1. Always use plain ` ` ` for closing fences
2. Never copy the opening fence line to close
3. Track block state when programmatically generating markdown

---

## Skill-Utility-002: Pre-commit Hook Auto-Fix

- **Atomicity**: 90%
- **Location**: `.githooks/pre-commit`

### Purpose

Automatically fixes markdown linting issues and re-stages corrected files before commit.

### Features

- Runs `markdownlint-cli2 --fix` on staged markdown files
- Automatically re-stages corrected files
- Blocks commit only if unfixable violations remain
- Bypass with `SKIP_AUTOFIX=1` or `--no-verify`

### Setup

```bash
git config core.hooksPath .githooks
```

### Security Features

- Uses arrays and proper quoting to prevent command injection
- Handles filenames with spaces safely
- Checks for symlinks to prevent TOCTOU attacks
- Prefers local installation over npx for dependency security

---

## Skill-Utility-003: Security Pattern Library (88%)

**Statement**: Maintain regex patterns for common vulnerabilities in automated scans

**Context**: Automated security scans, PR gates, pre-commit hooks

**Evidence**: Security detection utility with pattern library

**Atomicity**: 88%

**Tag**: helpful

**Impact**: 8/10

**Location**: `.claude/skills/security-detection/`

**Pattern Categories**:

- Hardcoded credentials (API keys, passwords, tokens)
- SQL injection vectors
- XSS vulnerability patterns
- Insecure deserialization
- Path traversal attempts

**Usage**:

```bash
# Run security pattern scan
pwsh .claude/skills/security-detection/scan.ps1 -Path ./src
```

**Source**: `.claude/skills/security-detection/SKILL.md`

---

## Skill-Utility-004: PowerShell PathInfo String Conversion (94%)

**Statement**: Use `(Resolve-Path $Path).Path` or `[string]` cast when string operations needed on resolved path

**Context**: PowerShell scripts using Resolve-Path output for string operations like .Length, -match, or concatenation

**Evidence**: PR #47 - `Resolve-Path` returns PathInfo object, `.Length` returned null without conversion; bug fixed with `.Path` property

**Atomicity**: 94%

**Tag**: helpful

**Impact**: 8/10

**Problem**:

```powershell
# WRONG - PathInfo object doesn't support string operations
$resolvedPath = Resolve-Path ".\relative\path"
$pathLength = $resolvedPath.Length  # Returns NULL - PathInfo has no .Length property
$isMatch = $resolvedPath -match "pattern"  # Type mismatch error
```

**Solution**:

```powershell
# CORRECT - Convert PathInfo to string first
$resolvedPath = (Resolve-Path ".\relative\path").Path  # Extract .Path property
$pathLength = $resolvedPath.Length  # Works - now a string
$isMatch = $resolvedPath -match "pattern"  # Works

# Alternative: Explicit cast
$resolvedPath = [string](Resolve-Path ".\relative\path")
$pathLength = $resolvedPath.Length  # Also works
```

**Detection**: String operation on Resolve-Path result returns null or type error

**Anti-Pattern**: Direct use of Resolve-Path output in string operations without conversion

**Validation**: 1 (PR #47 - cursor[bot] detected bug)

---

## Related Documents

- Source: `.claude/skills/fix-markdown-fences/SKILL.md`
- Source: `.claude/skills/security-detection/SKILL.md`
- Related: skills-security (security best practices)
