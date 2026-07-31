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
Measured 2026-07-31: base was `0.6.5447`, so `base + 2` would have been
`0.6.5449`, but **15 remote branches already held a higher value**, topping out at
`0.6.5472`. Any one of them merging first flips your gate red.

Enumerate the pack before you pick a number. The two lines are far apart, so
reading the wrong one hands you a number off by orders of magnitude: measured the
same day, the parity line topped out at `0.6.5472` and the `src/claude` line at
`0.3.57`. Report every line in one pass rather than picking a manifest by hand,
then bump the parity pair together to one value and `src/claude` to its own.

```bash
git fetch origin --quiet || { echo "ERROR: git fetch failed; refs may be stale" >&2; exit 1; }
for MANIFEST in .claude/.claude-plugin/plugin.json \
                src/copilot-cli/.claude-plugin/plugin.json \
                src/claude/.claude-plugin/plugin.json; do
  VERSIONS=$(for b in $(git ls-remote --heads origin | awk '{print $2}' | sed 's#refs/heads/##'); do
    git show "origin/$b:$MANIFEST" 2>/dev/null \
      | python3 -c 'import json,sys;print(json.load(sys.stdin)["version"])' 2>/dev/null
  done)
  [ -n "$VERSIONS" ] || { echo "ERROR: read zero versions from $MANIFEST" >&2; exit 1; }
  MAX=$(printf '%s\n' "$VERSIONS" | sort -V | tail -1)
  printf '%-46s %s\n' "$MANIFEST" "$MAX"
done
```

The emptiness check is load-bearing. Both `git show` and the decoder discard
stderr, so a mistyped manifest path makes every read fail silently; unguarded, the
pipeline then prints nothing and still exits 0, which reads as "nobody has
allocated" when it actually means "I measured nothing." Verified: the guarded
form exits 1 on a bogus path. The fetch guard is load-bearing for the same
reason, one step earlier. `git show` reads local remote-tracking refs, not the
network, so an unchecked fetch failure does not empty the output; it silently
answers from whatever those refs held last. Verified: with the fetch failing
(exit 128) and the return value discarded, the loop still printed a maximum and
exited 0. That is worse than reading nothing, because a stale answer understates
the pack and looks exactly like a fresh one. Separately, `sort -V` places a prerelease suffix
*after* the plain version (`0.6.5471`, then `0.6.5471-rc1`), the reverse of
SemVer precedence. No branch uses a suffix today, so that is latent rather than
live, but do not trust this snippet if one appears.

Increment the last component of that value. `max + 1` does not *guarantee* you
never rebump, because a branch that allocates after you can still land first. What
it buys is that you start above every allocation that already exists, so only new
entrants can displace you. `base + 1` starts below most of the pack, so it is
near-certain to need a rebump.

## The recipe when the gate goes red

**Merge, never rebase.** `AGENTS.md` lists force-push under **Never**, and
`.claude/rules/universal.md` MUST NOT-1 forbids it on shared branches. A branch
with an open PR is shared: reviewers and bots anchor comments to specific commit
SHAs. Rebasing a branch that has already diverged from its published head
rewrites those SHAs, so the push is rejected as non-fast-forward and the only way
through is a force-push. (A rebase whose upstream is already an ancestor is a
no-op and needs no force, but you cannot count on that on the long-lived PR this
rule is about.) Merging keeps the push fast-forward and needs no force. This is
not only policy: on PR #4063 the remote branch gained a commit from another actor
mid-session, the merge path absorbed it, and a force-push would have destroyed it.

1. `git fetch origin`, then reconcile **your own branch before main**:

   ```bash
   git merge origin/<your-branch>   # absorb commits pushed to the PR head
   git merge origin/main            # then absorb the new base
   ```

   Merging `origin/main` alone does **not** pick up a commit another actor or a
   bot pushed to your PR head, and it leaves your eventual push non-fast-forward
   for a reason no amount of rebasing against main will fix. That is the exact
   mechanism behind the #4063 case above. Resolve the `plugin.json` `version`
   conflict to the value computed above.
2. Stage **both** parity manifests together
   (`git add .claude/.claude-plugin/plugin.json src/copilot-cli/.claude-plugin/plugin.json`),
   plus `src/claude/.claude-plugin/plugin.json` if you touched `src/claude/**`.
   Staging only one of the parity pair fails the parity gate.
3. `git commit` to conclude the merge. The validators read committed state, not
   the working tree, so you MUST commit before re-running them.
4. Run these three manifest validators. Each fails independently, and the version
   gate alone does not catch a parity break or a malformed manifest:

   ```bash
   python3 build/scripts/validate_plugin_version_bump.py --base origin/main
   python3 build/scripts/check_plugin_manifest_parity.py
   python3 build/scripts/validate_plugin_manifests.py
   ```

   `check_plugin_manifest_parity.py` takes no arguments and does not implement
   `--help`; passing one runs the check anyway. All three are stdlib-only, so a
   bare `python3` is enough here. These are the manifest-specific gates, not the
   whole suite: pre-push and CI reach the manifest again through
   `tests/e2e/test_plugin_load_smoke.py`, which reads the manifest `version` and
   asserts it surfaces from the loaded plugin. A clean local run of these three is
   necessary, not sufficient.
5. `git push`, then **read the `To ...` line of its output**. `git push` itself
   exits nonzero when the remote rejects the push, but a pipeline hides that:
   `git push ... | tail` reports `tail`'s status, not git's. Measured:
   `(exit 7) | tail -1` yields `0`, and the same pipeline under
   `set -o pipefail` yields `7`. So do not pipe the push, or set `pipefail`
   first, and confirm independently that the remote head is **the commit you
   meant to push**:

   ```bash
   git rev-parse HEAD
   git ls-remote origin refs/heads/<branch> | cut -f1
   ```

   The two SHAs must match. Running `ls-remote` on its own proves only that the
   branch exists, which it did before you pushed. Then arm auto-merge (GraphQL
   `enablePullRequestAutoMerge`, `mergeMethod: SQUASH`) so the PR lands before the
   next merge bumps the base again. Speed is the mitigation.

## When your branch sits below the base

This case defeats naive conflict resolution. A branch cut a while ago can carry a
version *lower* than `main`. Then **neither side of the conflict is correct**:
`--ours` keeps a value below base, `--theirs` keeps base itself, and the gate
demands strictly greater than base. Either choice produces a red gate that looks
resolved. Resolve the rest of the manifest on its merits, keeping any branch-side
edits to fields like `description` or the component lists, then overwrite **only**
the `version` field with a freshly computed `max + 1`. Taking the incoming side
wholesale silently discards those edits; commit `384463efc` is a real precedent
for a manifest change that touched `description` and nothing else.

This is the common case, not a corner case. Measured 2026-07-31 against a base of
`0.6.5447`: of 182 remote branches, 84 change a non-manifest file under `.claude/`
and are therefore subject to the gate, and **50 of those 84 sit at or below base**
(the set includes stale branches). PR #4063 was one of them, at `0.6.5443`.

Note that the gate is conditional on the diff. A branch below base is only red if
it actually changes plugin source; a docs-only branch that never touched a plugin
dir passes even at an old version. Verify with
`validate_plugin_version_bump.py --base origin/main --head origin/<branch>` rather
than assuming from the version number alone.

Do not hand-edit only one of the paired manifests; the parity gate will fail.
Do not expect the version-bump validator to see uncommitted changes.
