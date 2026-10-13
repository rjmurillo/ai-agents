# Workflow Tool: Worktree Isolation With a Schema Fails Silently

<!-- placement: evidence; reason: records an observed harness failure and the working pattern, not an operating contract -->

**Provenance**: Observed in a prior session (Hindsight REF-IDs d2634227, 88a75954, 07334357, 41f6c6e7). Recorded 2026-10-13. Not re-verified when recorded. Re-test before building a large wave on it.

## The trap

Inside a Workflow tool script, `agent({ isolation: 'worktree', schema })` fails silently. No worktree is created. The wave returns nothing usable.

## Working pattern

1. Create the worktree yourself, outside the clone: `~/worktrees/<repo>/<branch>`.
2. Call the Agent tool directly. Pass no `schema`.
3. Ask the agent to end with a plain-text block, then parse it:

```text
=== REPORT ===
branch: ...
sha: ...
=== END ===
```

The Agent tool's `isolation: "worktree"` places worktrees under `.claude/worktrees/` inside the clone. Repository-wide scans then walk them. The external worktree with a text report is the safer default.

## Leak seen in worktree agents

Some worktree agents resolved Read, Edit, and Write to the main checkout instead of their worktree.

- Each agent runs `git rev-parse --show-toplevel` first and confirms the path.
- The parent runs `git rev-parse --abbrev-ref HEAD` in the main checkout after each wave and confirms it still reads `main`.

## Related

- `workflows/pr-review-batching-strategy.md` plans tier waves that use worktree isolation.
- `agent-workflow/fleet-worktree-live-versus-abandoned.md` covers triage of worktrees left behind.
