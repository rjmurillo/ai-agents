---
description: Ship it. Pre-flight validation, CI check, and PR creation. Run after /review.
allowed-tools: Task, Skill, Read, Glob, Grep, Bash(git diff:*), Bash(git log:*), Bash(git status:*), Bash(git push:*), Bash(python3:*)
argument-hint: [target-branch]
---

Invoke the pipeline-validator and validate-pr-description skills.

Ship the current branch: $ARGUMENTS

Use Task(subagent_type="devops") as the primary agent. Default target is main unless specified.

Pre-flight checks (all must pass):

1. **Pipeline health** - All CI checks green? No suppressed failures? Run pipeline-validator.
2. **Security posture** - Final security-scan clean? No new CWE findings? No secrets in diff?
3. **Review complete** - Has /review been run? Any unresolved Critical findings?
4. **Tests passing** - All tests green? No skipped tests without justification?
5. **Standards clean** - Golden principles and taste lints pass?

## Principles

- **Faster is safer**: Small, frequent shipments reduce blast radius. Ship early.
- **No deliberate debt**: If it is not ready, do not ship it. Fix it or defer it.
- **Observability first**: If you cannot measure it, you cannot ship it safely.

## Process

1. Run pre-flight checks (all 5 above)
2. If any check fails: report what failed, why, and how to fix. Stop.
3. If all pass: validate PR description (invoke validate-pr-description skill)
4. Create PR via /push-pr delegation (invoke Skill tool with push-pr)
5. Report: what shipped, PR link, any warnings

## Output

Ship report:

- Pre-flight results (pass/fail per check)
- PR link (if created)
- Warnings (non-blocking concerns)
- Next steps (monitoring, follow-up items)
