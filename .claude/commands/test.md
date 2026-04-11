---
description: Prove it works. Run layered tests and debug failures with hypothesis-driven investigation. Run after /build.
allowed-tools: Task, Skill, Read, Write, Edit, Glob, Grep, Bash(git diff:*), Bash(git status:*), Bash(python3:*), Bash(pytest:*), Bash(npm test:*)
argument-hint: [component-or-failure-description]
---

@CLAUDE.md

Invoke the code-qualities-assessment and quality-grades skills.

Test: $ARGUMENTS

Use Task(subagent_type="qa") as the primary agent. For security testing, also invoke Task(subagent_type="security"). If no argument provided, test the current branch diff against main.

Evaluate across all 5 axes:

1. **Unit coverage** - Each method in isolation, dependencies injected
2. **Integration coverage** - Contracts between components verified
3. **Acceptance coverage** - Each requirement has a passing test
4. **Security coverage** - OWASP top 10 scenarios exercised
5. **Failure coverage** - Error paths tested, chaos hypotheses validated

## Principles

- **Testability is design feedback**: Hard to test means poor encapsulation, tight coupling, Law of Demeter violation, weak cohesion, or procedural code.
- **Tests are proof**: A passing test is evidence. A missing test is a gap in knowledge.
- **Hypothesis-driven debugging**: When a test fails, form a hypothesis before changing code. Verify the hypothesis. Then fix.

## Process

1. Identify what changed (git diff against main)
2. Map changes to test coverage: which tests cover this code?
3. Run existing tests first (catch regressions)
4. Identify coverage gaps: new code paths without tests
5. Write missing tests (unit first, then integration)
6. For failures: hypothesis, verify, fix (never change code without understanding why)
7. Run security-scan for CWE patterns
8. Report: passing, failing, gaps, recommendations

## Output

Structured test report:

- Tests run (count, pass/fail)
- Coverage gaps (specific files and functions)
- Security findings (CWE references)
- Recommendations (what to add, what to fix)
