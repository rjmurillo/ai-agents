# Worktree Identity Verification Before Writes

Verified 2026-07-26 against `origin/main` @ `17b89457`.

## The failure

`~/repos/ai-agents/.git/config` sets `core.worktree` to a Kanban workspace under `~/.hermes/kanban/boards/ai-agents/workspaces/<id>/work`. That `.git` directory therefore manages a *different* tree than the one you are standing in.

Files written into `~/repos/ai-agents` were real on disk, correct in content, and permanently invisible to git. `git status` reported a clean tree the entire time, because it was faithfully reporting on the other directory. Two rule files plus 22 generated outputs landed before the mismatch surfaced, and only via an unrelated observation.

`git rev-parse --show-toplevel` from `~/repos/ai-agents` returns the Kanban path, not `~/repos/ai-agents`.

## The check (run before the first write)

```bash
repo_root=$(git rev-parse --show-toplevel)
case "$(pwd -P)" in
  "$repo_root"|"$repo_root"/*) ;;
  *) echo MISMATCH ;;
esac

git_dir=$(git rev-parse --absolute-git-dir)
common_dir=$(git rev-parse --path-format=absolute --git-common-dir)
if [ "$git_dir" = "$common_dir" ]; then
  git config --local --get core.worktree
fi
```

Full four-condition gate:

1. `pwd -P` is the toplevel or a directory below it
2. the worktree's **own local** `core.worktree` does not redirect. Read `--local` only when `git rev-parse --git-dir` equals `--git-common-dir`; plain `git config` reports inherited values and false-positives on legitimate linked worktrees
3. a throwaway probe file actually appears in `git status --untracked-files=all`
4. every file you intend to edit already exists (absence means wrong branch, not greenfield)

## Why `git status` is not the confirmation

A clean status is equally consistent with "nothing changed" and "git is not observing this directory." It cannot distinguish them. When a write should have produced a diff and status shows none, treat it as a failed probe and check tree identity before rewriting or concluding success.

## Same defect class as bare relative path resolution

`src/copilot-cli/skills/pr-autofix/SKILL.md` `resolve_pr_scripts_dir()` probes the bare relative string `".claude"` (lines 44, 135 at `17b89457`). Both bugs assume cwd is the repo root, both silently operate on a different tree, both fail open with no diagnostic. Anchor on `git rev-parse --show-toplevel` in both cases. See `.claude/rules/worktree-identity.md` and `.claude/rules/harness-path-resolution.md`.

## Generated-mirror note

`.github/instructions/` and `src/copilot-cli/instructions/` are **generated** from `.claude/rules/` by `build/scripts/generate_rules.py` (35 rules to 70 outputs at `17b89457`). Author the `.claude/rules/` file only, then run the generator. Never hand-write the mirrors. Frontmatter uses `paths:`/`priority:` on the source; the generator rewrites to `applyTo:` and drops `priority:`.
