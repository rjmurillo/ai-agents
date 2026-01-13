# Skill-security-011: Adversarial Testing Protocol

**Statement**: Test security fixes with malicious inputs before claiming complete: relative path with .., absolute path outside base, symlinks.

**Context**: Security fixes require adversarial testing with malicious inputs BEFORE claiming fix works. If fix only passes happy-path tests, absolute paths or symlink attacks may bypass the defense.

**Evidence**: PR #760 commit c46a4ca attempted path injection fix but missed absolute path bypass. Fix passed initial tests but failed when tested with `/etc/passwd` absolute paths. Commit ddf7052 fixed properly with `(allowed_base / user_path).resolve()` pattern and included path anchoring comments.

**Atomicity**: 95% | **Impact**: 9/10

## Pattern

For path injection vulnerabilities, ALWAYS test:

1. **Relative path with traversal**: `../../etc/passwd` or `..\\..\\windows\\system32`
2. **Absolute path outside base**: `/etc/passwd` or `C:\\Windows\\System32`
3. **Symlink attack**: If filesystem supports, verify symlink targets are validated
4. **Mixed case / encoding**: `../` vs `..%2F` (URL encoding bypass)
5. **Double encoding**: `..%252F` (double-encoded slash)

Document test results BEFORE claiming fix complete:
- Test case
- Input value
- Expected behavior (blocked or safe)
- Actual behavior
- Result: PASS or FAIL

## Anti-Pattern

Never claim security fix complete based on:
- CI checks pass
- Unit tests pass
- Code review approved

These don't verify defense against malicious inputs. Always add adversarial test cases that simulate attacker behavior.

## Related

- [security-002-input-validation-first](security-002-input-validation-first.md)
- [security-003-secure-error-handling](security-003-secure-error-handling.md)
- [security-004-security-event-logging](security-004-security-event-logging.md)
- [security-007-defense-in-depth-for-cross-process-security-checks](security-007-defense-in-depth-for-cross-process-security-checks.md)
- [security-008-first-run-gap-analysis](security-008-first-run-gap-analysis.md)
