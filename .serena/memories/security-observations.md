# Skill Observations: security

**Last Updated**: 2026-01-18
**Sessions Analyzed**: 4

## Purpose

This memory captures learnings from security patterns, vulnerability prevention, and secure coding practices across sessions.

## Constraints (HIGH confidence)

These are corrections that MUST be followed:

- SHA-pinning requirement for GitHub Actions - use commit SHAs not version tags to prevent supply chain attacks. Pattern: actions/checkout@34e114... not actions/checkout@v4 (Session 821, 2026-01-10)
  - Evidence: Implemented blocking validation in pre-commit hook with bash regex, created Validate-ActionSHAPinning.ps1 script, updated PROJECT-CONSTRAINTS.md and security-practices.md with SHA-pinning requirement
  - Enforcement: Pre-commit hook blocks commits with version tags using POSIX regex [[:space:]] pattern, CI validation with Validate-ActionSHAPinning.ps1 -CI flag

## Preferences (MED confidence)

These are preferences that SHOULD be followed:

- Path traversal prevention pattern: Use GetFullPath() + trailing separator check before StartsWith() comparison to prevent directory escape attacks (CWE-22) (Session 905, 2026-01-13)
  - Evidence: Export-ForgetfulMemories.ps1 implementation - normalizes paths with GetFullPath(), adds trailing separator to parent directory, then verifies child path starts with normalized parent to prevent `../` attacks
- Strict allowlist validation before path operations - validate input against explicit allowlist before constructing file paths to prevent injection attacks (Session 909, 2026-01-15)
  - Evidence: PR #908 review - Python hook enforced strict skill name allowlist before building .env file paths: `ALLOWED_SKILLS = {'session-init', 'merge-resolver', 'reflect', ...}` then validated skill_name in allowlist before `project_dir / '.env'` construction
- Security hardening for Python hooks - validate paths against safe base directory allowlist to prevent path traversal attacks (Session 2, 2026-01-15)
  - Evidence: Batch 37 - Python hook implementation with explicit path validation against allowlist before file operations
- CodeQL CLI requires zstd for extraction - add automatic dependency handling for extraction operations (Session 03, 2026-01-16)
  - Evidence: Batch 36 - CodeQL extraction failed without zstd dependency, added installation step

## Edge Cases (MED confidence)

These are scenarios to handle:

## Notes for Review (LOW confidence)

These are observations that may become patterns:

## History

| Date | Session | Type | Learning |
|------|---------|------|----------|
| 2026-01-10 | Session 821 | HIGH | SHA-pinning for GitHub Actions to prevent supply chain attacks |
| 2026-01-15 | Session 2 | HIGH | Security hardening for Python hooks with path allowlist |
| 2026-01-13 | Session 905 | MED | Path traversal prevention with GetFullPath() + trailing separator |
| 2026-01-15 | Session 909 | MED | Strict allowlist validation before path operations |
| 2026-01-16 | Session 03 | MED | CodeQL CLI requires zstd for extraction |

## Related

- [security-principles-owasp](security-principles-owasp.md)
- [security-validation-chain](security-validation-chain.md)
