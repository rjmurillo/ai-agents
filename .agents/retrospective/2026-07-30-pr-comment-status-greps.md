# Retrospective: PR Comment Status Greps

## Context
Issue #4034 exposed dead verification greps in pr-comment-responder. The comment-map detail field emits `**Status**: [VALUE]`, while the gates searched for `Status: [VALUE]`.

## What Changed
- Added a regression test that proves the old grep pattern returns 0 and the anchored bold-field pattern counts emitted statuses.
- Updated shared, hand-maintained, generated, and skill-reference carriers.
- Regenerated platform mirrors and bumped affected plugin manifests.

## Learnings Captured
- Prompt-contract bugs need tests that execute the documented shell regex behavior, not only source-string checks.
- Markdown table cells should avoid raw `|` inside inline code; use separate `grep -e` arguments when documenting alternatives.
