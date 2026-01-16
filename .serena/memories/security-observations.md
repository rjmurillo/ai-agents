# Skill Observations: security

**Last Updated**: 2026-01-16
**Sessions Analyzed**: 3

## Purpose

This memory captures learnings from security practices, vulnerability assessments, and secure coding patterns across sessions.

## Constraints (HIGH confidence)

These are corrections that MUST be followed:

- All GitHub Actions must use commit SHA, never version tags (@v4, @v2, etc.) (Session 2026-01-16-session-07, 2026-01-16)
- SEMVER 2.0.0 comprehensive detection required for version tags (major, major.minor, major.minor.patch, prerelease, build) (Session 2026-01-16-session-07, 2026-01-16)
- Pre-commit hook + CI validation for defense in depth (Session 2026-01-16-session-07, 2026-01-16)
- Repeated constraint violations indicate insufficient enforcement - add blocking pre-commit hooks for documented read-only rules (Session 2026-01-16-session-07, 2026-01-16)
- Create reusable validation functions for repeated security patterns (Test-SafePath, ConvertTo-SafeShellArgument) - 9 security fixes for similar vulnerability classes indicate missing centralization (Session 2026-01-16-session-07, 2026-01-16)
- Bot-on-bot review loops must be prevented with actor filtering (github.actor != 'copilot[bot]' && github.actor != 'dependabot[bot]') (Session 2026-01-16-session-07, 2026-01-16)
- Pass date as parameter to hooks/scripts to prevent midnight race conditions - generate timestamp ONCE at workflow start (Session 2026-01-16-session-07, 2026-01-16)
- Silent catch blocks must include Write-Warning with error context - never swallow exceptions without logging (Session 2026-01-16-session-07, 2026-01-16)
- Convert paths to absolute at entry point using Resolve-Path or Join-Path with $PSScriptRoot - test scripts from multiple working directories (Session 2026-01-16-session-07, 2026-01-16)
- Validate file paths within repository root using git rev-parse --show-toplevel, allow test bypass with IS_TEST_ENVIRONMENT=1 (Session 2026-01-16-session-07, PR #715)
- Path injection prevention (CWE-22): Anchor BEFORE resolve using `(allowed_base / user_input).resolve()` not `Path(user_input).resolve()` then check containment. Absolute paths bypass unanchored resolution (Session 07, 2026-01-16)
  - Evidence: PR #760 - incorrect pattern allowed absolute paths to bypass anchor check, CodeQL flagged 11 issues, user-provided patches show correct pattern
- User frustration signals (WANTING TO SUPPRESS, patches PROVIDED) are BLOCKING - stop and clarify before continuing (Session 07, 2026-01-16)
  - Evidence: PR #760 - user perception of suppression attempt, frustration indicated approach failure, required explicit clarification

## Preferences (MED confidence)

These are preferences that SHOULD be followed:

- Version comments after SHA improve maintainability without sacrificing security (e.g., @SHA # v4) (Session 2026-01-16-session-07, 2026-01-16)
- Cross-platform regex patterns using POSIX-compatible syntax ([[:space:]]) (Session 2026-01-16-session-07, 2026-01-16)
- Security scanning in CI should be blocking for critical findings (Session 2026-01-16-session-07, 2026-01-16)

## Edge Cases (MED confidence)

- None yet

## Notes for Review (LOW confidence)

- None yet

## History

| Date | Session | Type | Learning |
|------|---------|------|----------|
| 2026-01-16 | 2026-01-16-session-07 | HIGH | All GitHub Actions must use commit SHA, never version tags |
| 2026-01-16 | 2026-01-16-session-07 | HIGH | SEMVER 2.0.0 comprehensive detection required |
| 2026-01-16 | 2026-01-16-session-07 | HIGH | Pre-commit hook + CI validation for defense in depth |
| 2026-01-16 | 2026-01-16-session-07 | HIGH | Repeated constraint violations indicate insufficient enforcement |
| 2026-01-16 | 2026-01-16-session-07 | HIGH | Create reusable validation functions for security patterns |
| 2026-01-16 | 2026-01-16-session-07 | HIGH | Bot-on-bot review loops prevention with actor filtering |
| 2026-01-16 | 2026-01-16-session-07 | HIGH | Pass date as parameter to prevent midnight race conditions |
| 2026-01-16 | 2026-01-16-session-07 | HIGH | Silent catch blocks must include Write-Warning |
| 2026-01-16 | 2026-01-16-session-07 | HIGH | Convert paths to absolute at entry point |
| 2026-01-16 | 2026-01-16-session-07 | HIGH | Validate file paths within repo root using git rev-parse, test bypass with env var |
| 2026-01-16 | Session 07 | HIGH | Path injection (CWE-22) prevention pattern: anchor before resolve |
| 2026-01-16 | Session 07 | HIGH | User frustration signals are BLOCKING - stop and clarify |
| 2026-01-16 | 2026-01-16-session-07 | MED | Version comments after SHA improve maintainability |
| 2026-01-16 | 2026-01-16-session-07 | MED | Cross-platform regex patterns using POSIX syntax |
| 2026-01-16 | 2026-01-16-session-07 | MED | Security scanning in CI should be blocking for critical findings |

## Related

- [security-002-input-validation-first](security-002-input-validation-first.md)
- [security-003-secure-error-handling](security-003-secure-error-handling.md)
- [security-007-defense-in-depth-for-cross-process-security-checks](security-007-defense-in-depth-for-cross-process-security-checks.md)
- [security-010-pre-commit-bash-detection](security-010-pre-commit-bash-detection.md)
- [security-011-workflow-least-privilege](security-011-workflow-least-privilege.md)
- [security-012-workflow-author-association](security-012-workflow-author-association.md)
