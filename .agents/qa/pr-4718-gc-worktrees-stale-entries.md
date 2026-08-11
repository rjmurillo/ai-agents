---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-10-session-10035-bfffb0de4-create-report-4718-worktree-changes.json
qaCommit: 1d1ea7fe53811ea07f8758d2916997ca02ffcb8c
---
# Test Report: PR #4718 GC worktree stale entries

## Scope

Branch `fix/gc-worktrees-stale-entries`, code tip
`1d1ea7fe53811ea07f8758d2916997ca02ffcb8c`, which is the merge of current `origin/main` at `ff1fcd7b37`.

This round closes the two open review threads. Both were reproduced against real
git 2.43.0 before the fix and re-broken afterwards.

## Live state and setup

- Acquired the PR lease with `pr_autofix_lease.py`: `action=ACT`, `reason=free`.
- `check_pr_live_state.py` returned `ACT` for PR #4718 at head
  `21b0a779de451a7bb93e6fdafbc01bff599ce69f`, base `main`.
- Worked in the isolated worktree `/home/richard/sessions/autofix-4718`.

## Finding 1: a per-worktree ref lock did not stop a removal

`refs/worktree/*` lives in the worktree's own admin directory, and git's files
backend writes `<ref>.lock` beside the ref while installing one. The marker
probe read only the flat names at the top of that directory.

Measured with `refs/worktree/installing.lock` held:

| Probe | Before | After |
|---|---|---|
| `in_progress_operation` | `None` | `another git process is updating a worktree-local ref` |
| `worktree_ref_oids` | `[]` | `[]`, unchanged: an empty lock names no object |
| `git worktree remove` | exit 0, no output, worktree gone | exit 0, no output, so the guard is what keeps it |

An empty lock is not a corner case. A `git update-ref --stdin` delete
transaction holds a 0-byte lock for its whole prepared window, measured, and an
update holds one between creation and the write.

## Finding 2: the orphan count broke the rescue chain it followed

Past three orphans the reason appended the count of the rest onto the last SHA.
Measured on the seven-orphan case, the slice a reader copies ended
`... <sha> (and 4 more, named under <path>, which the removal deletes)`, and
`bash -c` on it exits 2 with ``syntax error near unexpected token `('`` before
creating a single rescue branch. The count now sits behind the `" | "`
delimiter the staged-work rescue already uses, which is where `command_of` and a
reader both stop.

## Test execution results

| Command | Result |
|---------|--------|
| `pytest tests/ -k "gc_worktrees or gc_stale or gc_anchor"` | 305 passed |
| Same suite with only the two source files reverted | 7 failed, 50 passed in the three touched files: the negative control |
| `pytest tests/test_gc_worktrees_real_git_rescue.py tests/test_gc_worktrees_real_git_stale.py` | 18 passed after the split |
| `scripts/ci/taste_count_ratchet.py` | OK, count == baseline 583 |
| `scripts/ci/ruff_count_ratchet.py` | OK, 27 <= baseline 30 |
| `scripts/ci/subprocess_encoding_count_ratchet.py` | OK, 236 <= baseline 253 |
| `ruff check` and `ruff format --check` on every changed file | clean |
| Same GC suite and ratchets re-run after merging `origin/main` at `ff1fcd7b37` | 305 passed, taste 583, ruff 27 <= 30 |

New coverage: five real-git cases for the ref lock, including one that drives a
prepared `git update-ref --stdin` transaction so git itself writes the lock, a
negative control on a settled ref with no lock, an unreadable-`refs` case, and a
no-subprocess cost pin. One real-git case runs the sliced rescue chain in `bash`
from a directory outside any repository and asserts three branches are created.

## Ratchet repair

Merging current `main` put the taste count at 584 against a baseline of 583.
Diffing the branch and main violation sets on `(file, rule)` named exactly one
addition: `tests/test_gc_worktrees_real_git_stale.py` file-size. The file
answered two questions, so the rescue-command cases moved to
`tests/test_gc_worktrees_real_git_rescue.py`. Both files now sit under the limit
at 463 and 234 lines, and the count returned to 583. The baseline was not
raised.

## Verdict

PASS. Both review findings are fixed at the root, each with a real-git
reproduction and a negative control, and every ratchet is back at or under its
baseline.
