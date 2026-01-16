# Skill Observations: security

**Last Updated**: 2026-01-16
**Sessions Analyzed**: 1

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

## Preferences (MED confidence)

These are preferences that SHOULD be followed:

- Version comments after SHA improve maintainability without sacrificing security (e.g., @SHA # v4) (Session 2026-01-16-session-07, 2026-01-16)
- Cross-platform regex patterns using POSIX-compatible syntax ([[:space:]]) (Session 2026-01-16-session-07, 2026-01-16)
- Security scanning in CI should be blocking for critical findings (Session 2026-01-16-session-07, 2026-01-16)

## Edge Cases (MED confidence)

These are scenarios to handle:

## Notes for Review (LOW confidence)

These are observations that may become patterns:

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
