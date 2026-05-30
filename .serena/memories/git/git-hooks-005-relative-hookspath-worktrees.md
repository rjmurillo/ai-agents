# Skill-Git-005: Relative core.hooksPath, never absolute (worktree-safe)

**Statement**: Set `core.hooksPath` to the relative value `.githooks`, never an absolute path. Relative resolves per-worktree to each tree's own checked-out hooks; absolute silently bypasses guards in every `git worktree`.

**Context**: Installing/enforcing the repository's `.githooks/` (pre-commit, pre-push, including the plugin version-bump gate from #2118). Diagnosed during PR #2138/#2136 work when a clone was found with `core.hooksPath = /abs/path/.git/hooks` (the empty default dir), so no guard ran locally and un-bumped plugin PRs reached merge.

**Evidence**:

- `core.hooksPath` is stored once in the shared `.git/config` and inherited by every worktree.
- githooks(5): before running a hook, git sets cwd to the work-tree root. A **relative** `core.hooksPath` therefore resolves against the current worktree root, so each worktree runs its OWN `.githooks/`. Verified empirically: a throwaway `git worktree add` reported `core.hooksPath=.githooks` and found its own executable `pre-push`.
- An **absolute** value (e.g. `/home/.../.git/hooks`) overrides `.githooks` AND makes every worktree run the main repo's empty hooks dir, bypassing all guards. This is the footgun.
- Nothing local can self-detect a wrong/absent `hooksPath`: if hooks are off, no guard runs to notice. Only a CI **required** check is non-bypassable.

**Atomicity**: 90%

**Tag**: critical

**Impact**: 9/10 (silent guard bypass across all worktrees)

**Created**: 2026-05-30

**Validation Count**: 1 (diagnosed live, PR #2138/#2136)

**Failure Count**: 0

**Category**: Git

## Anti-Pattern

```bash
# WRONG: absolute path. Overrides .githooks and breaks every worktree.
git config core.hooksPath "$(pwd)/.git/hooks"
git config core.hooksPath /home/user/repo/.git/hooks
```

## Correct Pattern

```bash
# RIGHT: relative. Self-configures the main tree and every worktree.
git config core.hooksPath .githooks
# Or the idempotent installer (also verifies executability + flags stale shims):
python3 scripts/install_git_hooks.py
# Verify without mutating (wired into scripts/validation/pre_pr.py, skipped under CI):
python3 scripts/install_git_hooks.py --check
```

## Related

- `scripts/install_git_hooks.py` (installer + `--check`)
- `scripts/validation/pre_pr.py::validate_git_hooks_installed` (local drift gate, CI-skipped)
- `CONTRIBUTING.md` setup step 6 + Pre-Commit Hooks section
- `.githooks/pre-push` (the guards being protected; version-bump section ~line 741)
- The separate merge-gate half: add `Validate Plugin Version Bump` to ruleset required checks (governance change).
