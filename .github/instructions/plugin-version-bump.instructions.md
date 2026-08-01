---
applyTo: .claude/**,src/copilot-cli/**,src/claude/**,**/.claude-plugin/plugin.json
---

# Plugin Version Bump (ADR-091: post-merge bot owns the parity versions)

**Do NOT manually bump `.claude/.claude-plugin/plugin.json` or
`src/copilot-cli/.claude-plugin/plugin.json`.** A post-merge bot handles
parity-pair versions after every merge to `main`. If your PR includes a
version bump in either of those files, the CI gate will block it with
`manually-bumped`.

## Which manifests bump, and who owns them

There are two independent version lines:

- **Parity pair (bot-managed).** `.claude/.claude-plugin/plugin.json` and
  `src/copilot-cli/.claude-plugin/plugin.json` are owned by the post-merge bot
  (ADR-091). Do NOT touch them. If you accidentally committed a version bump to
  either file, revert it before pushing.
- **Separate line (author-managed).** `src/claude/.claude-plugin/plugin.json`
  tracks its own line. Bump it when you touch `src/claude/**`, the same way you
  always have. The strict-greater-SemVer rule still applies here.

## What to do if the gate says `manually-bumped`

You have a version change in `.claude/.claude-plugin/plugin.json` or
`src/copilot-cli/.claude-plugin/plugin.json`. Revert it:

```bash
git checkout origin/main -- .claude/.claude-plugin/plugin.json src/copilot-cli/.claude-plugin/plugin.json
git add .claude/.claude-plugin/plugin.json src/copilot-cli/.claude-plugin/plugin.json
git commit --amend --no-edit   # or a new commit if already pushed
```

Then re-run `python3 build/scripts/validate_plugin_version_bump.py --base origin/main`
to confirm the gate passes.

## The `src/claude` line (unchanged)

Set the new version to `max(base_version) + 1`. If another PR is already in
flight at `base + 1`, target `base + 2`. Run the validator to confirm:

```bash
python3 build/scripts/validate_plugin_version_bump.py --base origin/main
```

The validator reads committed state, not the working tree, so commit before
running it.

## Prior behavior (superseded by ADR-091)

Before ADR-091, authors were required to bump both parity manifests on every
PR touching parity source dirs. That requirement created an O(N^2) conflict
class: 11+ PRs could not land without rebumping each time another landed. The
post-merge bot removes that class entirely. The old recipe in this file is no
longer correct.
