---
description: Ship it. Pre-flight validation, CI check, and PR creation. Run after /review.
allowed-tools: Task, Skill, Read, Glob, Grep, Bash(git diff:*), Bash(git log:*), Bash(git status:*), Bash(git push:*), Bash(gh:*), Bash(python3:*)
argument-hint: [target-branch]
---

@CLAUDE.md

Ship: $ARGUMENTS

Default target is main unless specified. If $ARGUMENTS names a different branch, use that as the target.

## Pre-flight Checks

Task(subagent_type="devops"): You are a release engineer. Run all 5 pre-flight checks below. Report pass/fail for each with specific evidence. Any failure blocks shipping.

1. **Pipeline health** - Invoke Skill(skill="pipeline-validator"). All CI checks green? No suppressed failures?
2. **Security posture** - Invoke Skill(skill="security-scan"). No new CWE findings? No secrets in diff?
3. **Review complete** - Has /review been run on this branch? Any unresolved Critical findings? Check review logs.
4. **Tests passing** - All tests green? No skipped tests without justification?
5. **Standards clean** - Invoke Skill(skill="golden-principles") and Skill(skill="taste-lints"). Both pass?

## Process

1. Run all 5 pre-flight checks
2. If any check fails: report what failed, why, and how to fix. Stop.
3. If all pass: invoke Skill(skill="validate-pr-description") to validate PR metadata
4. Create PR: invoke Skill(skill="push-pr") to commit, push, and open PR
5. Report: what shipped, PR link, any warnings

## Principles

- **Faster is safer**: Small, frequent shipments reduce blast radius. Ship early.
- **No deliberate debt**: If it is not ready, do not ship it. Fix it or defer it.
- **Observability first**: If you cannot measure it, you cannot ship it safely.

## Output

Ship report:

```text
PRE-FLIGHT:
  Pipeline:  PASS|FAIL (evidence)
  Security:  PASS|FAIL (evidence)
  Review:    PASS|FAIL (evidence)
  Tests:     PASS|FAIL (evidence)
  Standards: PASS|FAIL (evidence)

RESULT: SHIPPED|BLOCKED
PR: [link if created]
WARNINGS: [non-blocking concerns]
NEXT: [monitoring, follow-up items]
```
