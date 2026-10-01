# A sticky CodeRabbit changes-requested review clears with an approve command

## What happens

CodeRabbit leaves a changes-requested review on a PR. Pushing fixes and resolving its threads does not always clear that state. The PR stays blocked on the stale review.

## Practice

After CodeRabbit posts a clean incremental review of the fix, comment `@coderabbitai approve` on the PR. That clears the sticky state. Post it only after the incremental review is clean.

## Source

Observed by Richard during the P1 triage session 2026-09-29. Not re-derived from CodeRabbit documentation.
