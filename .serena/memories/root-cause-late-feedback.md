# Root Cause Pattern: Late Feedback Loop

**Pattern ID**: RootCause-Process-002
**Category**: Shift-Left Failure
**Created**: 2026-01-15
**Source**: PR #908 Comprehensive Retrospective

## Description

Issues discovered in CI (CodeQL, session validation) that should have been caught locally
before push. Creates noise in PR, wastes review cycles, delays feedback to 10-30 minutes
instead of 10-30 seconds.

## Detection Signals

- Security findings appear in PR checks, not pre-commit
- Session validation fails in CI, not locally
- Lint errors caught in CI, not in editor
- "Fix CI failures" commits after PR creation
- Multiple CI-fix commits in PR history

## Prevention Skills

- **Skill-Shift-Left-Validation-001**: Before push, run local subset: CodeQL critical rules,
  session validation, markdownlint, Pester tests
- **Skill-Security-Pre-Push-001**: Local security scanning added to session protocol

## Evidence from PR #908

- **Incident**: PR #908 CodeQL findings (CWE-22 path traversal) discovered in CI
- **Root Cause Path**:
  - Q1: Why CodeQL findings in CI? → Not run locally
  - Q2: Why not run locally? → CodeQL is CI-only tool
  - Q3: Why CI-only? → Assumed CI sufficient
  - Q4: Why assume CI sufficient? → No "clean PR" requirement
  - Q5: Why no requirement? → Prioritized speed over quality
- **Resolution**: Added local security scanning to session protocol

## Related Patterns

- **Similar to**: RootCause-Fail-Safe-003 (bypassing hooks with --no-verify)
- **Related to**: RootCause-Process-001 (Governance Without Enforcement)
- **Related to**: RootCause-Process-003 (Scope Creep via Tool Side Effects)
- **Case Study**: PR #908 (https://github.com/rjmurillo/ai-agents/pull/908)

## References

- `.agents/retrospective/2026-01-15-pr-908-comprehensive-retrospective.md` (lines 1038-1078)
- PR: https://github.com/rjmurillo/ai-agents/pull/908
