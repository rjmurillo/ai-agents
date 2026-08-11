# Never place a git worktree inside the repository checkout

## Rule

Worktrees go in a sibling directory outside the repository root:
`../ai-agents6-worktrees/<name>`, or `../<repo>-<branch>`. Never
`.claude/worktrees/`. Never any path under the checkout, gitignored or not.

The canonical binding form is `.claude/rules/universal.md` MUST NOT 7, with the
generated mirrors at `.github/instructions/universal.instructions.md` and
`src/copilot-cli/instructions/universal.instructions.md`. This memory carries
the incident.

## Why gitignoring the directory does not help

`.gitignore` line 165 already ignores `.claude/worktrees/`. That hides the path
from git. It does not hide it from the filesystem, and a large share of this
repository's tooling walks the filesystem rather than asking git what is
tracked. `tests/test_no_verify_prohibition.py:86` is the clearest case: it calls
`root.rglob("*")` over the instruction roots, so every nested copy of the
repository is scanned as though it were part of the project.

## Measurement, 2026-08-05

59 worktrees had accumulated under `.claude/worktrees/`, each a full checkout.
One measured 577M.

The failure did not look like a worktree problem. It looked like a broken test
suite:

| Check | With worktrees present | After moving them out |
|---|---|---|
| `tests/test_no_verify_prohibition.py` | 422 s, 1 failed | 0.49 s, 9 passed |
| `check_unreachable_after_terminator.py` | over 5 min, hook timeout at 2 min | within budget |
| `tests/test_no_duplicate_module_level_defs.py` | pytest-timeout at 120 s | passes |

The reported violations were real strings in real files, and none of them were
in this project. They were prose in `.serena/memories/git/git-hooks-*.md` inside
a scratch copy, quoting `--no-verify` in order to prohibit it.

The signature to recognize: **CI is green and the local push is red.** A fresh
CI checkout has no worktrees, so the entire class is invisible there. `main`'s
pytest workflow was green at `b22b19b63c` while no push could leave the machine.
Three separate checks failed, which reads like a broken branch and is really one
environmental cause.

## Relocating an existing one

Use `git worktree move`, not removal, when the worktree is dirty:

```
git worktree move .claude/worktrees/<name> ../ai-agents6-worktrees/<name>
```

It preserves uncommitted and untracked files. In the 2026-08-05 cleanup, 23 of
the 59 held uncommitted work, one with 1947 changed files, so removal would have
destroyed real work. The other 36 were clean and were removed with
`git worktree remove`, which refuses on a dirty worktree and is therefore safe
to run in a loop. Removing a worktree does not delete its branch, so committed
work survives either path.

## Related

- `git/git-stash-is-shared-across-every-worktree.md`. The stash stack is shared,
  so a pop in one worktree can take another agent's work.
- `git/git-shallow-is-shared-across-every-worktree.md`. Shallow state is shared
  through the common dir.
- `git/git-a-subagent-in-your-worktree-moves-your-head.md`. A subagent operating
  in your worktree moves your HEAD.
