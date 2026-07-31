---
applyTo: .claude/**,src/copilot-cli/**,src/claude/**,**/.claude-plugin/plugin.json
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

Set the new version to `max(version across every remote branch) + 1`. Do not use
`base + 1`, and do not "target `base + 2`" because one other PR sits at `base + 1`.
Measured 2026-07-31: base was `0.6.5446`, so `base + 2` would have been
`0.6.5448`, but **14 remote branches already held a higher value**, topping out at
`0.6.5471`. Any one of them merging first flips your gate red.

Enumerate the pack before you pick a number:

```bash
git fetch origin --quiet
for b in $(git ls-remote --heads origin | awk '{print $2}' | sed 's#refs/heads/##'); do
  git show "origin/$b:.claude/.claude-plugin/plugin.json" 2>/dev/null \
    | python3 -c 'import json,sys;print(json.load(sys.stdin)["version"])' 2>/dev/null
done | sort -V | tail -1
```

Increment the last component of that value. `max + 1` does not *guarantee* you
never rebump, because a branch that allocates after you can still land first. What
it buys is that you start above every allocation that already exists, so only new
entrants can displace you. `base + 1` starts below most of the pack, so it is
near-certain to need a rebump.

## The recipe when the gate goes red

**Merge, never rebase.** `AGENTS.md` lists force-push under **Never**, and
`.claude/rules/universal.md` MUST NOT-1 forbids it on shared branches. A branch
with an open PR is shared: reviewers and bots anchor comments to specific commit
SHAs. Rebasing rewrites those SHAs, so the push is rejected as non-fast-forward
and the only way through is a force-push. Merging keeps the push fast-forward and
needs no force. This is not only policy: on PR #4063 the remote branch gained a
commit from another actor mid-session, the merge path absorbed it, and a
force-push would have destroyed it.

1. `git fetch origin && git merge origin/main`. Resolve the `plugin.json`
   `version` conflict to the value computed above.
2. Stage **both** parity manifests together
   (`git add .claude/.claude-plugin/plugin.json src/copilot-cli/.claude-plugin/plugin.json`),
   plus `src/claude/.claude-plugin/plugin.json` if you touched `src/claude/**`.
   Staging only one of the parity pair fails the parity gate.
3. `git commit` to conclude the merge. The validators read committed state, not
   the working tree, so you MUST commit before re-running them.
4. Run all three gates. Each fails independently, and the version gate alone does
   not catch a parity break or a malformed manifest:

   ```bash
   python3 build/scripts/validate_plugin_version_bump.py --base origin/main
   python3 build/scripts/check_plugin_manifest_parity.py
   python3 build/scripts/validate_plugin_manifests.py
   ```

   `check_plugin_manifest_parity.py` takes no arguments and does not implement
   `--help`; passing one runs the check anyway.
5. `git push`, then **read the `To ...` line of its output**. A rejected
   non-fast-forward push can still leave the shell exit code at 0, so the exit
   code is not proof. Confirm independently with
   `git ls-remote origin refs/heads/<branch>`. Then arm auto-merge (GraphQL
   `enablePullRequestAutoMerge`, `mergeMethod: SQUASH`) so the PR lands before the
   next merge bumps the base again. Speed is the mitigation.

## When your branch sits below the base

This case defeats naive conflict resolution. A branch cut a while ago can carry a
version *lower* than `main`. Then **neither side of the conflict is correct**:
`--ours` keeps a value below base, `--theirs` keeps base itself, and the gate
demands strictly greater than base. Either choice produces a red gate that looks
resolved. Take the incoming content, then overwrite the `version` field with a
freshly computed `max + 1`.

This is the common case, not a corner case. Measured 2026-07-31: 56 remote
branches touch plugin source and sit at or below base (the set includes stale
branches). PR #4063 was one of them, at `0.6.5443` against a base of `0.6.5446`.

Note that the gate is conditional on the diff. A branch below base is only red if
it actually changes plugin source; a docs-only branch that never touched a plugin
dir passes even at an old version. Verify with
`validate_plugin_version_bump.py --base origin/main --head origin/<branch>` rather
than assuming from the version number alone.

Do not hand-edit only one of the paired manifests; the parity gate will fail.
Do not expect the version-bump validator to see uncommitted changes.
