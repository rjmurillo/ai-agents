---
applyTo: src/copilot-cli/**,src/claude/**,**/.claude-plugin/plugin.json
---

# Plugin Version Bump and the Parallel-PR Deadlock

This rule exists because two CI gates interact to deadlock any long-lived PR
that touches a plugin source dir. `build/scripts/validate_plugin_version_bump.py`
requires the `version` in a changed plugin's `.claude-plugin/plugin.json` to be
**strictly greater** than the same field on the base branch. A separate
manifest-parity gate requires the paired dirs (`.claude` and `src/copilot-cli`)
to hold the **same** version. Every merge to `main` that touches a plugin source
bumps that dir's version. So the moment another plugin-source PR lands, your open
PR's version is no longer strictly greater than the new base, the gate flips red,
and you must rebump. An unrelated merge that touches no plugin source does not
move these versions and does not flip the gate. Tracked in issue #2855.

## Which manifests bump, and together or independently

There are two independent version lines. Bump only the ones whose source you
touched:

- **Parity pair (bump together, same value).** `.claude/.claude-plugin/plugin.json`
  and `src/copilot-cli/.claude-plugin/plugin.json` must always hold the same
  version. Touching a file under `.claude/` or `src/copilot-cli/` requires
  bumping **both** of these to the same new value, or the parity gate fails.
- **Separate line (bump independently).** `src/claude/.claude-plugin/plugin.json`
  tracks its own `0.3.x` line. Bump it only when you touch `src/claude/**`. It is
  not coupled to the parity pair.

Set the new version to `max(base_version_across_open_plugin_PRs) + 1`, not just
`base + 1`. If another PR is already in flight at `base + 1`, target `base + 2`
so you sit above it and land without a rebump.

## The recipe when the gate goes red (observed live twice, ~15 min each)

1. `git fetch origin && git rebase origin/main`. Resolve the `plugin.json`
   `version` conflict to `new_base_max + 1`.
2. Stage **both** parity manifests together
   (`git add .claude/.claude-plugin/plugin.json src/copilot-cli/.claude-plugin/plugin.json`),
   plus `src/claude/.claude-plugin/plugin.json` if you touched `src/claude/**`.
   Staging only one of the parity pair fails the parity gate.
3. Finish the rebase with `git rebase --continue` (this recommits the resolved
   state; do not run `git commit --amend`, which is only correct when you are not
   mid-rebase). The validator reads committed state, not the working tree, so you
   MUST commit before re-running it.
4. Run `python3 build/scripts/validate_plugin_version_bump.py --base origin/main`
   until it prints `plugin-version-bump: OK`.
5. `git push --force-with-lease` (safer than a plain force-push: it refuses to
   overwrite unexpected remote updates), then **immediately** arm auto-merge
   (GraphQL `enablePullRequestAutoMerge`, `mergeMethod: SQUASH`) so the PR lands
   before the next merge bumps the base again. Speed is the mitigation.

Do not hand-edit only one of the paired manifests; the parity gate will fail.
Do not expect the version-bump validator to see uncommitted changes.
