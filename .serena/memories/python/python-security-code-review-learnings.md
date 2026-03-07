# Python Security Code Review Learnings

**Last Updated**: 2026-01-14
**Session Reference**: 2026-01-14-session-02

## Purpose

Security patterns learned from reviewing and patching Python code. Load this memory when:

- Reviewing Python files for security vulnerabilities
- Implementing file system operations in Python
- Applying security patches to Python code

## Constraints (HIGH confidence)

None (no explicit user corrections in this session)

## Patterns (MEDIUM confidence)

### Defense-in-Depth Path Validation

**Statement**: Use multiple layers of validation for path inputs before any filesystem operations.

**Pattern Components**:

1. **Repository root constraint**: Define a safe base directory at module level
   ```python
   SAFE_BASE_DIR = Path(__file__).resolve().parents[2]
   ```

2. **Safe path validation function**: Validate paths against a safe root
   ```python
   def get_safe_project_path(project_dir: str) -> Optional[Path]:
       safe_root = Path(os.getenv("SAFE_ROOT", os.getcwd())).resolve()
       resolved_project = Path(project_dir).resolve()
       if not resolved_project.is_relative_to(safe_root):
           return None
       return resolved_project
   ```

3. **Local validation at entry points**: Re-validate before any filesystem operation
   ```python
   if '..' in user_input or '/' in user_input or '\\' in user_input:
       return False  # Reject path traversal attempts
   ```

4. **Fail-safe behavior**: Fall back to safe base directory on validation errors

**Evidence**: Multiple security patches showing layered validation in `invoke_skill_learning.py`:
- `SAFE_BASE_DIR` for repository root constraint
- `get_safe_project_path()` for safe path validation
- Local validation in `update_skill_memory()` before file operations

**Why This Works**: Each layer catches different attack vectors:
- Module-level constraint prevents escaping repository
- Safe path function validates against configurable root
- Local validation catches path traversal in parameters
- Fail-safe prevents errors from bypassing security

### Git Patch Workflow

**Statement**: When user provides patches in git diff format, use `git apply` to apply them.

**Pattern**:

```bash
# Check for conflicts first
git apply --check patch.diff

# Apply if no conflicts
git apply patch.diff
```

**Evidence**: User provided three patches in git diff format with explicit instruction to use "git apply"

**Anti-Pattern**: Manually copying patch content and editing files (error-prone, may miss changes)

## Notes for Review (LOW confidence)

### Iterative Security Improvements

**Observation**: Security patches often build on each other sequentially.

**Pattern**:
- Later patches may be redundant if earlier ones are comprehensive
- Check existing code before applying additional validation layers
- Prefer extending existing validation functions over adding new ones

**Evidence**: Third patch in session was rejected as redundant with existing implementation that already validated paths adequately.

**Recommendation**: Before adding new security checks:
1. Review existing validation in the function
2. Check if the attack vector is already covered
3. Consider whether consolidation is better than layering

## Related Memories

- [security-007-defense-in-depth-for-cross-process-security-checks](security-007-defense-in-depth-for-cross-process-security-checks.md)
- [security-002-input-validation-first](security-002-input-validation-first.md)
- [cwe-699-security-agent-integration](cwe-699-security-agent-integration.md)
- [powershell-security-ai-output](powershell-security-ai-output.md)

## CWE References

| CWE | Name | Relevance |
|-----|------|-----------|
| CWE-22 | Path Traversal | Primary focus of defense-in-depth pattern |
| CWE-23 | Relative Path Traversal | `..` sequence detection |
| CWE-36 | Absolute Path Traversal | Repository root constraint |
| CWE-73 | External Control of File Name | Input validation before file ops |
