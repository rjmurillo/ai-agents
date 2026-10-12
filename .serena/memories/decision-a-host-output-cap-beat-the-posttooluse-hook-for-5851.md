# EUREKA: the host's own output cap beat a PostToolUse hook for issue #5851

## The conventional move

Issue #5851 asked to contain raw tool output before the model reads it. The standard answer is a PostToolUse hook that trims or replaces the output. Layer 1 and 2 reading says use a hook.

## What first principles and ADR-097 showed

- ADR-097 (accepted 2026-08-19) sets a zero tool-use hook policy.
- Claude Code already has `bashOutputMaxChars`: a native inline ceiling on a Bash result, about 30,000 characters by default and up to 128,000. Past it, the result becomes a saved file path plus a 2,000 character preview. Failures get about 10,000 characters inline.
- That is the spill-to-file behavior the hook would have built, for the cost of one setting. A hook was the wrong layer.

## Decision

The owner chose the native cap plus an opt-in wrapper for the command shapes the cap does not cover.

## Sources

- `.project-toolkit/analysis/5851-harness-output-containment-inventory.md` line 47 (the `bashOutputMaxChars` row, doc checked 2026-10-02) and line 49 (the failing-command gap).
- `.project-toolkit/architecture/ADR-097-zero-tool-use-hooks.md`.
- Issue #5851.
- Owner decision as relayed in the sweep task, not found in a repo file.
