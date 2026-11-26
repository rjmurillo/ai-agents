# Skill-security-014: Path Anchoring Pattern

**Statement**: Path injection prevention requires anchoring relative paths: (base / path).resolve() not Path(path).resolve().

**Context**: Absolute paths bypass validation when resolved directly. Anchor relative paths to trusted base first, then resolve. This prevents absolute path bypasses of path containment checks.

**Evidence**: PR #760 commit c46a4ca resolved user input after validation. Commit ddf7052 moved resolution under the allowed base. An absolute right operand replaces the base, so joining alone cannot constrain the result.

**Atomicity**: 91% | **Impact**: 9/10

## Pattern

Correct path injection prevention (Python):

```python
from pathlib import Path


class SecurityError(ValueError):
    """The requested path violates the allowed directory boundary."""


def resolve_user_path(allowed_base: Path, user_input: str) -> Path:
    base = allowed_base.resolve(strict=True)
    requested = Path(user_input)
    if not user_input.strip() or requested.anchor:
        raise SecurityError("Expected a nonempty relative path")

    resolved = (base / requested).resolve()
    if not resolved.is_relative_to(base):
        raise SecurityError("Path traversal attempt detected")
    return resolved
```

Why this works:
- Rejecting anchored operands keeps the trusted base in the join
- `.resolve()` normalizes `..` and follows symlinks that exist, so a link out of base resolves outside it
- `is_relative_to` compares path parts, so a sibling directory that shares
  the base name as a prefix still fails the check
- The check runs once: a link swapped in after it can still race the file open

## Anti-Pattern

Never do:

```python
# WRONG: Validates then resolves absolute path unanchored
if validate_path_safety(user_input):
    resolved_path = Path(user_input).resolve()  # Absolute paths bypass!
```

This allows `/etc/passwd` or `C:\Windows\System32` to bypass the validation entirely.

## Related

- [security-002-input-validation-first](security-002-input-validation-first-88.md)
- [security-003-secure-error-handling](security-003-secure-error-handling-90.md)
- [security-004-security-event-logging](security-004-security-event-logging-85.md)
- [security-007-defense-in-depth-for-cross-process-security-checks](security-007-defenseindepth-for-crossprocess-security-checks-94.md)
- [security-008-first-run-gap-analysis](security-008-firstrun-gap-analysis-91.md)
