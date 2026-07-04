---
applyTo: .claude/**,src/copilot-cli/**,src/claude/**,**/.claude-plugin/plugin.json
---

# Plugin Version Bump and the Parallel-PR Deadlock

This rule exists because two CI gates interact to deadlock any long-lived PR
that touches a plugin source dir. `build/scripts/validate_plugin_version_bump.py`
requires the `version` in a changed plugin's `.claude-plugin/plugin.json` to be
**strictly greater** than the same field on the base branch. A separate
manifest-parity gate requires the paired dirs (`.claude` and `src/copilot-cli`)
to hold the **same** version. Every merge to `main` bumps those versions. So the
moment another plugin-source PR lands, your open PR's version is no longer
strictly greater than the new base, the gate flips red, and you must rebump.
Tracked in issue #2855.

## What to do

When you edit any file under `.claude/`, `src/copilot-cli/`, or `src/claude/`,
you MUST bump the `version` in that dir's `.claude-plugin/plugin.json`:

- Bump `.claude` and `src/copilot-cli` **together** to the same value (parity).
- Bump `src/claude` only when you touch `src/claude/**` (it tracks a separate
  `0.3.x` line).
- Set the new version to `max(base_version_across_open_plugin_PRs) + 1`, not just
  `base + 1`. If another PR is already in flight at `base + 1`, target `base + 2`
  so you sit above it and land without a rebump.

## The recipe when the gate goes red (observed live twice, ~15 min each)

1. `git fetch origin && git rebase origin/main` (resolve the `plugin.json`
   `version` conflict to `new_base_max + 1`).
2. `git add` the manifest, `git commit --amend` (the validator reads committed
   state, not the working tree, so you MUST commit before re-running it).
3. `python3 build/scripts/validate_plugin_version_bump.py --base origin/main`
   until it prints `plugin-version-bump: OK`.
4. Force-push, then **immediately** arm auto-merge (GraphQL
   `enablePullRequestAutoMerge`, `mergeMethod: SQUASH`) so the PR lands before
   the next merge bumps the base again. Speed is the mitigation.

Do not hand-edit only one of the paired manifests; the parity gate will fail.
Do not expect the version-bump validator to see uncommitted changes.
