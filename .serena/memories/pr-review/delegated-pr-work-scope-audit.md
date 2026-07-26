# Skill: Audit Delegated PR Work Before Acceptance

## Statement

Compare a delegated agent's changed files and completed actions with its assigned PR scope before accepting the result.

## Trigger

After any delegated PR review, CI fix, or thread-response task returns.

## Action

1. Inspect the agent result and `git status --short` or the branch diff.
2. Confirm every changed file supports the assigned PR action.
3. Isolate or discard unrelated artifacts before continuing.
4. Re-check the original completion condition, such as unresolved thread count.

## Evidence

PR #3348's responder was assigned the final review thread but created retrospective and Serena artifacts instead. The scope audit caught the diversion, preserved the existing `.serena/project.yml` change, and returned work to the remaining thread.

## Failure Mode

Maps to FM-7, Self-Contained Agent Delegation Failure. A delegate can return plausible output without completing the assigned action.

## Atomicity

**Score**: 96%

## Category

pr-comment-responder
