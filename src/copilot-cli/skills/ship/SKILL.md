---
name: ship
description: Ship it. Pre-flight validation, CI check, and PR creation. Run after /review.
argument-hint:
  - target-branch
allowed-tools: Task, Skill, Read, Glob, Grep, Bash(*)
user-invocable: true
---

@CLAUDE.md

Ship: $ARGUMENTS

Default target is main unless specified. If $ARGUMENTS names a different branch, use that as the target.

## Pre-flight Checks

Task(subagent_type="devops"): You are a release engineer. Run all 4 pre-flight checks below. Report pass/fail for each with specific evidence. Any failure blocks shipping.

1. **Pipeline health** - Invoke Skill(skill="pipeline-validator"). All CI checks green? No suppressed failures?
2. **Security posture** - Invoke Skill(skill="security-scan"). No new CWE findings? No secrets in diff?
3. **Reviewed on this SHA** - The shipped code must carry a SHA-bound `/review` PASS marker (Issue #1938). Run the review-skill validator:
   - If `CLAUDE_SKILL_DIR` is set: `python3 "$CLAUDE_SKILL_DIR/../review/scripts/validate_review_marker.py" --ref HEAD --repo-root "$(pwd)"`
   - Source checkout fallback: `python3 .claude/skills/review/scripts/validate_review_marker.py --ref HEAD --repo-root "$(pwd)"`
   - Vendored plugin fallback: `python3 skills/review/scripts/validate_review_marker.py --ref HEAD --repo-root "$(pwd)"`

   The validator exits `0` only when HEAD is a `/review` marker commit whose `Reviewed-By: /review@<axes> on <sha>` trailer binds the reviewed tip (its parent). Exit `1` means no marker, a stale marker, or new code landed after review; exit `2` is a config error. On any non-zero exit, this check FAILS: run `/review` on this branch (it writes the marker on a PASS verdict), then re-run `/ship`. This replaces the old "has /review been run somewhere?" check with proof it passed on the exact code being shipped. Because `/review` is the strict superset of CI (Child 1 #1934), a passing marker covers golden-principles, taste-lints, and code-quality too; there is no separate standards check.
4. **Tests passing** - All tests green? No skipped tests without justification?

> `golden-principles` + `taste-lints` + `code-quality` are now part of `/review` (Child 1 #1934), so `/ship` does not invoke them separately. `/pr-quality:all` is likewise no longer a required separate step before `/ship`: a passing `/review` marker (check 3) already runs the same canonical axes locally, and CI runs the same prompts as a backstop.

## Process

1. Run all 4 pre-flight checks
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
  Reviewed:  PASS|FAIL (SHA-bound /review marker on HEAD; evidence)
  Tests:     PASS|FAIL (evidence)

RESULT: SHIPPED|BLOCKED
PR: [link if created]
WARNINGS: [non-blocking concerns]
NEXT: [monitoring, follow-up items]
```
