---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-11-session-14681-b7d9a64ed-fix-unresolved-4718-review-thread.json
qaCommit: 7325eab3b15d7f98cf5f4cfe97e65e1308048a62
---
# PR 4718 occupied stale path fix

## Scope

Verify that worktree GC does not recommend a destructive removal command when
a stale registered path is occupied by another checkout or repository.

## Evidence

Before the fix, the real-Git standalone repository fixture produced a kept
decision whose reason still included `git worktree remove <path>`. The command
would delete the foreign repository and its object database.

The reason now checks whether the registered path exists. Missing paths retain
repair and removal guidance. Occupied paths tell the operator to inspect or
move the foreign data first.

## Tests

| Command | Result |
| --- | --- |
| Missing, linked-checkout, and standalone-repository cases | 3 passed |
| `pytest tests -q -k "gc_worktrees or gc_anchor or gc_stale"` | 307 passed after merging current main |
| `ruff check` on changed Python files | passed |
| `mypy` changed-files ratchet | passed |

## Verdict

PASS. Missing paths retain actionable cleanup advice. Occupied paths no longer
print the command that can delete unrelated repository data.
