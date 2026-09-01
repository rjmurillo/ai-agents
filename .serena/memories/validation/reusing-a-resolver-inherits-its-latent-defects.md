# Routing a second caller into a resolver inherits its latent defects

Source: issue #4635 / PR #5455 on 2026-09-01, `scripts/validation/check_push_lock_paths.py`.

Current behavior: the fix for #4635 routed a new input class (unfenced Markdown) through `_lock_targets`, the resolver the fenced path already used. That was the right structure, and it also doubled the reach of three defects the resolver already had. None of them were introduced by the change; all three surfaced in review of it.

Evidence, in the order review found them, each one granularity finer than the last:

- `_assignments` collapsed a block to one value per variable, so `$LOCK` resolved to the block's *last* assignment. A canonical rebind placed below a `flock` laundered the bad path that call actually opened; reversed, it condemned a canonical one. Fixed by keeping source order and resolving at the reading line.
- Line-level ordering left the same defect on a shared line: `flock "$LOCK" ; LOCK=...` resolved forward to an assignment that runs after the call. Fixed by ordering on `(line, column)`.
- `_ASSIGNMENT` read a commented-out assignment as a live binding, so `LOCK=/tmp/bad.lock` followed by a commented canonical-looking line passed the gate. Fixed by stripping shell comments (quote-aware) before collecting assignments only; candidate-token collection still reads comments, because that direction over-reports.
<!-- push-lock-historical: the broken shapes above are specimens of what the gate
now rejects, not recipes. The gate flagged this list on its first run, which is
the behavior working. -->

Decision: when widening a caller into shared code, re-read the shared code against the new inputs rather than trusting that it was already correct, and expect the defect class to repeat at finer granularity after the first fix. Fixing one granularity is a prompt to check the next one down, not a finish line. Pair each fix with a negative control that reverts only that change.

Note: the quote-aware shell-comment parser now lives once, in `scripts/validation/shell_text.py`, shared with `check_skill_portability.py`, so a second copy cannot drift.
