# A push from a linked worktree exports GIT_DIR, and it outranks `git -C`

## The trap

`git -C <root> <cmd>` does not win against an exported `GIT_DIR`. The `-C` only
changes the working directory; `GIT_DIR` names the repository, and it takes
precedence. Measured on git 2.43.0, scratch repo tracking only `keep.py`:

```text
$ git -C <scratch> ls-files                          # clean environment
keep.py

$ GIT_DIR=<other gitdir> git -C <scratch> ls-files   # reads the OTHER repo
keep.py
scripts/validation/only_on_branch.py
```

## Why it only bites agents

`git push` exports `GIT_DIR` into the pre-push hook environment **only from a
linked worktree**. Measured by dumping `env | grep ^GIT_` from a pre-push hook
on git 2.43.0:

| Push origin | `GIT_DIR` in the hook environment |
|-------------|-----------------------------------|
| Linked worktree (`git worktree add`) | `<main>/.git/worktrees/<name>` |
| Ordinary checkout | absent |

Worktrees are the documented pattern here, so every agent is on the affected
path and no one working in a plain clone can reproduce it.

## How it surfaced

`scripts/ci/count_ratchet.py::tracked_files` ran with the ambient environment.
`merge_tree_ratchet_check` calls `current_count(<scratch>)`, so `ls-files`
listed the *pushing worktree's* index against the *scratch* tree. Any file the
branch carries that `origin/main` deleted was then handed to ruff as a scratch
path that does not exist:

```text
ruff could not read <scratch>/scripts/validation/check_unreachable_after_terminator.py:
No such file or directory
counter returned None
```

`merge-tree-ratchet` and `pre-pr-validation` then blocked the push, naming a
file the branch legitimately has. Issue #4914; it cost five pushes and about 40
minutes on PR #4912 before anyone looked at the environment.

Fixed by `count_ratchet.git_environment()`, which strips `GIT_*` from a copy of
`os.environ`, and by routing every git call site in that module through it.

## The symptom to recognize

A gate reports a path that **exists on your branch and does not exist in the
tree the gate says it is measuring**. That shape means the tool is reading a
different repository than the one it was pointed at. Check `env | grep ^GIT_`
before you doubt the branch.

Workaround if you are blocked right now: push from a non-linked clone. All
hooks still run there.

## Guidance: isolating GIT_* in scripts that run git against a caller-supplied root

> **Non-binding incident guidance.** This is a Serena memory note, not a project rule.
> Cross-harness conventions must live under `.claude/rules/` per `.claude/rules/knowledge-persistence.md`.

Pass an environment, never inherit one:

```python
env = {k: v for k, v in os.environ.items() if not k.upper().startswith("GIT_")}
subprocess.run(["git", "-C", str(root), ...], env=env, check=False)
```

`name.upper()` matters: Windows folds environment names case-insensitively, so
a lowercased `git_dir` set there is the same variable.

Do **not** reach for
`scripts/ci/merge_tree_materialization.py::isolated_git_environment` by reflex.
It is right for a repo the script just created and owns, but it also blanks
`HOME` and the global git config. `actions/checkout` records `safe.directory`
in the global config, and blanking it invites "detected dubious ownership" on a
runner. Measured: a global `safe.directory` that `git config --get-all` returns
under the ambient environment (rc 0) is invisible under that helper's
environment (rc 1). Against a real checkout, strip `GIT_*` and nothing else.

## This will bite your throwaway diagnostic script too

While diagnosing #4914 a scratch harness ran

```python
subprocess.run(["git", "-C", scratch, "add", "-A"])   # GIT_DIR still exported
subprocess.run(["git", "-C", scratch, "commit", "-qm", "snap"])
```

with `GIT_DIR` pointing at the live worktree. Git used `GIT_DIR` as the
repository and `scratch` as the work tree, so `add -A` staged every real file
as **deleted**, and the commit landed on the working branch. `git reset --mixed
<origin/main sha>` recovered it; the working tree was untouched.

Two rules for any repro script:

1. Build fixtures with a `GIT_*`-free environment.
2. Point `GIT_DIR` only at a disposable repository. An unisolated write goes
   *through* it.

## Related

- `git/git-shallow-is-shared-across-every-worktree` - another worktree-scoped
  git state that leaks across checkouts.
- `ci/run-count-ratchets-before-the-expensive-pre-push` - run the cheap ratchets
  first, which is also how you see this failure in seconds instead of after the
  twelve-minute suite.
