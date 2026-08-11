# A script that derives its root from `__file__` reads its own worktree, whatever directory you are standing in

## The trap

Many scripts in this repository find the repository root from their own
location on disk rather than from the current directory.
`scripts/update_memory_index_tokens.py:171` is the shape:

```python
repo_root = Path(__file__).resolve().parent.parent
```

With `git worktree`, that is a silent correctness hole. Standing in worktree B
and invoking worktree A's copy of a validator makes the validator read, check,
and report on **A's** files. It exits 0 because A is fine. You conclude B is
fine. B was never examined.

The failure is silent and it inverts the signal: the more worktrees you run, the
more confident and the more wrong the PASS becomes.

## Measured proof

Observed 2026-08-05. Same working directory, only the script copy differs.

Setup: in worktree `wt-scriptroot`, edit one recorded token count in
`.serena/memories/memory-index.md` from `1132` to `9999`. That worktree's index
is now provably stale. The other clone's index is untouched and current.

Direction A, the other tree's script by absolute path:

```
$ cd ~/src/scratch/wt-scriptroot
$ uv run --frozen python ~/src/GitHub/rjmurillo/ai-agents/scripts/update_memory_index_tokens.py --check
Creating virtual environment at: .venv
   Building ai-agents @ file:///home/richard/src/scratch/wt-scriptroot
memory-index.md token counts are current
exit=0
```

Direction B, this worktree's own copy, unchanged cwd, unchanged file:

```
$ cd ~/src/scratch/wt-scriptroot
$ uv run --frozen python scripts/update_memory_index_tokens.py --check
memory-index.md token counts are stale:
  git/git-shallow-is-shared-across-every-worktree.md: recorded 9999, actual 1132
exit=1
```

A reports current because it never looked at the stale file; it examined the
other clone. B reports stale. The only variable is which copy of the script ran.

Note the `Built ai-agents @ file:///home/richard/src/scratch/wt-scriptroot` line
in direction A. `uv` resolved the project from cwd correctly, and the script
still read the wrong tree, because `uv` has no influence on a `__file__`-derived
path. A correct `uv` project does not save you.

## What this does and does not prove

**Proven**: the script targets the tree containing the script. `--check`
therefore reports on that tree, so a false PASS about the tree you are editing
is real and reproducible.

**Not proven by the experiment above**: that the mutating form necessarily
writes. Read the code rather than assuming. `update_memory_index_tokens.py:140`
writes only when the content changed:

```python
if updated != original:
    index_path.write_text(updated, encoding="utf-8")
```

So without `--check`, any needed correction lands in the **script's** tree, and
only if that tree's index was itself stale. A clean tree is left alone. Either
way the tree you meant to fix is untouched.

## The hook is not fooled, and normally repairs rather than rejects

Do not expect the commit hook to catch this for you, and do not expect it to
reject. In `lefthook.yml` the pre-commit sequence is piped and ordered:

1. `memory-token-update` (line 260) runs the updater without `--check`, repairing counts.
2. `stage-memory-index` (line 268) stages the repaired index.
3. `memory-token-counts` (line 291) runs `--check`, which then passes.

Each of those invocations is a relative path inside the tree being committed, so
the hook operates on the right tree regardless of what you ran at the desk.

Rejection at step 3 is the exception, not the rule. Steps 1 and 2 both carry
`skip: [merge, "test $SKIP_AUTOFIX = 1"]`, so the check only sees stale counts
when the commit is a merge or `SKIP_AUTOFIX=1` is set. That matches
`.claude/rules/knowledge-persistence.md` MUST-6, which documents the same
skip-driven staleness from the other direction.

## The actual invariant

The rule is not "use a relative path". An absolute path that lands inside the
intended worktree is fine, and a relative path that resolves through a symlink
into another worktree is not.

**The resolved script path must be contained by the worktree you intend to
operate on.** Invoking relatively from that worktree's root is simply the
cheapest way to guarantee it:

```bash
set -euo pipefail
WORKTREE="$(git rev-parse --show-toplevel)"
SCRIPT="scripts/update_memory_index_tokens.py"
cd "$WORKTREE"
test -f "$SCRIPT" || { echo "script missing in this tree"; exit 1; }
uv run --frozen python "$SCRIPT" --check
```

## Checking a candidate invocation

A detector must inspect the path you are **about to run**, so it has to take
that path as input. A check that rebuilds the path from the current tree is
tautological: it can only ever report a path inside the current tree, so it
never fires.

```bash
set -euo pipefail
CANDIDATE="${1:?pass the script path you intend to run}"
python3 - "$CANDIDATE" <<'PY'
import os, subprocess, sys
from pathlib import Path

candidate = Path(sys.argv[1]).resolve()
for var in ("GIT_DIR", "GIT_WORK_TREE"):
    if var in os.environ:
        sys.exit(f"{var} is set; resolve it before trusting this check")
top = subprocess.run(
    ["git", "rev-parse", "--show-toplevel"],
    capture_output=True, text=True, check=True,
).stdout.strip()
tree = Path(top).resolve()
if not candidate.is_relative_to(tree):
    sys.exit(f"WRONG TREE\n  candidate: {candidate}\n  this tree: {tree}")
print(f"contained by {tree}")
PY
```

Python does the resolution because `realpath` is absent on stock macOS, and
`Path.resolve` follows symlinks on both paths so a symlinked script cannot
escape the containment test. `git rev-parse --show-toplevel` is correct inside a
linked worktree; `--git-common-dir` would be wrong, since it names the shared
metadata directory rather than this checkout.

## Scope: common, not universal

Do not over-apply this. Measured in this repository:

| Measure | Count |
|---|---|
| files under `scripts/` matching `Path(__file__).resolve().parent` | 119 |
| Python files under `scripts/` (recursive) | 431 |
| Python files at the top level of `scripts/` | 60 |

So the pattern appears in roughly 28 percent of the tree, and a bare substring
match does not prove the expression controls that script's operational root.
Counterexamples that correctly derive from cwd:

- `scripts/restructure_memories.py:394`, `repo_root = Path.cwd()`
- `scripts/validation/check_unreachable_code.py:119`, `repo_root = Path.cwd()`

Confirmed to carry the trap alongside the token updater:
`scripts/check_skill_exists.py`.

Treat an absolute-path invocation from a different worktree as unproven for any
script you have not read, rather than assuming every script is affected.

## Related

- [git/git-shallow-is-shared-across-every-worktree](git-shallow-is-shared-across-every-worktree.md), the opposite shape: state shared across worktrees when you expect it to be per-tree.
- [git/git-stash-is-shared-across-every-worktree](git-stash-is-shared-across-every-worktree.md), same family.
