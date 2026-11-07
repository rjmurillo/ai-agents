# Post-merge cleanup

Run this after every merge this skill lands, once `test_pr_merged.py` reports
`merged: true`. The snippet reads its inputs from `test_pr_merged.py`
(`head_ref`, `head_sha`, `merge_commit_sha`, `head_repo`), fails when any is empty, and checks `git merge-base --is-ancestor "$MERGE_SHA" origin/main` first.
A leftover worktree costs disk and slows repo-wide scans: one machine counted
113 of them at 10.6G. A merged PR has been found with its worktree and
local branch still in place.

```bash
# Replace <pr> with the merged PR number.
resolve_pr_scripts_dir() {
  repo_root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
  for root in \
    "${COPILOT_PLUGIN_ROOT:-}" \
    "${CLAUDE_PLUGIN_ROOT:-}" \
    "$repo_root/.claude" \
    "${HOME:-}/.copilot/installed-plugins/_direct/project-toolkit" \
    "${HOME:-}/.copilot/installed-plugins"/*/project-toolkit \
    "${HOME:-}/.claude/plugins/cache"/*/project-toolkit; do
    if [ -n "$root" ] && [ -d "$root/skills/github/scripts/pr" ]; then
      printf '%s\n' "$root/skills/github/scripts/pr"
      return 0
    fi
  done
  printf '%s\n' ".claude/skills/github/scripts/pr"
}
SCRIPTS_DIR="$(resolve_pr_scripts_dir)"
# jq prints nothing unless all five values exist, so the guard below fails loud.
read -r PR_HEAD_REF MERGED_HEAD_SHA MERGE_SHA PR_HEAD_REPO < <(python3 "$SCRIPTS_DIR/test_pr_merged.py" --pull-request <pr> --output-format json \
    | jq -r 'select(.merged == true and .head_ref and .head_sha and .merge_commit_sha and .head_repo) | [.head_ref, .head_sha, .merge_commit_sha, .head_repo] | @tsv')
: "${PR_HEAD_REF:?}" "${MERGED_HEAD_SHA:?}" "${MERGE_SHA:?}" "${PR_HEAD_REPO:?}"
git fetch origin main && git merge-base --is-ancestor "$MERGE_SHA" origin/main || { echo "merge not on main yet"; exit 1; }
# The branch name is chosen by the PR author, so the ref alone does not identify
# the worktree. Also require HEAD to equal the merged head and origin to be the
# PR's head repository (the fork for a fork PR, not the base repository). A worktree
# that fails either check is not matched, so WT stays empty and the guard below
# keeps and reports it. There is no path-convention fallback: it would reinstate
# a ref-only match.
WT=""
# pr-worktree-select:begin
WANT_REPO=$(printf '%s' "$PR_HEAD_REPO" | tr 'A-Z' 'a-z')
# awk fields are written $(N), not $N: the skill loader rewrites a bare $<digit> as an argument.
while IFS= read -r CANDIDATE; do
    [ -n "$CANDIDATE" ] || continue
    [ "$(git -C "$CANDIDATE" rev-parse HEAD 2>/dev/null)" = "$MERGED_HEAD_SHA" ] || continue
    ORIGIN_URL=$(git -C "$CANDIDATE" remote get-url origin 2>/dev/null | tr 'A-Z' 'a-z')
    ORIGIN_URL=${ORIGIN_URL%/}
    ORIGIN_URL=${ORIGIN_URL%.git}
    case "$ORIGIN_URL" in
        *"/$WANT_REPO" | *":$WANT_REPO") WT="$CANDIDATE"; break ;;
    esac
done < <(git worktree list --porcelain | awk -v ref="refs/heads/$PR_HEAD_REF" \
    '/^worktree /{p=substr($(0), 10)} $(1) == "branch" && $(2) == ref {print p}')
# pr-worktree-select:end
# Keep when nothing matched, or the match has local edits or a head other than the merged one.
[ -n "$WT" ] && [ -z "$(git -C "$WT" status --porcelain)" ] && \
  [ "$(git -C "$WT" rev-parse HEAD)" = "$MERGED_HEAD_SHA" ] || { echo "keep ${WT:-<no matching worktree>}"; exit 1; }
COMMON=$(git -C "$WT" rev-parse --path-format=absolute --git-common-dir)
# -C, not --git-dir: after a self-removal the cwd is gone and git cannot start there.
git -C "$COMMON" worktree remove "$WT"
# -D, not -d: a squash merge leaves the tip outside main's history. The SHA check above makes it safe.
git -C "$COMMON" branch -D "$PR_HEAD_REF"
# Empty output means the remote branch is gone.
git -C "$COMMON" ls-remote origin "refs/heads/$PR_HEAD_REF"
```

- Never pass `--force` to `git worktree remove`. A dirty or moved worktree is
  kept and reported with the reason.
- Run removal through the owning clone's `--git-common-dir`. `git worktree list`
  in a sibling clone does not see the worktree.
- The remote branch goes away when the repository sets `delete_branch_on_merge`.
  Otherwise pass `--delete-branch` to `merge_pr.py`. Set `git config fetch.prune
  true` so the next fetch drops the stale remote-tracking ref.
