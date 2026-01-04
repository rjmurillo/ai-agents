# Security: Path Injection Prevention via Anchoring

**Date**: 2026-01-04
**Context**: PR #760 CodeQL path injection fixes (CWE-22)
**Atomicity**: 91%

## The Pattern

Path injection prevention requires anchoring relative paths to trusted base BEFORE resolving.

### Incorrect Pattern (Vulnerable)

```python
def validate_path_safety(path_str: str, allowed_base: Path) -> bool:
    # Validate string
    if '..' in path_str:
        return False
    
    # WRONG: Resolve before anchoring
    resolved = Path(path_str).resolve()  # Absolute paths bypass anchor!
    resolved.relative_to(allowed_base)
    return True
```

**Vulnerability**: Absolute paths like `/etc/passwd` resolve directly, bypassing containment check.

### Correct Pattern (Secure)

```python
def validate_path_safety(path_str: str, allowed_base: Path) -> bool:
    base = allowed_base.resolve()
    candidate = Path(path_str)
    
    # CORRECT: Anchor relative paths BEFORE resolving
    if candidate.is_absolute():
        resolved = candidate.resolve()  # Absolute: validate containment
    else:
        resolved = (base / candidate).resolve()  # Relative: anchor first
    
    resolved.relative_to(base)  # Verify containment
    return True
```

**Security**: Relative paths anchored to trusted base, absolute paths validated for containment.

## Why It Works

### Absolute Path Attack

**Input**: `/etc/passwd`
**Incorrect**: `Path('/etc/passwd').resolve()` → `/etc/passwd` (outside allowed base)
**Correct**: Detected as absolute, validated for containment, rejected

### Relative Path Attack

**Input**: `../../etc/passwd`
**Incorrect**: `Path('../../etc/passwd').resolve()` → `/etc/passwd` (outside allowed base)
**Correct**: `(base / '../../etc/passwd').resolve()` → still within base due to anchor

### The Critical Difference

**Key Insight**: `Path.resolve()` behavior differs for absolute vs relative paths:
- Relative paths: Resolve relative to CWD (not necessarily safe)
- Absolute paths: Resolve to themselves (bypass anchor)

**Solution**: Anchor relative paths to trusted base BEFORE resolving.

## Evidence from PR #760

### Commit c46a4ca (Incorrect Pattern)

```python
# Pre-resolution check
if '..' in path_str:
    return False

resolved_path = Path(path_str).resolve()  # Absolute bypass!
resolved_path.relative_to(allowed_base)
```

**Flaw**: Missed absolute path bypass (e.g., `/tmp/evil`)

### Commit ddf7052 (Correct Pattern)

```python
candidate = Path(path_str)

if candidate.is_absolute():
    resolved_path = candidate.resolve()
else:
    resolved_path = (base / candidate).resolve()  # Anchor first!

resolved_path.relative_to(base)
```

**Fix**: Absolute paths validated, relative paths anchored before resolution.

## Testing Protocol

### Test Cases (Adversarial)

1. **Relative with `..`**: `../../etc/passwd` → Should reject (escapes base)
2. **Absolute outside base**: `/etc/passwd` → Should reject (not in base)
3. **Absolute inside base**: `/home/user/repo/file.txt` → Should accept (if base is `/home/user/repo`)
4. **Symlink attack**: `symlink -> /etc/passwd` → Should reject (resolved path outside base)
5. **Windows path**: `C:\Windows\System32` → Should reject (not in base)

### Required Test Coverage

For any path validation function:
- [ ] Test with relative path containing `..`
- [ ] Test with absolute path outside base
- [ ] Test with absolute path inside base
- [ ] Test with symlink (if filesystem supports)
- [ ] Test with Windows absolute path (if cross-platform)

## Required Parameters

**CRITICAL**: `allowed_base` parameter must be REQUIRED, not optional.

**Wrong**:
```python
def validate_path_safety(path_str: str, allowed_base: Path = None):
    if allowed_base is None:
        allowed_base = Path.cwd()  # Dangerous assumption!
```

**Right**:
```python
def validate_path_safety(path_str: str, allowed_base: Path):
    # Caller MUST specify trusted base explicitly
    base = allowed_base.resolve()
```

**Rationale**: Defaulting to `Path.cwd()` makes assumptions about execution context. Explicit is safer.

## Implementation Checklist

When adding path validation:
- [ ] `allowed_base` parameter is REQUIRED (no default)
- [ ] Handle absolute vs relative paths differently
- [ ] Anchor relative paths: `(base / candidate).resolve()`
- [ ] Validate absolute paths: `candidate.resolve().relative_to(base)`
- [ ] Test with adversarial inputs (see Test Cases above)
- [ ] Document WHY pattern works in code comments

## Related Skills

- security-011-adversarial-testing-protocol (test with malicious inputs)
- security-002-input-validation-first (validate before processing)
- security-013-no-blind-suppression (never suppress without understanding)

## Cross-Reference

- Retrospective: `.agents/retrospective/2026-01-04-pr760-security-suppression-failure.md`
- PR: #760
- Commits: c46a4ca (incorrect), ddf7052 (correct)
