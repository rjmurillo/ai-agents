# Copilot SWE Anti-Patterns

**Created**: 2025-12-25
**Evidence**: PR #395 failure analysis

## Overview

Documented patterns of Copilot SWE (Sonnet 4.5) failures and how to prevent them.

## Anti-Pattern 1: Scope Explosion

**Symptom**: 17x more lines changed than needed
**Cause**: Ambiguous prompt without constraints
**Example**: "Debug" interpreted as "fix everything"

**Prevention**:
- Include maximum line count in prompt
- Require investigation report before changes
- Add explicit prohibitions ("do not remove code")

## Anti-Pattern 2: Discovery-Driven Expansion

**Symptom**: Finds unrelated issues, expands to fix them
**Cause**: No boundary between investigation and implementation
**Example**: Found "dead code" (lock functions), removed them

**Prevention**:
- Two-phase approach: investigate THEN propose
- Document discoveries, defer fixes
- Explicit: "Do not fix issues outside original scope"

## Anti-Pattern 3: Test Mutation

**Symptom**: Tests "fixed" to match broken code
**Cause**: Code-first mindset, tests seen as implementation detail
**Example**: 6 tests modified to accept new API

**Prevention**:
- Block: "Do not modify tests during refactoring"
- Instruct: "If tests fail, revert code change"
- Exception: Only TDD context allows test changes first

## Anti-Pattern 4: Breaking API Changes

**Symptom**: Function return types changed without migration
**Cause**: Optimization/cleanup without considering consumers
**Example**: `Test-RateLimitSafe` changed from boolean to hashtable

**Prevention**:
- Explicit: "Do not change function signatures"
- Require deprecation path for API changes
- Run all consumers to verify compatibility

## Anti-Pattern 5: Documentation Inflation

**Symptom**: ADRs, session logs for minor fixes
**Cause**: Over-documentation of small changes
**Example**: ADR-022 created for logging enhancement

**Prevention**:
- ADRs only for architectural decisions
- Session logs only for significant sessions
- Minimal documentation for minimal changes

## Anti-Pattern 6: User Signal Ignoring

**Symptom**: Continues approach after explicit feedback
**Cause**: Sunk cost, commitment to current direction
**Example**: "YAGNI" comment ignored, expansion continued

**Prevention**:
- YAGNI/KISS = immediate stop
- "Less is more" = revert and minimize
- User pushback = pause and reassess

## Anti-Pattern 7: No Verification

**Symptom**: Shipped code that crashes on startup
**Cause**: No execution before commit
**Example**: `Write-Log ""` crashes but never run locally

**Prevention**:
- Require: "Run script/tests before committing"
- Add syntax validation step
- Verify baseline still works after changes

## Quick Reference

| Anti-Pattern | Detection | Prevention |
|--------------|-----------|------------|
| Scope Explosion | >100 lines for minor fix | Max line limit in prompt |
| Discovery Expansion | Unrelated fixes | Two-phase investigate/fix |
| Test Mutation | Tests changed with code | Block test changes in refactoring |
| Breaking API | Signature changes | Require deprecation path |
| Doc Inflation | ADR for small fix | ADRs for arch decisions only |
| Signal Ignoring | Continues after YAGNI | Immediate stop on pushback |
| No Verification | Crashes on run | Execute before commit |

## Related Memories

- skill-scope-002-minimal-viable-fix
- skill-prompt-002-copilot-swe-constraints
- agent-workflow-scope-discipline
