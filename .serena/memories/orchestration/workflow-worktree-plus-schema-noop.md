# Isolated Worktree Agent With A Schema Can No-Op (Observed)

## Statement

In the Workflow tool, `agent({isolation: 'worktree', schema})` can complete as a
no-op. No worktree is created, and the forced StructuredOutput returns without
the work done.

## Do this instead

- Call the direct Agent tool with `isolation: "worktree"` and no schema. Ask the
  agent for a plain-text report block and parse that.
- Or have the agent create its own worktree under `~/worktrees/ai-agents/<branch>`.
  The 2026-10-12 sweep used this path.

## Check before trusting a result

A schema-valid return is not proof of work. Confirm the worktree exists with
`git worktree list` and that the branch has commits before you accept the report.

## Evidence

Observed in a prior session, not re-run for this memory. It is runtime behavior
of the Workflow tool, so no repository file proves it.

- Source: Hindsight page "Multi-agent run playbook" (kp-5ad73a597d6a4cb69a6a3dd731fad139).
- REF-IDs: d2634227, 9da94c81.
- Owner-approved and logged 2026-10-13. Repository-side checks on that date
  covered only the worktree path convention.
