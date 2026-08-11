---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-11-session-14681-b7d9a64ed-fix-unresolved-4718-review-thread.json
qaCommit: 1f0fd72afc2a814ef64ede9b82de91e8f44b43bf
---
# PR 4718 reftable anchor fix

## Scope

Verify that worktree GC refuses removal when a linked worktree uses reftable
storage that the files-backend anchor readers cannot inspect.

## Evidence

The unfixed reader returned empty lists for an admin directory containing
`reftable/tables.list`. `unreachable_admin_commits` therefore returned `[]`.
Git's reftable backend stores linked-worktree refs and reflogs in that directory.

The fix treats any present or unreadable `reftable` marker as unknown. Callers
already withhold removal on unknown.

## Tests

| Command | Result |
| --- | --- |
| Focused files-backend, reftable, and dangling-marker cases | 3 passed |
| `pytest tests/test_gc_anchor_readers.py -q` | 36 passed |
| `pytest tests/test_gc_worktrees_real_git_anchors.py -q` | 5 passed |
| `ruff check scripts/maintenance/_gc_anchors.py tests/test_gc_anchor_readers.py` | passed |

Local Git 2.43.0 rejects `git init --ref-format=reftable`. The regression uses
Git's documented linked-worktree reftable layout and confirms fail-closed
behavior without claiming a local reftable integration run.

## Verdict

PASS. The reported silent all-clear now returns unknown. Existing files-backend
behavior remains covered by real Git tests.
