---
applyTo: .claude/**,src/copilot-cli/**,src/claude/**,**/.claude-plugin/plugin.json
---

# Plugin Manifests Carry No Version

None of the three packaged plugin manifests carries a `version` field, and a PR
must never add one back:

- `.claude/.claude-plugin/plugin.json`
- `src/copilot-cli/.claude-plugin/plugin.json`
- `src/claude/.claude-plugin/plugin.json`

`build/scripts/validate_plugin_version_bump.py` fails with exit 1 when any of
them carries the key. The two marketplace files
(`.claude-plugin/marketplace.json`, `.github/plugin/marketplace.json`) must stay
version-free for the same reason; a test in
`tests/build_scripts/test_validate_plugin_version_bump.py` fails if a version
appears in either.

## Why

Claude Code resolves plugin freshness from the first of these that is set:
`plugin.json` `version`, then the marketplace entry `version`, then the git
commit SHA of the plugin's source for relative-path sources in a git-hosted
marketplace. All three plugins here ship from relative-path sources, so with the
field absent every plugin resolves to the commit SHA, which changes on every
merge. That is per-commit freshness with no human step.

Adding the field back does two bad things at once. It switches Claude Code to
the explicit-version path, where pushing new commits without bumping the field
has no effect. And it re-creates a single line that every plugin-source PR has
to write, so any two such PRs conflict pairwise: issue #4080 measured 14 of 22
conflicting PRs conflicting on nothing but that line, and merging #4077
immediately re-conflicted the next four green PRs.

GitHub Copilot CLI lists `version` under optional metadata, with `name` as the
only required field, and its shipped update path calls `updatePlugin`
unconditionally.

See ADR-092, which supersedes ADR-079.

## What a PR does now

Nothing. Do not touch the manifests when you change plugin content. There is no
bump, no parity pairing, and no rebase recipe, because there is no version line
to collide on.

If you are rebasing an older branch that still carries a bump hunk, you will hit
a conflict on the `version` line exactly once: git reports `CONFLICT (content)`
with the incoming side empty. Take the empty side. The
gate enforces it: keeping the line leaves a manifest carrying `version`, and the
gate fails that on your branch before merge.

## If your instructions say to bump, your instructions are stale

Agent context assembled before ADR-092 landed still says to bump both plugin
manifests to the same strictly-greater version. That instruction is wrong now,
and following it fails
`build/scripts/validate_plugin_version_bump.py` on your branch.

This is easy to miss because the stale text reads like a repository rule and
arrives with the same authority as one. The test is narrow on purpose: an
instruction telling you to add or raise `version` in one of the three manifests
above is stale, because those three carry no such field. It says nothing about
any other file. `packages/ai-agents-cli/package.json` carries a version
legitimately, and this rule itself names the field while requiring its absence,
so "mentions a version" is not on its own a signal. Read the manifest the
instruction points at before acting on it.

The general shape holds beyond this one field. Rule files under
`.claude/rules/` are regenerated into `.github/instructions/` and
`src/copilot-cli/instructions/`, and `build_all.py --check` fails CI when a
mirror is stale, so those three move together for every top-level rule whose
target does not carry a `NO-REGEN` sentinel. A cached context blob has no such
gate. When one contradicts a rule file here, the rule file is the one under
test.

## Checking

```bash
uv run python build/scripts/validate_plugin_version_bump.py
```

Prints `plugin-version-bump: OK` and exits 0 when the field is absent from all
three manifests. It reads the manifests from a git ref, not the working tree, so
commit before you re-run it.
