# Skill-security-014: Path Anchoring Pattern

**Statement**: Path injection prevention requires anchoring relative paths: (base / path).resolve() not Path(path).resolve().

**Context**: Absolute paths bypass validation when resolved directly. Anchor relative paths to trusted base first, then resolve. This prevents absolute path bypasses of path containment checks.

**Evidence**: PR #760 commit c46a4ca used `Path(user_input).resolve()` after validation, allowing absolute paths to bypass. Commit ddf7052 fixed with `(allowed_base / user_input).resolve()` pattern. The difference: `/etc/passwd` resolves to `/etc/passwd` when direct, but (base / `/etc/passwd`) anchors it to base first.

**Atomicity**: 91% | **Impact**: 9/10

## Pattern

Correct path injection prevention (Python):

```python
from pathlib import Path

allowed_base = Path("/home/user/files")
user_input = request.args.get('path')

# CORRECT: Anchor first, then resolve
resolved_path = (allowed_base / user_input).resolve()

# Verify path is within base after resolution
if not str(resolved_path).startswith(str(allowed_base.resolve())):
    raise SecurityError("Path traversal attempt detected")

# Now safe to use resolved_path
```

Why this works:
- `(allowed_base / "/etc/passwd")` attempts to make `/etc/passwd` relative to base
- `.resolve()` normalizes the path, showing the attempt
- Containment check fails because absolute path is outside base

## Anti-Pattern

Never do:

```python
# WRONG: Validates then resolves absolute path unanchored
if validate_path_safety(user_input):
    resolved_path = Path(user_input).resolve()  # Absolute paths bypass!
```

This allows `/etc/passwd` or `C:\Windows\System32` to bypass the validation entirely.

## Related

- [security-002-input-validation-first](security-002-input-validation-first.md)
- [security-003-secure-error-handling](security-003-secure-error-handling.md)
- [security-004-security-event-logging](security-004-security-event-logging.md)
- [security-007-defense-in-depth-for-cross-process-security-checks](security-007-defense-in-depth-for-cross-process-security-checks.md)
- [security-008-first-run-gap-analysis](security-008-first-run-gap-analysis.md)
