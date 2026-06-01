---
description: Ship it. Pre-flight validation, CI check, and PR creation. Run after /review.
allowed-tools: Task, Skill, Read, Glob, Grep, Bash(*)
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
5. **Standards clean** - Invoke Skill(skill="golden-principles") and Skill(skill="taste-lints"), scoped to the PR diff. Both pass? Determine the PR base branch from `gh pr view --json baseRefName -q .baseRefName` (fall back to the ship target from $ARGUMENTS, default `main`, when no PR exists yet), store it in `BASE_BRANCH`, and pass it quoted so the gates scan only changed files:
   - `python3 .claude/skills/golden-principles/scripts/scan_principles.py --diff-scope "$BASE_BRANCH"`
   - `python3 .claude/skills/taste-lints/scripts/taste_lints.py --diff-scope "$BASE_BRANCH"`
   This keeps the gate blast radius equal to the diff, not the whole tree, so a pre-existing violation elsewhere does not block this ship.

## Process

1. Run all 5 pre-flight checks
2. If any check fails: report what failed, why, and how to fix. Stop.
3. If all pass: run /validate-pr-description to validate PR metadata
4. Create PR: run /push-pr to commit, push, and open PR
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
